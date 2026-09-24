"""
Reimplementierung der Kennzahlen, die in der Excel-Datei ueber verschachtelte
Formeln (u.a. die Tages-Interpolation im Blatt 'Gesamtstatistik') berechnet
wurden – hier als nachvollziehbarer Python-Code statt Tabellenformeln.

Verbrauchsberechnung folgt der ueblichen "Voll-zu-Voll"-Methode: nur
Tankungen mit nicht_voll=False gelten als verlaessliche Referenzpunkte,
weil nur dann klar ist, wie viel Kraftstoff seit der letzten Volltankung
tatsaechlich verbraucht wurde.

Auswertungszeitraum: ohne von/bis der gesamte Zeitraum (Kauf bis heute bzw.
Verkauf), sonst der gewaehlte. Kaufpreis und km-Stand bei Kauf zaehlen nur,
wenn der Kauf im Zeitraum liegt (ohne Kaufdatum: nur beim Gesamtzeitraum).
Anschaffungskosten = Kaufpreis + Kosten der Kategorie "Einmalig".
"""
from __future__ import annotations

import datetime
from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.access import CurrentUser, get_accessible_vehicle, get_current_user
from app.consumption import verbrauch_nach_kraftstoff
from app.db import get_db
from app.models import Kostenkategorie, Kraftstoffart, Vehicle
from app.schemas import VehicleStats

router = APIRouter(prefix="/api/vehicles", tags=["stats"])


@router.get("/{vehicle_id}/stats", response_model=VehicleStats)
def get_vehicle_stats(
    vehicle_id: int,
    von: datetime.date | None = None,
    bis: datetime.date | None = None,
    mit_anschaffung: bool = True,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> VehicleStats:
    vehicle = get_accessible_vehicle(db, vehicle_id, user)
    return compute_vehicle_stats(vehicle, von, bis, mit_anschaffung)


def compute_vehicle_stats(
    vehicle: Vehicle,
    von: datetime.date | None = None,
    bis: datetime.date | None = None,
    mit_anschaffung: bool = True,
) -> VehicleStats:
    """Kennzahlen eines Fahrzeugs fuer den Zeitraum - auch vom Export
    (app/export.py) genutzt, damit der PDF-Bericht dieselben Zahlen zeigt
    wie die Auswertung in der Oberflaeche."""
    vehicle_id = vehicle.id

    def im_zeitraum(datum: datetime.date) -> bool:
        return (von is None or datum >= von) and (bis is None or datum <= bis)

    gesamtzeitraum = von is None and bis is None
    kauf_im_zeitraum = im_zeitraum(vehicle.kaufdatum) if vehicle.kaufdatum else gesamtzeitraum

    fuel_entries = sorted(
        (e for e in vehicle.fuel_entries if im_zeitraum(e.datum)), key=lambda e: e.kilometerstand
    )
    other_costs = [c for c in vehicle.other_costs if im_zeitraum(c.datum)]
    trips = [t for t in vehicle.trips if im_zeitraum(t.datum)]
    logbook = [entry for entry in vehicle.logbook_entries if im_zeitraum(entry.datum)]

    einmalig = [c for c in other_costs if c.kategorie == Kostenkategorie.EINMALIG]
    laufend = [c for c in other_costs if c.kategorie != Kostenkategorie.EINMALIG]

    kaufpreis = (vehicle.kaufpreis or 0.0) if kauf_im_zeitraum else 0.0
    anschaffungskosten = kaufpreis + sum(c.betrag for c in einmalig)
    gesamt_kraftstoffkosten = sum(e.gesamtpreis for e in fuel_entries)
    gesamt_sonstige_kosten = sum(c.betrag for c in laufend)
    gesamtkosten = gesamt_kraftstoffkosten + gesamt_sonstige_kosten
    if mit_anschaffung:
        gesamtkosten += anschaffungskosten

    kosten_nach_kategorie: dict[str, float] = defaultdict(float)
    for c in laufend:
        kosten_nach_kategorie[c.kategorie.value] += c.betrag

    km_punkte = [e.kilometerstand for e in fuel_entries]
    km_punkte += [km for t in trips for km in (t.km_start, t.km_ende)]
    km_punkte += [entry.kilometerstand for entry in logbook if entry.kilometerstand is not None]
    if kauf_im_zeitraum and vehicle.kaufkilometerstand is not None:
        km_punkte.append(vehicle.kaufkilometerstand)
    gefahrene_km = float(max(km_punkte) - min(km_punkte)) if len(km_punkte) >= 2 else 0.0

    daten = [e.datum for e in fuel_entries] + [c.datum for c in other_costs]
    daten += [t.datum for t in trips] + [entry.datum for entry in logbook]
    if kauf_im_zeitraum and vehicle.kaufdatum:
        daten.append(vehicle.kaufdatum)
    zeitraum_von = von or (min(daten) if daten else None)
    zeitraum_bis = bis or ((vehicle.verkauft_am or datetime.date.today()) if daten else None)

    kosten_pro_monat = None
    if zeitraum_von and zeitraum_bis and zeitraum_bis > zeitraum_von:
        kosten_pro_monat = gesamtkosten / ((zeitraum_bis - zeitraum_von).days / 30.44)

    kosten_lpg = sum(e.gesamtpreis for e in fuel_entries if e.kraftstoffart == Kraftstoffart.LPG)
    kosten_benzin = sum(e.gesamtpreis for e in fuel_entries if e.kraftstoffart == Kraftstoffart.BENZIN)
    anteil_lpg = kosten_lpg / gesamt_kraftstoffkosten if gesamt_kraftstoffkosten else None
    anteil_benzin = kosten_benzin / gesamt_kraftstoffkosten if gesamt_kraftstoffkosten else None

    kosten_pro_km = gesamtkosten / gefahrene_km if gefahrene_km > 0 else None
    start_km = (
        vehicle.kaufkilometerstand
        if vehicle.bei_kauf_vollgetankt and kauf_im_zeitraum
        else None
    )
    verbrauch_je_art = verbrauch_nach_kraftstoff(fuel_entries, start_km)
    verbrauch = next(iter(verbrauch_je_art.values())) if len(verbrauch_je_art) == 1 else None

    return VehicleStats(
        vehicle_id=vehicle_id,
        zeitraum_von=zeitraum_von,
        zeitraum_bis=zeitraum_bis,
        mit_anschaffung=mit_anschaffung,
        gefahrene_km=gefahrene_km,
        gesamt_kraftstoffkosten=round(gesamt_kraftstoffkosten, 2),
        gesamt_sonstige_kosten=round(gesamt_sonstige_kosten, 2),
        anschaffungskosten=round(anschaffungskosten, 2),
        kosten_nach_kategorie={k: round(v, 2) for k, v in kosten_nach_kategorie.items()},
        gesamtkosten=round(gesamtkosten, 2),
        verbrauch_nach_kraftstoff={k: round(v, 2) for k, v in verbrauch_je_art.items()},
        ø_verbrauch_l_100km=round(verbrauch, 2) if verbrauch is not None else None,
        kosten_pro_km=round(kosten_pro_km, 3) if kosten_pro_km is not None else None,
        kosten_pro_monat=round(kosten_pro_monat, 2) if kosten_pro_monat is not None else None,
        anteil_lpg=round(anteil_lpg, 3) if anteil_lpg is not None else None,
        anteil_benzin=round(anteil_benzin, 3) if anteil_benzin is not None else None,
    )
