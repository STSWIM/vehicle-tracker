"""
Webhook-Endpunkt fuer den Nextcloud-Talk-Bot.

ACHTUNG / TODO vor dem produktiven Einsatz: das Herauslösen von Bild-
Anhaengen aus dem Talk-Webhook-Payload ist der Teil, der laut Community-
Berichten je nach Talk-Version noch nicht ganz rund laeuft (siehe
Diskussion in docs/ARCHITECTURE.md). '_extract_attached_image_url' ist
hier bewusst als klar markierter Platzhalter gehalten und muss gegen eine
echte Talk-Instanz getestet und ggf. angepasst werden. Bis das steht, ist
WhatsApp/Threema fuer den Foto-Versand der robustere Weg (s. README).
"""
from __future__ import annotations

import json
import os
import tempfile

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.geocoding import extract_gps_from_photo, reverse_geocode
from app.i18n import t
from app.ocr.engine import run_ocr
from app.ocr.parser import parse_beleg, parse_tacho
from app.talk_bot import session as capture_session
from app.talk_bot.talk_api import send_reply, verify_signature
from app.validation import KilometerstandUnplausibelError, pruefe_verbrauch

router = APIRouter(prefix="/talk-bot", tags=["talk-bot"])

NEXTCLOUD_URL = os.environ.get("NEXTCLOUD_URL", "")


def _get_header_any(request: Request, names: tuple[str, ...]) -> str | None:
    for name in names:
        value = request.headers.get(name)
        if value:
            return value
    return None


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


@router.post("/webhook")
async def talk_webhook(request: Request):
    from app.talk_bot.talk_api import (
        RANDOM_HEADER_CANDIDATES,
        SIGNATURE_HEADER_CANDIDATES,
    )

    body = await request.body()
    random_value = _get_header_any(request, RANDOM_HEADER_CANDIDATES)
    signature = _get_header_any(request, SIGNATURE_HEADER_CANDIDATES)

    if not random_value or not signature or not verify_signature(random_value, signature, body):
        raise HTTPException(status_code=401, detail="Signatur ungültig")

    payload = json.loads(body)
    if payload.get("type") != "Create":
        return {"status": "ignored"}

    conversation_token = payload["target"]["id"]
    raw_content = payload["object"].get("content", "{}")
    content = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
    message_text = (content.get("message") or "").strip()

    db: Session = SessionLocal()
    try:
        await _handle_message(conversation_token, message_text, content, db)
    finally:
        db.close()

    return {"status": "ok"}


async def _handle_message(token: str, text: str, content: dict, db: Session) -> None:
    session = capture_session.get_or_create_session(token)

    # 1) Fahrzeug-Zuordnung per Codewort, falls noch nicht gesetzt
    if session.vehicle_id is None:
        vehicle = capture_session.resolve_vehicle_by_codewort(db, text)
        if vehicle:
            session.vehicle_id = vehicle.id
            if session.is_complete:
                # Fotos kamen bereits vor dem Codewort an - jetzt die
                # Zusammenfassung nachreichen statt sie zu verschlucken.
                send_reply(
                    NEXTCLOUD_URL, token,
                    capture_session.format_confirmation_message(session, vehicle),
                )
            else:
                send_reply(
                    NEXTCLOUD_URL, token,
                    t("vehicle_selected", hersteller=vehicle.hersteller, modell=vehicle.modell),
                )
            return

    # 2) Bestätigung eines vollständigen Vorschlags
    if session.is_complete and text.lower() in {"ja", "ok", "passt", "👍"}:
        if session.vehicle_id is None:
            send_reply(NEXTCLOUD_URL, token, t("ask_codeword"))
            return

        fehlend = capture_session.fehlende_pflichtfelder(session)
        if fehlend:
            send_reply(NEXTCLOUD_URL, token, t("missing_fields", felder=", ".join(fehlend)))
            return

        try:
            capture_session.pruefe_kilometerstand_fuer_session(db, session)
        except KilometerstandUnplausibelError as exc:
            send_reply(NEXTCLOUD_URL, token, t("kilometerstand_unplausibel", fehler=str(exc)))
            return

        entry = capture_session.build_fuel_entry(session)
        db.add(entry)
        db.commit()
        warnungen = pruefe_verbrauch(db, entry)
        capture_session.clear_session(token)

        nachricht = t("entry_saved")
        if warnungen:
            nachricht += "\n⚠️ " + " / ".join(warnungen)
        send_reply(NEXTCLOUD_URL, token, nachricht)
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
                send_reply(NEXTCLOUD_URL, token, t("tacho_recognized"))
            elif session.beleg is None:
                session.beleg = parse_beleg(ocr_result)
                gps = extract_gps_from_photo(local_path)
                if gps:
                    session.beleg.tankstelle_name = reverse_geocode(*gps)
        except Exception:
            send_reply(NEXTCLOUD_URL, token, t("photo_processing_failed"))
            return
        finally:
            if local_path and os.path.exists(local_path):
                os.remove(local_path)

        if session.is_complete and session.vehicle_id is not None:
            from app.models import Vehicle

            vehicle = db.get(Vehicle, session.vehicle_id)
            send_reply(
                NEXTCLOUD_URL, token, capture_session.format_confirmation_message(session, vehicle)
            )
        return

    # 4) Sonst: kurze Hilfe
    if text:
        send_reply(NEXTCLOUD_URL, token, t("help_text"))
