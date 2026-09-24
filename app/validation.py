"""
Plausibilitaetspruefungen fuer neu erfasste Tankeintraege. Gilt fuer die
manuelle/REST-Erfassung (app/routers/fuel_entries.py) genauso wie fuer den
Talk-Bot (app/talk_bot/session.py), damit Kilometerstaende nie
widerspruechlich zur bestehenden Fahrhistorie gespeichert werden und
unplausible Verbrauchswerte auffallen statt unbemerkt in der Statistik zu
landen.
"""
from __future__ import annotations

import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.consumption import verbrauch_l_pro_100km
from app.models import FuelEntry, Vehicle

# Erfahrungswerte als Ausweichgrenze, solange fuer das Fahrzeug noch kein
# eigener Verbrauchsschnitt vorliegt (erste Volltankungen).
MIN_PLAUSIBLER_VERBRAUCH = 2.0
MAX_PLAUSIBLER_VERBRAUCH = 25.0
VERBRAUCH_ABWEICHUNG_TOLERANZ = 0.4  # 40 % Abweichung vom eigenen Schnitt


class KilometerstandUnplausibelError(ValueError):
    """Ein Kilometerstand widerspricht der bereits erfassten Fahrhistorie
    (kann an einem spaeteren Datum nicht sinken bzw. an einem frueheren
    Datum nicht ueber einem spaeter erfassten Stand liegen)."""


def pruefe_kilometerstand(
    db: Session,
    vehicle_id: int,
    datum: datetime.date,
    kilometerstand: int,
    *,
    exclude_entry_id: int | None = None,
) -> None:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is not None and vehicle.kaufkilometerstand is not None and kilometerstand < vehicle.kaufkilometerstand:
        raise KilometerstandUnplausibelError(
            f"Kilometerstand {kilometerstand} km liegt unter dem Kilometerstand "
            f"beim Kauf ({vehicle.kaufkilometerstand} km)."
        )

    q_vorherige = select(func.max(FuelEntry.kilometerstand)).where(
        FuelEntry.vehicle_id == vehicle_id, FuelEntry.datum <= datum
    )
    q_naechste = select(func.min(FuelEntry.kilometerstand)).where(
        FuelEntry.vehicle_id == vehicle_id, FuelEntry.datum > datum
    )
    if exclude_entry_id is not None:
        q_vorherige = q_vorherige.where(FuelEntry.id != exclude_entry_id)
        q_naechste = q_naechste.where(FuelEntry.id != exclude_entry_id)

    vorherige = db.execute(q_vorherige).scalar_one()
    if vorherige is not None and kilometerstand < vorherige:
        raise KilometerstandUnplausibelError(
            f"Kilometerstand {kilometerstand} km liegt unter einem bereits "
            f"erfassten Stand von {vorherige} km an einem frueheren oder "
            f"gleichen Datum."
        )

    naechste = db.execute(q_naechste).scalar_one()
    if naechste is not None and kilometerstand > naechste:
        raise KilometerstandUnplausibelError(
            f"Kilometerstand {kilometerstand} km liegt ueber einem bereits "
            f"erfassten Stand von {naechste} km an einem spaeteren Datum."
        )


def pruefe_verbrauch(db: Session, entry: FuelEntry) -> list[str]:
    """Warnt (blockiert nicht) bei stark unplausiblem Verbrauch seit der
    letzten Volltankung - z.B. weil OCR eine falsche Literzahl gelesen hat.
    Echte Ausreisser (lange Autobahnfahrt, Anhaenger, ...) sollen weiterhin
    speicherbar bleiben, nur eben mit Warnhinweis."""
    if entry.nicht_voll:
        return []

    fruehere = (
        db.execute(
            select(FuelEntry)
            .where(
                FuelEntry.vehicle_id == entry.vehicle_id,
                # je Kraftstoff getrennt, sonst vermischt ein bivalentes
                # Fahrzeug (LPG + Benzin) die Volltank-Ketten
                FuelEntry.kraftstoffart == entry.kraftstoffart,
                FuelEntry.kilometerstand < entry.kilometerstand,
                FuelEntry.id != entry.id,
            )
            .order_by(FuelEntry.kilometerstand.desc())
        )
        .scalars()
        .all()
    )
    letzte_volltankung = next((e for e in fruehere if not e.nicht_voll), None)
    if letzte_volltankung is None:
        return []

    km = entry.kilometerstand - letzte_volltankung.kilometerstand
    if km <= 0:
        return []

    segment = [e for e in fruehere if e.kilometerstand > letzte_volltankung.kilometerstand]
    liter = entry.fuellmenge_liter + sum(e.fuellmenge_liter for e in segment)
    aktueller_verbrauch = liter / km * 100

    historie = sorted(
        (e for e in fruehere if e.kilometerstand <= letzte_volltankung.kilometerstand),
        key=lambda e: e.kilometerstand,
    )
    historischer_schnitt = verbrauch_l_pro_100km(historie)

    if historischer_schnitt:
        abweichung = abs(aktueller_verbrauch - historischer_schnitt) / historischer_schnitt
        if abweichung > VERBRAUCH_ABWEICHUNG_TOLERANZ:
            return [
                f"Verbrauch dieser Tankung ({aktueller_verbrauch:.1f} l/100km) weicht "
                f"stark vom bisherigen Schnitt ({historischer_schnitt:.1f} l/100km) ab."
            ]
    elif not (MIN_PLAUSIBLER_VERBRAUCH <= aktueller_verbrauch <= MAX_PLAUSIBLER_VERBRAUCH):
        return [
            f"Verbrauch dieser Tankung ({aktueller_verbrauch:.1f} l/100km) wirkt unplausibel."
        ]
    return []
