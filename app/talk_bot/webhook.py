"""
Webhook-Endpunkt fuer den Nextcloud-Talk-Bot.

Laeuft als ExApp hinter AppAPI: eingehende Talk-Bot-Nachrichten kommen
bereits durch die AppAPIAuthMiddleware validiert an (siehe main.py), die
Nachricht selbst wird ueber nc_py_api.ex_app.atalk_bot_msg geparst - eine
eigene HMAC-Signaturpruefung wie frueher in app/talk_bot/talk_api.py ist
dafuer nicht mehr noetig. Antworten laufen ueber die zentrale Bot-Instanz
in app/talk_bot/bot.py (registriert/verwaltet ihr Secret selbst über AppAPI).

Foto-Anhaenge: Talk schickt geteilte Dateien als Nachricht "{file}" mit
einem Rich-Object-Parameter, z.B.

    {"message": "{file}", "parameters": {"file": {"type": "file", "id": "123",
     "name": "IMG.jpg", "path": "Talk/IMG.jpg", "mimetype": "image/jpeg", ...}}}

(nc_py_api.talk_bot.TalkBotMessage.object_content ist genau dieses per
json.loads geparste "content"-Feld). Heruntergeladen wird NICHT ueber den
mitgeschickten Link (SSRF), sondern per WebDAV im Namen des Absenders -
ueber die Datei-ID, ersatzweise den Pfad relativ zu seinem Home.
Zum Pruefen des Formats auf einer echten Instanz: TALK_DEBUG_PAYLOAD=true
loggt den rohen Nachrichteninhalt.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import typing
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends
from nc_py_api.ex_app import atalk_bot_msg
from nc_py_api.talk_bot import TalkBotMessage
from sqlalchemy.orm import Session

from app.access import CurrentUser, load_user, standalone_mode
from app.db import SessionLocal
from app.geocoding import extract_gps_from_photo, reverse_geocode
from app.i18n import t
from app.models import FuelEntry, Vehicle
from app.ocr.engine import run_ocr
from app.ocr.parser import parse_beleg, parse_tacho
from app.photo_storage import (
    MAX_PHOTO_BYTES,
    PhotoError,
    PhotoKind,
    PhotoStorageError,
    PhotoTooLargeError,
    save_photo,
    validate_photo,
)
from app.talk_bot import session as capture_session
from app.talk_bot.bot import bot
from app.talk_bot.rebind import remember_conversation
from app.validation import KilometerstandUnplausibelError, pruefe_verbrauch

router = APIRouter(prefix="/talk-bot", tags=["talk-bot"])

LOGGER = logging.getLogger(__name__)

CONFIRM_WORDS = {"ja", "ok", "passt", "👍"}


class TalkAttachment(typing.NamedTuple):
    file_id: str | None
    path: str | None
    mimetype: str


def extract_talk_attachment(content: dict) -> TalkAttachment | None:
    """Datei-Anhang aus dem object_content einer Talk-Nachricht (reine
    Funktion, siehe Modul-Docstring). None, wenn die Nachricht keine Datei
    enthaelt. Der Link aus dem Payload wird bewusst ignoriert."""
    params = content.get("parameters") if isinstance(content, dict) else None
    # PHP serialisiert leere Parameter als [] statt {}.
    if not isinstance(params, dict):
        return None
    file_param = params.get("file")
    if not isinstance(file_param, dict) or file_param.get("type") != "file":
        return None

    file_id = str(file_param.get("id") or "").strip()
    if not file_id.isdigit():
        file_id = None

    path = str(file_param.get("path") or "").strip().lstrip("/")
    if not path or "\\" in path or ".." in PurePosixPath(path).parts:
        path = None

    if file_id is None and path is None:
        return None
    return TalkAttachment(file_id=file_id, path=path, mimetype=str(file_param.get("mimetype") or "").lower())


def _debug_payload_enabled() -> bool:
    return os.environ.get("TALK_DEBUG_PAYLOAD", "false").lower() == "true"


def _log_raw_payload(message: TalkBotMessage) -> None:
    # Ohne konfiguriertes Root-Logging wuerde INFO sonst verschluckt.
    if not LOGGER.isEnabledFor(logging.INFO):
        LOGGER.setLevel(logging.INFO)
    if not LOGGER.handlers and not logging.getLogger().handlers:
        LOGGER.addHandler(logging.StreamHandler())
    LOGGER.info(
        "TALK_DEBUG_PAYLOAD actor=%s conversation=%s object_name=%s media_type=%s object_content=%s",
        message.actor_id,
        message.conversation_token,
        message.object_name,
        message.object_media_type,
        json.dumps(message.object_content, ensure_ascii=False),
    )


async def download_talk_attachment(uid: str, attachment: TalkAttachment) -> bytes:
    """Laedt den Anhang per WebDAV als der absendende Nutzer (dessen Datei
    liegt in seinem Home, i.d.R. im Ordner "Talk")."""
    from nc_py_api import AsyncNextcloudApp

    nc = AsyncNextcloudApp(user=uid)
    node = None
    if attachment.file_id:
        try:
            node = await nc.files.by_id(attachment.file_id)
        except Exception:  # noqa: BLE001 - dann ueber den Pfad versuchen
            LOGGER.warning("Talk-Anhang %s von %s nicht per ID gefunden", attachment.file_id, uid, exc_info=True)
    if node is not None:
        if node.info.mimetype and not node.info.mimetype.lower().startswith("image/"):
            raise PhotoError("Nur Fotos werden ausgewertet")
        if node.info.content_length > MAX_PHOTO_BYTES:
            raise PhotoTooLargeError(f"Foto ist größer als {MAX_PHOTO_BYTES // (1024 * 1024)} MB")
        return await nc.files.download(node)
    if attachment.path:
        return await nc.files.download(attachment.path)
    raise PhotoStorageError("Talk-Anhang nicht gefunden")


async def _talk_user(message: TalkBotMessage) -> CurrentUser | None:
    """Absender als Nextcloud-Nutzer; Gaeste/Federated-User haben keinen
    Fahrzeugzugriff."""
    kind, _, uid = message.actor_id.partition("/")
    if standalone_mode():
        return CurrentUser(uid=uid if kind == "users" and uid else "dev", superuser=True)
    if kind != "users" or not uid:
        return None
    return await load_user(uid)


async def _reply(message: TalkBotMessage, text: str) -> None:
    await bot.send_message(text, reply_to_message=message.object_id, token=message.conversation_token)


async def _store_session_photos(db: Session, entry: FuelEntry, session: capture_session.CaptureSession) -> bool:
    """Legt die Fotos der Session beim Fahrzeugbesitzer ab. Der Eintrag
    bleibt auch bei einem Fehler gespeichert; False signalisiert das."""
    vehicle = db.get(Vehicle, entry.vehicle_id)
    ok = True
    for kind, data in ((PhotoKind.TACHO, session.tacho_foto), (PhotoKind.BELEG, session.beleg_foto)):
        if not data:
            continue
        try:
            path = await save_photo(vehicle, kind, entry.datum, data, suffix=str(entry.id))
        except Exception:  # noqa: BLE001 - Eintrag nicht an der Foto-Ablage scheitern lassen
            LOGGER.exception("Talk-Foto (%s) fuer Eintrag %s nicht abgelegt", kind.value, entry.id)
            ok = False
            continue
        setattr(entry, f"{kind.value}_foto_pfad", path)
    db.commit()
    return ok


@router.post("/webhook")
async def talk_webhook(message: typing.Annotated[TalkBotMessage, Depends(atalk_bot_msg)]):
    if message.message_type != "Create":
        return {"status": "ignored"}

    db: Session = SessionLocal()
    try:
        kind, _, uid = message.actor_id.partition("/")
        if kind == "users" and uid:
            # fuer das automatische Wiederaktivieren nach einem Deploy
            remember_conversation(db, message.conversation_token, uid)
        await _handle_message(message, db)
    finally:
        db.close()

    return {"status": "ok"}


async def _handle_message(message: TalkBotMessage, db: Session) -> None:
    if _debug_payload_enabled():
        _log_raw_payload(message)

    token = message.conversation_token
    actor = message.actor_id
    content = message.object_content
    attachment = extract_talk_attachment(content)
    text = (content.get("message") or "").strip()
    if attachment and text == "{file}":
        text = ""  # Platzhalter, keine Bildunterschrift

    user = await _talk_user(message)
    if user is None:
        return
    session = capture_session.get_or_create_session(token, actor)

    # 1) Fahrzeug-Zuordnung per Codewort, falls noch nicht gesetzt (auch als
    #    Bildunterschrift moeglich - dann wird das Foto direkt mit verarbeitet)
    if session.vehicle_id is None and text:
        vehicle = capture_session.resolve_vehicle_by_codewort(db, text, user)
        if vehicle:
            session.vehicle_id = vehicle.id
            if not attachment:
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
    if not attachment and session.is_complete and text.lower() in CONFIRM_WORDS:
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

        entry = capture_session.build_fuel_entry(session, erfasst_von=user.uid)
        db.add(entry)
        db.commit()
        warnungen = pruefe_verbrauch(db, entry)
        fotos_ok = await _store_session_photos(db, entry, session)
        capture_session.clear_session(token, actor)

        nachricht = t("entry_saved")
        if warnungen:
            nachricht += "\n⚠️ " + " / ".join(warnungen)
        if not fotos_ok:
            nachricht += "\n" + t("photo_store_failed")
        await _reply(message, nachricht)
        return

    # 3) Foto-Anhang verarbeiten
    if attachment:
        if attachment.mimetype and not attachment.mimetype.startswith("image/"):
            await _reply(message, t("photo_not_image"))
            return
        local_path = None
        try:
            data = await download_talk_attachment(user.uid, attachment)
            _mimetype, ext = validate_photo(data)
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as f:
                f.write(data)
                local_path = f.name
            ocr_result = run_ocr(local_path)

            # Heuristik: erstes Foto in einer neuen Session = Tacho, zweites =
            # Beleg. Alternative: der Nutzer schickt "tacho"/"beleg" als
            # Bildunterschrift - dafuer muesste text zusaetzlich ausgewertet
            # werden.
            if session.tacho is None:
                session.tacho = parse_tacho(ocr_result)
                session.tacho_foto = data
                await _reply(message, t("tacho_recognized"))
            elif session.beleg is None:
                session.beleg = parse_beleg(ocr_result)
                session.beleg_foto = data
                gps = extract_gps_from_photo(local_path)
                if gps:
                    session.beleg.tankstelle_name = reverse_geocode(*gps)
        except PhotoError as exc:
            await _reply(message, t("photo_invalid", fehler=str(exc)))
            return
        except Exception:  # noqa: BLE001 - Download/OCR fehlgeschlagen
            LOGGER.exception("Talk-Foto von %s konnte nicht verarbeitet werden", actor)
            await _reply(message, t("photo_processing_failed"))
            return
        finally:
            if local_path and os.path.exists(local_path):
                os.remove(local_path)

        if session.is_complete and session.vehicle_id is not None:
            vehicle = db.get(Vehicle, session.vehicle_id)
            await _reply(message, capture_session.format_confirmation_message(session, vehicle))
        return

    # 4) Sonst: kurze Hilfe
    if text:
        await _reply(message, t("help_text"))
