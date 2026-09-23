"""
EXIF-GPS-Auslesung aus Fotos (fuer die Tankstellen-Karte) plus optionales
Reverse-Geocoding ueber Nominatim (OpenStreetMap) – bewusst kein Google
Maps, um ohne API-Key/Kosten auszukommen und selbst hostbar zu bleiben.
"""
from __future__ import annotations

import httpx
import piexif


def _dms_to_decimal(dms: tuple, ref: bytes) -> float:
    degrees, minutes, seconds = (
        dms[0][0] / dms[0][1],
        dms[1][0] / dms[1][1],
        dms[2][0] / dms[2][1],
    )
    value = degrees + minutes / 60 + seconds / 3600
    if ref in (b"S", b"W"):
        value = -value
    return value


def extract_gps_from_photo(image_path: str) -> tuple[float, float] | None:
    """Liest GPS-Koordinaten aus den EXIF-Metadaten eines Fotos, falls
    vorhanden (Standortfreigabe der Handykamera muss dafuer aktiv sein)."""
    try:
        exif = piexif.load(image_path)
    except Exception:  # noqa: BLE001 - kein/kaputtes EXIF ist ein normaler Fall
        return None

    gps = exif.get("GPS")
    if not gps:
        return None

    try:
        lat = _dms_to_decimal(gps[piexif.GPSIFD.GPSLatitude], gps[piexif.GPSIFD.GPSLatitudeRef])
        lon = _dms_to_decimal(gps[piexif.GPSIFD.GPSLongitude], gps[piexif.GPSIFD.GPSLongitudeRef])
    except KeyError:
        return None

    return lat, lon


def reverse_geocode(lat: float, lon: float, *, nominatim_url: str | None = None) -> str | None:
    """Ermittelt einen Tankstellen-/Adressnamen zu Koordinaten. Nutzt per
    Default den oeffentlichen Nominatim-Dienst (fairer-use-Limits!) –
    fuer regen Gebrauch besser eine eigene Nominatim-Instanz betreiben und
    NOMINATIM_URL entsprechend setzen."""
    url = nominatim_url or "https://nominatim.openstreetmap.org/reverse"
    try:
        response = httpx.get(
            url,
            params={"lat": lat, "lon": lon, "format": "jsonv2"},
            headers={"User-Agent": "vehicle-tracker-exapp/0.1 (witt14.de)"},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:  # noqa: BLE001
        return None

    return data.get("name") or data.get("display_name")
