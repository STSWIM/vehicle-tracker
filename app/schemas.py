"""Pydantic-Schemas fuer die REST-API (Request/Response-Modelle)."""
from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import ErinnerungsTyp, Fahrtzweck, Kostenkategorie, Kraftstoffart, Quelle, ShareType


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
    bei_kauf_vollgetankt: bool = False
    bot_codewort: str | None = None


class ShareIn(BaseModel):
    share_type: ShareType
    share_with: str = Field(min_length=1, max_length=255)


class ShareOut(ShareIn):
    model_config = ConfigDict(from_attributes=True)


class VehicleOut(VehicleCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    aktiv: bool
    owner: str | None = None
    shares: list[ShareOut] = []

    @field_validator("bei_kauf_vollgetankt", mode="before")
    @classmethod
    def _none_als_false(cls, value: bool | None) -> bool:
        # Spalte ist nullable, weil sie per add_missing_columns nachgezogen wird.
        return bool(value)


class CurrentUserOut(BaseModel):
    uid: str
    standalone: bool


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
    faellig_km: int | None = Field(default=None, ge=0)
    intervall_monate: int | None = Field(default=None, ge=1)
    intervall_km: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _irgendeine_faelligkeit(self) -> ReminderCreate:
        if not any((self.faellig_am, self.faellig_km, self.intervall_monate, self.intervall_km)):
            raise ValueError("Bitte ein Fälligkeitsdatum, einen km-Stand oder ein Intervall angeben")
        return self


class ReminderOut(ReminderCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    erledigt: bool
    letzte_erledigung_am: datetime.date | None = None
    letzte_erledigung_km: int | None = None


class ReminderStatusOut(ReminderOut):
    """Erinnerung plus berechneter Faelligkeitsstatus fuer die Oberflaeche
    (siehe app/reminder_notifications.reminder_status)."""

    # "faellig" (ueberfaellig/heute), "bald" (innerhalb des Vorwarnfensters) oder None
    status: str | None = None
    rest_tage: int | None = None
    rest_km: int | None = None
    aktueller_km: int | None = None


class LogbookEntryCreate(BaseModel):
    vehicle_id: int
    datum: datetime.date
    kilometerstand: int | None = Field(default=None, ge=0)
    eintrag: str = Field(min_length=1, max_length=300)
    notiz: str | None = None


class LogbookEntryOut(LogbookEntryCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    warnungen: list[str] = []


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
    warnungen: list[str] = []


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
    # Voll-zu-Voll je Kraftstoff (bivalente Fahrzeuge wie LPG+Benzin getrennt);
    # ø_verbrauch_l_100km nur gesetzt, wenn genau ein Kraftstoff einen Wert hat.
    verbrauch_nach_kraftstoff: dict[str, float]
    ø_verbrauch_l_100km: float | None
    kosten_pro_km: float | None
    kosten_pro_monat: float | None
    anteil_lpg: float | None
    anteil_benzin: float | None
    # offene Tankluecke (letzter bekannter km-Stand vs. letzte Tankung), s. Issue #12
    hinweise: list[str] = []
