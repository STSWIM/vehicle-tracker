"""Pydantic-Schemas fuer die REST-API (Request/Response-Modelle)."""
from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import ErinnerungsTyp, Fahrtzweck, Kostenkategorie, Kraftstoffart, Quelle


class VehicleCreate(BaseModel):
    kennzeichen: str
    hersteller: str
    modell: str
    variante: str | None = None
    tankvolumen_lpg_l: float | None = None
    tankvolumen_benzin_l: float | None = None
    kaufdatum: datetime.date | None = None
    kaufpreis: float | None = None
    kaufkilometerstand: int | None = Field(default=None, ge=0)
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


class LogbookEntryCreate(BaseModel):
    vehicle_id: int
    datum: datetime.date
    kilometerstand: int | None = Field(default=None, ge=0)
    eintrag: str = Field(min_length=1, max_length=300)
    notiz: str | None = None


class LogbookEntryOut(LogbookEntryCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class TripCreate(BaseModel):
    vehicle_id: int
    datum: datetime.date
    start: str = Field(min_length=1, max_length=200)
    ziel: str = Field(min_length=1, max_length=200)
    km_start: int = Field(ge=0)
    km_ende: int = Field(ge=0)
    zweck: Fahrtzweck = Fahrtzweck.PRIVAT
    notiz: str | None = None

    @model_validator(mode="after")
    def _km_ende_nicht_vor_start(self) -> TripCreate:
        if self.km_ende < self.km_start:
            raise ValueError("km-Stand am Ende darf nicht kleiner sein als am Start")
        return self


class TripOut(TripCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class VehicleStats(BaseModel):
    """Kennzahlen analog zu den oberen Kopfzeilen der Excel-Tabelle
    (Ø-Verbrauch, Gesamtkosten, €/km, €/Monat, ...).

    gesamt_sonstige_kosten sind die laufenden Kosten ohne Kategorie
    "Einmalig"; diese zaehlt zusammen mit dem Kaufpreis zu
    anschaffungskosten, die nur bei mit_anschaffung in gesamtkosten stecken.
    """

    vehicle_id: int
    zeitraum_von: datetime.date | None
    zeitraum_bis: datetime.date | None
    mit_anschaffung: bool
    gefahrene_km: float
    gesamt_kraftstoffkosten: float
    gesamt_sonstige_kosten: float
    anschaffungskosten: float
    kosten_nach_kategorie: dict[str, float]
    gesamtkosten: float
    ø_verbrauch_l_100km: float | None
    kosten_pro_km: float | None
    kosten_pro_monat: float | None
    anteil_lpg: float | None
    anteil_benzin: float | None
