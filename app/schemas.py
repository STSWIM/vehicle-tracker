"""Pydantic-Schemas fuer die REST-API (Request/Response-Modelle)."""
from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict

from app.models import ErinnerungsTyp, Kostenkategorie, Kraftstoffart, Quelle


class VehicleCreate(BaseModel):
    kennzeichen: str
    hersteller: str
    modell: str
    variante: str | None = None
    tankvolumen_lpg_l: float | None = None
    tankvolumen_benzin_l: float | None = None
    kaufdatum: datetime.date | None = None
    kaufpreis: float | None = None
    bot_codewort: str | None = None


class VehicleOut(VehicleCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    aktiv: bool


class FuelEntryCreate(BaseModel):
    vehicle_id: int
    datum: datetime.date
    kilometerstand: int
    kraftstoffart: Kraftstoffart
    fuellmenge_liter: float
    preis_pro_liter: float
    gesamtpreis: float
    nicht_voll: bool = False
    tankstelle_name: str | None = None
    lat: float | None = None
    lon: float | None = None
    beleg_foto_pfad: str | None = None
    tacho_foto_pfad: str | None = None
    quelle: Quelle = Quelle.MANUELL
    ocr_rohtext: str | None = None
    ocr_konfidenz: float | None = None


class FuelEntryOut(FuelEntryCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    warnungen: list[str] = []


class OtherCostCreate(BaseModel):
    vehicle_id: int
    datum: datetime.date
    kategorie: Kostenkategorie
    betrag: float
    beschreibung: str | None = None
    jaehrlich_wiederkehrend: bool = False
    beleg_foto_pfad: str | None = None
    quelle: Quelle = Quelle.MANUELL


class OtherCostOut(OtherCostCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ReminderCreate(BaseModel):
    vehicle_id: int
    typ: ErinnerungsTyp
    beschreibung: str | None = None
    faellig_am: datetime.date | None = None
    faellig_km: int | None = None
    intervall_monate: int | None = None
    intervall_km: int | None = None


class ReminderOut(ReminderCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    erledigt: bool
    letzte_erledigung_am: datetime.date | None = None
    letzte_erledigung_km: int | None = None


class VehicleStats(BaseModel):
    """Kennzahlen analog zu den oberen Kopfzeilen der Excel-Tabelle
    (Ø-Verbrauch, Gesamtkosten, €/km, €/Monat, ...)."""

    vehicle_id: int
    zeitraum_von: datetime.date | None
    zeitraum_bis: datetime.date | None
    gefahrene_km: float
    gesamt_kraftstoffkosten: float
    gesamt_sonstige_kosten: float
    gesamtkosten: float
    ø_verbrauch_l_100km: float | None
    kosten_pro_km: float | None
    kosten_pro_monat: float | None
    anteil_lpg: float | None
    anteil_benzin: float | None
