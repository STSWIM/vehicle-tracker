"""
Webhook-Endpunkt fuer den Nextcloud-Talk-Bot.

Laeuft als ExApp hinter AppAPI: eingehende Talk-Bot-Nachrichten kommen
bereits durch die AppAPIAuthMiddleware validiert an (siehe main.py), die
Nachricht selbst wird ueber nc_py_api.ex_app.atalk_bot_msg geparst - eine
eigene HMAC-Signaturpruefung wie frueher in app/talk_bot/talk_api.py ist
dafuer nicht mehr noetig. Antworten laufen ueber die zentrale Bot-Instanz
in app/talk_bot/bot.py (registriert/verwaltet ihr Secret selbst über AppAPI).

ACHTUNG / TODO vor dem produktiven Einsatz: das Herauslösen von Bild-
Anhaengen aus dem Talk-Webhook-Payload ist der Teil, der laut Community-
Berichten je nach Talk-Version noch nicht ganz rund laeuft (siehe
Diskussion in docs/ARCHITECTURE.md). '_extract_attached_image_url' ist
hier bewusst als klar markierter Platzhalter gehalten und muss gegen eine
echte Talk-Instanz getestet und ggf. angepasst werden. Bis das steht, ist
WhatsApp/Threema fuer den Foto-Versand der robustere Weg (s. README).
"""
from __future__ import annotations

import os
import tempfile
import typing

import httpx
from fastapi import APIRouter, Depends
from nc_py_api.ex_app import atalk_bot_msg
from nc_py_api.talk_bot import TalkBotMessage
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.geocoding import extract_gps_from_photo, reverse_geocode
from app.i18n import t
from app.ocr.engine import run_ocr
from app.ocr.parser import parse_beleg, parse_tacho
from app.talk_bot import session as capture_session
from app.talk_bot.bot import bot
from app.validation import KilometerstandUnplausibelError, pruefe_verbrauch

router = APIRouter(prefix="/talk-bot", tags=["talk-bot"])


def _extract_attached_image_url(content: dict) -> str | None:
    """Platzhalter: Talk liefert geteilte Dateien i.d.R. über
    content['parameters']['file'] mit einem 'link'/'path'-Feld. Muss gegen
    eine echte Instanz verifiziert werden - siehe Modul-Docstring."""
    params = content.get("parameters", {})
    file_param = params.get("file")
    if not file_param:
        return None
    return file_param.get("link") or file_param.get("path")


def _download_to_tempfile(url: str) -> str:
    response = httpx.get(url, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    suffix = ".jpg"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(response.content)
        return f.name


async def _reply(message: TalkBotMessage, text: str) -> None:
    await bot.send_message(text, reply_to_message=message.object_id, token=message.conversation_token)


@router.post("/webhook")
async def talk_webhook(message: typing.Annotated[TalkBotMessage, Depends(atalk_bot_msg)]):
    if message.message_type != "Create":
        return {"status": "ignored"}

    db: Session = SessionLocal()
    try:
        await _handle_message(message, db)
    finally:
        db.close()

    return {"status": "ok"}


async def _handle_message(message: TalkBotMessage, db: Session) -> None:
    token = message.conversation_token
    content = message.object_content
    text = (content.get("message") or "").strip()
    session = capture_session.get_or_create_session(token)

    # 1) Fahrzeug-Zuordnung per Codewort, falls noch nicht gesetzt
    if session.vehicle_id is None:
        vehicle = capture_session.resolve_vehicle_by_codewort(db, text)
        if vehicle:
            session.vehicle_id = vehicle.id
            if session.is_complete:
                # Fotos kamen bereits vor dem Codewort an - jetzt die
                # Zusammenfassung nachreichen statt sie zu verschlucken.
                await _reply(message, capture_session.format_confirmation_message(session, vehicle))
            else:
                await _reply(
                    message, t("vehicle_selected", hersteller=vehicle.hersteller, modell=vehicle.modell)
                )
            return

    # 2) Bestätigung eines vollständigen Vorschlags
    if session.is_complete and text.lower() in {"ja", "ok", "passt", "👍"}:
        if session.vehicle_id is None:
            await _reply(message, t("ask_codeword"))
            return

        fehlend = capture_session.fehlende_pflichtfelder(session)
        if fehlend:
            await _reply(message, t("missing_fields", felder=", ".join(fehlend)))
            return

        try:
            capture_session.pruefe_kilometerstand_fuer_session(db, session)
        except KilometerstandUnplausibelError as exc:
            await _reply(message, t("kilometerstand_unplausibel", fehler=str(exc)))
            return

        entry = capture_session.build_fuel_entry(session)
        db.add(entry)
        db.commit()
        warnungen = pruefe_verbrauch(db, entry)
        capture_session.clear_session(token)

        nachricht = t("entry_saved")
        if warnungen:
            nachricht += "\n⚠️ " + " / ".join(warnungen)
        await _reply(message, nachricht)
        return

    # 3) Foto-Anhang verarbeiten
    image_url = _extract_attached_image_url(content)
    if image_url:
        local_path = None
        try:
            local_path = _download_to_tempfile(image_url)
            ocr_result = run_ocr(local_path)

            # Heuristik: erstes Foto in einer neuen Session = Tacho, zweites =
            # Beleg. Alternative: der Nutzer schickt "tacho"/"beleg" als
            # Bildunterschrift - dafuer muesste text zusaetzlich ausgewertet
            # werden.
            if session.tacho is None:
                session.tacho = parse_tacho(ocr_result)
                await _reply(message, t("tacho_recognized"))
            elif session.beleg is None:
                session.beleg = parse_beleg(ocr_result)
                gps = extract_gps_from_photo(local_path)
                if gps:
                    session.beleg.tankstelle_name = reverse_geocode(*gps)
        except Exception:
            await _reply(message, t("photo_processing_failed"))
            return
        finally:
            if local_path and os.path.exists(local_path):
                os.remove(local_path)

        if session.is_complete and session.vehicle_id is not None:
            from app.models import Vehicle

            vehicle = db.get(Vehicle, session.vehicle_id)
            await _reply(message, capture_session.format_confirmation_message(session, vehicle))
        return

    # 4) Sonst: kurze Hilfe
    if text:
        await _reply(message, t("help_text"))
