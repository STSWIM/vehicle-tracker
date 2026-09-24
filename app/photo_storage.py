"""
Ablage von Beleg- und Tachofotos.

ExApp-Modus: in den Nextcloud-Dateien des Fahrzeug-BESITZERS unter
``Fahrzeuge/<Kennzeichen>/Belege/`` - egal, wer das Foto geschickt oder
hochgeladen hat. Die ExApp greift dafuer per WebDAV im Namen des Besitzers
zu (AppAPI-Impersonation ueber ``AsyncNextcloudApp(user=...)``, Scope FILES).
Freigegebene Nutzer sehen die Fotos ueber GET /api/fuel-entries/{id}/foto,
das die Datei wiederum im Kontext des Besitzers ausliefert.

Standalone-Modus (lokale Entwicklung/Tests ohne Nextcloud): gleiche
Ordnerstruktur lokal unter ``<APP_PERSISTENT_STORAGE oder ./data>/fotos/<Besitzer>/``.

In der Datenbank steht in beiden Faellen derselbe Pfad relativ zum Home
des Besitzers, z.B. ``Fahrzeuge/RT-WI 14/Belege/2024-05-01_beleg_17.jpg``.
"""
from __future__ import annotations

import datetime
import enum
import logging
import os
import re
from pathlib import Path, PurePosixPath

from app.access import standalone_mode
from app.models import Vehicle

LOGGER = logging.getLogger(__name__)

MAX_PHOTO_BYTES = 15 * 1024 * 1024

MIMETYPE_BY_EXT = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "heic": "image/heic",
}

_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}


class PhotoKind(str, enum.Enum):
    BELEG = "beleg"
    TACHO = "tacho"


class PhotoError(ValueError):
    """Ungueltiges Foto (leer, zu gross, kein Bild) - Fehler des Absenders."""


class PhotoTooLargeError(PhotoError):
    pass


class PhotoStorageError(RuntimeError):
    """Ablage/Abruf fehlgeschlagen (Nextcloud nicht erreichbar, ...)."""


class PhotoNotFoundError(PhotoStorageError):
    pass


def detect_image_type(data: bytes) -> tuple[str, str] | None:
    """(mimetype, endung) anhand der Magic Bytes - dem vom Client
    mitgeschickten Content-Type wird bewusst nicht vertraut."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    if data[4:8] == b"ftyp" and data[8:12] in _HEIF_BRANDS:
        return "image/heic", "heic"
    return None


def validate_photo(data: bytes) -> tuple[str, str]:
    if not data:
        raise PhotoError("Leere Datei")
    if len(data) > MAX_PHOTO_BYTES:
        raise PhotoTooLargeError(f"Foto ist größer als {MAX_PHOTO_BYTES // (1024 * 1024)} MB")
    detected = detect_image_type(data)
    if detected is None:
        raise PhotoError("Nur Fotos (JPEG, PNG, WebP, HEIC) sind erlaubt")
    return detected


def _safe_name(value: str) -> str:
    """Kennzeichen/Nutzer-ID als Ordnernamen: keine Pfadtrenner, keine
    Steuerzeichen, kein '.'/'..'."""
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "-", value).strip(" .")
    return cleaned or "_"


def photo_folder(vehicle: Vehicle) -> str:
    return f"Fahrzeuge/{_safe_name(vehicle.kennzeichen)}/Belege"


def photo_filename(kind: PhotoKind, datum: datetime.date, suffix: str, ext: str) -> str:
    return f"{datum.isoformat()}_{kind.value}_{_safe_name(suffix)}.{ext}"


def mimetype_for_path(path: str) -> str:
    return MIMETYPE_BY_EXT.get(PurePosixPath(path).suffix.lstrip(".").lower(), "application/octet-stream")


def _check_path(path: str) -> None:
    """Nur von uns erzeugte Pfade (Fahrzeuge/<K>/Belege/<Datei>) zulassen -
    Schutz davor, ueber einen manipulierten DB-Wert beliebige Dateien des
    Besitzers auszuliefern."""
    parts = PurePosixPath(path).parts
    if (
        not path
        or "\\" in path
        or path.startswith("/")
        or len(parts) != 4
        or parts[0] != "Fahrzeuge"
        or parts[2] != "Belege"
        or any(p in {".", ".."} for p in parts)
    ):
        raise PhotoStorageError(f"Ungültiger Fotopfad: {path!r}")


def _local_root(vehicle: Vehicle) -> Path:
    base = Path(os.environ.get("APP_PERSISTENT_STORAGE") or "./data")
    return base / "fotos" / _safe_name(vehicle.owner or "_")


def _nc_as(uid: str):
    from nc_py_api import AsyncNextcloudApp

    return AsyncNextcloudApp(user=uid)


async def save_photo(
    vehicle: Vehicle, kind: PhotoKind, datum: datetime.date, data: bytes, suffix: str
) -> str:
    """Speichert das Foto beim Besitzer des Fahrzeugs und liefert den Pfad
    fuer beleg_foto_pfad/tacho_foto_pfad. suffix macht den Dateinamen
    eindeutig (i.d.R. die Eintrags-ID); gleicher Name ueberschreibt."""
    _mimetype, ext = validate_photo(data)
    folder = photo_folder(vehicle)
    path = f"{folder}/{photo_filename(kind, datum, suffix, ext)}"

    if standalone_mode():
        target = _local_root(vehicle) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return path

    if not vehicle.owner:
        raise PhotoStorageError("Fahrzeug hat keinen Besitzer - Foto kann nicht abgelegt werden")
    nc = _nc_as(vehicle.owner)
    try:
        await nc.files.makedirs(folder, exist_ok=True)
        await nc.files.upload(path, data)
    except Exception as exc:  # noqa: BLE001 - WebDAV-/Verbindungsfehler
        LOGGER.exception("Foto %s konnte bei %s nicht abgelegt werden", path, vehicle.owner)
        raise PhotoStorageError("Foto konnte nicht in Nextcloud abgelegt werden") from exc
    return path


async def load_photo(vehicle: Vehicle, path: str) -> bytes:
    _check_path(path)

    if standalone_mode():
        try:
            return (_local_root(vehicle) / path).read_bytes()
        except FileNotFoundError as exc:
            raise PhotoNotFoundError(path) from exc

    if not vehicle.owner:
        raise PhotoNotFoundError(path)
    from nc_py_api import NextcloudException

    try:
        return await _nc_as(vehicle.owner).files.download(path)
    except NextcloudException as exc:
        if exc.status_code == 404:
            raise PhotoNotFoundError(path) from exc
        LOGGER.exception("Foto %s konnte bei %s nicht geladen werden", path, vehicle.owner)
        raise PhotoStorageError("Foto konnte nicht aus Nextcloud geladen werden") from exc
    except Exception as exc:  # noqa: BLE001 - Verbindungsfehler o.ae.
        LOGGER.exception("Foto %s konnte bei %s nicht geladen werden", path, vehicle.owner)
        raise PhotoStorageError("Foto konnte nicht aus Nextcloud geladen werden") from exc
