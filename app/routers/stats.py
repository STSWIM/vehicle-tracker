"""
Reimplementierung der Kennzahlen, die in der Excel-Datei ueber verschachtelte
Formeln (u.a. die Tages-Interpolation im Blatt 'Gesamtstatistik') berechnet
wurden – hier als nachvollziehbarer Python-Code statt Tabellenformeln.

Verbrauchsberechnung folgt der ueblichen "Voll-zu-Voll"-Methode: nur
Tankungen mit nicht_voll=False gelten als verlaessliche Referenzpunkte,
weil nur dann klar ist, wie viel Kraftstoff seit der letzten Volltankung
tatsaechlich verbraucht wurde.
"""
from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.consumption import verbrauch_l_pro_100km
from app.db import get_db
from app.models import FuelEntry, Kraftstoffart, OtherCost, Vehicle
from app.schemas import VehicleStats

router = APIRouter(prefix="/api/vehicles", tags=["stats"])


@router.get("/{vehicle_id}/stats", response_model=VehicleStats)
def get_vehicle_stats(
    vehicle_id: int,
    von: datetime.date | None = None,
    bis: datetime.date | None = None,
    db: Session = Depends(get_db),
) -> VehicleStats:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Fahrzeug nicht gefunden")

    fuel_q = select(FuelEntry).where(FuelEntry.vehicle_id == vehicle_id)
    cost_q = select(OtherCost).where(OtherCost.vehicle_id == vehicle_id)
    if von is not None:
        fuel_q = fuel_q.where(FuelEntry.datum >= von)
        cost_q = cost_q.where(OtherCost.datum >= von)
    if bis is not None:
        fuel_q = fuel_q.where(FuelEntry.datum <= bis)
        cost_q = cost_q.where(OtherCost.datum <= bis)

    fuel_entries = sorted(db.execute(fuel_q).scalars().all(), key=lambda e: e.kilometerstand)
    other_costs = db.execute(cost_q).scalars().all()

    if fuel_entries:
        gefahrene_km = float(fuel_entries[-1].kilometerstand - fuel_entries[0].kilometerstand)
        zeitraum_von = min(e.datum for e in fuel_entries)
        zeitraum_bis = max(e.datum for e in fuel_entries)
    else:
        gefahrene_km = 0.0
        zeitraum_von = von
        zeitraum_bis = bis

    gesamt_kraftstoffkosten = sum(e.gesamtpreis for e in fuel_entries)
    gesamt_sonstige_kosten = sum(c.betrag for c in other_costs)
    gesamtkosten = gesamt_kraftstoffkosten + gesamt_sonstige_kosten

    kosten_lpg = sum(e.gesamtpreis for e in fuel_entries if e.kraftstoffart == Kraftstoffart.LPG)
    kosten_benzin = sum(
        e.gesamtpreis for e in fuel_entries if e.kraftstoffart == Kraftstoffart.BENZIN
    )
    anteil_lpg = kosten_lpg / gesamt_kraftstoffkosten if gesamt_kraftstoffkosten else None
    anteil_benzin = kosten_benzin / gesamt_kraftstoffkosten if gesamt_kraftstoffkosten else None

    kosten_pro_km = gesamtkosten / gefahrene_km if gefahrene_km > 0 else None

    kosten_pro_monat = None
    if zeitraum_von and zeitraum_bis and zeitraum_bis > zeitraum_von:
        monate = (zeitraum_bis - zeitraum_von).days / 30.44
        if monate > 0:
            kosten_pro_monat = gesamtkosten / monate

    return VehicleStats(
        vehicle_id=vehicle_id,
        zeitraum_von=zeitraum_von,
        zeitraum_bis=zeitraum_bis,
        gefahrene_km=gefahrene_km,
        gesamt_kraftstoffkosten=round(gesamt_kraftstoffkosten, 2),
        gesamt_sonstige_kosten=round(gesamt_sonstige_kosten, 2),
        gesamtkosten=round(gesamtkosten, 2),
        ø_verbrauch_l_100km=(
            round(v, 2) if (v := verbrauch_l_pro_100km(fuel_entries)) is not None else None
        ),
        kosten_pro_km=round(kosten_pro_km, 3) if kosten_pro_km is not None else None,
        kosten_pro_monat=round(kosten_pro_monat, 2) if kosten_pro_monat is not None else None,
        anteil_lpg=round(anteil_lpg, 3) if anteil_lpg is not None else None,
        anteil_benzin=round(anteil_benzin, 3) if anteil_benzin is not None else None,
    )
