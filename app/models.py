"""
SQLAlchemy-Modelle, abgeleitet aus der Struktur der bisherigen Excel-Datei
(Kraftstoffkosten LPG/Benzin, Gesamtstatistik, Sonstige Kosten) plus den
zusaetzlich besprochenen Erweiterungen (Standort, Fotos, Erinnerungen).
"""
from __future__ import annotations

import datetime
import enum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Kraftstoffart(str, enum.Enum):
    LPG = "LPG"
    BENZIN = "Benzin"
    DIESEL = "Diesel"
    STROM = "Strom"


class Kostenkategorie(str, enum.Enum):
    VERSICHERUNG = "Versicherung"
    STEUER = "Steuer"
    FINANZIERUNG = "Finanzierung"
    REIFEN_TEILE = "Reifen/Teile"
    SERVICE_TUEV = "Service/TÜV"
    WASCHEN = "Waschen"
    EINMALIG = "Einmalig"        # z.B. Kauf, Zulassung, Zubehoer
    EINNAHME = "Einnahme"        # z.B. Weiterverkauf einzelner Teile
    SONSTIGES = "Sonstiges"


class ErinnerungsTyp(str, enum.Enum):
    TUEV_HU = "TÜV/HU"
    VERSICHERUNG_FAELLIG = "Versicherung fällig"
    STEUER_FAELLIG = "Steuer fällig"
    SERVICE = "Service/Inspektion"
    REIFENWECHSEL = "Reifenwechsel"
    SONSTIGES = "Sonstiges"


class Quelle(str, enum.Enum):
    MANUELL = "manuell"
    CHAT_BOT = "chat-bot"


class Fahrtzweck(str, enum.Enum):
    PRIVAT = "Privat"
    DIENSTLICH = "Dienstlich"
    ARBEITSWEG = "Arbeitsweg"


class Vehicle(Base):
    """Entspricht den Stammdaten oben in jedem Excel-Tabellenblatt
    (Amtl. Kennzeichen, Hersteller, Modell, Variante, Tankvolumen, ...)."""

    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kennzeichen: Mapped[str] = mapped_column(String(20), unique=True)
    hersteller: Mapped[str] = mapped_column(String(100))
    modell: Mapped[str] = mapped_column(String(100))
    variante: Mapped[str | None] = mapped_column(String(200), nullable=True)

    tankvolumen_lpg_l: Mapped[float | None] = mapped_column(Float, nullable=True)
    tankvolumen_benzin_l: Mapped[float | None] = mapped_column(Float, nullable=True)

    kaufdatum: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    kaufpreis: Mapped[float | None] = mapped_column(Float, nullable=True)
    kaufkilometerstand: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verkauft_am: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)

    # Zuordnung fuer den Talk-Bot: z.B. Codewort "previa" oder feste Raum-ID,
    # damit ankommende Fotos automatisch dem richtigen Fahrzeug zugeordnet werden.
    bot_codewort: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True)

    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)
    erstellt_am: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    fuel_entries: Mapped[list["FuelEntry"]] = relationship(back_populates="vehicle")
    other_costs: Mapped[list["OtherCost"]] = relationship(back_populates="vehicle")
    reminders: Mapped[list["MaintenanceReminder"]] = relationship(back_populates="vehicle")
    logbook_entries: Mapped[list["LogbookEntry"]] = relationship(back_populates="vehicle")
    trips: Mapped[list["Trip"]] = relationship(back_populates="vehicle")


class FuelEntry(Base):
    """Entspricht einer Zeile aus 'Kraftstoffkosten LPG' bzw.
    'Kraftstoffkosten Benzin' (Datum, Kilometerstand, Füllmenge,
    Preis/Liter, Gesamtpreis, nicht voll, ...)."""

    __tablename__ = "fuel_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))

    datum: Mapped[datetime.date] = mapped_column(Date)
    kilometerstand: Mapped[int] = mapped_column(Integer)
    kraftstoffart: Mapped[Kraftstoffart] = mapped_column(Enum(Kraftstoffart))

    fuellmenge_liter: Mapped[float] = mapped_column(Float)
    preis_pro_liter: Mapped[float] = mapped_column(Float)
    gesamtpreis: Mapped[float] = mapped_column(Float)
    nicht_voll: Mapped[bool] = mapped_column(Boolean, default=False)

    tankstelle_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)

    beleg_foto_pfad: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tacho_foto_pfad: Mapped[str | None] = mapped_column(String(500), nullable=True)

    quelle: Mapped[Quelle] = mapped_column(Enum(Quelle), default=Quelle.MANUELL)
    ocr_rohtext: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_konfidenz: Mapped[float | None] = mapped_column(Float, nullable=True)

    erstellt_am: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    vehicle: Mapped["Vehicle"] = relationship(back_populates="fuel_entries")


class OtherCost(Base):
    """Entspricht einer Zeile aus 'Sonstige Kosten' (Versicherung, Steuer,
    Finanzierung, Reifen/Teile, Service/TÜV, Waschen, Einmalkosten)."""

    __tablename__ = "other_costs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))

    datum: Mapped[datetime.date] = mapped_column(Date)
    kategorie: Mapped[Kostenkategorie] = mapped_column(Enum(Kostenkategorie))
    betrag: Mapped[float] = mapped_column(Float)
    beschreibung: Mapped[str | None] = mapped_column(String(300), nullable=True)
    jaehrlich_wiederkehrend: Mapped[bool] = mapped_column(Boolean, default=False)

    beleg_foto_pfad: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quelle: Mapped[Quelle] = mapped_column(Enum(Quelle), default=Quelle.MANUELL)

    erstellt_am: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    vehicle: Mapped["Vehicle"] = relationship(back_populates="other_costs")


class MaintenanceReminder(Base):
    """Neu gegenueber der Excel-Datei: aktive Erinnerungen statt reiner
    Ruecksschau. Faelligkeit entweder nach Datum, nach Kilometerstand,
    oder als wiederkehrendes Intervall."""

    __tablename__ = "maintenance_reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))

    typ: Mapped[ErinnerungsTyp] = mapped_column(Enum(ErinnerungsTyp))
    beschreibung: Mapped[str | None] = mapped_column(String(300), nullable=True)

    faellig_am: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    faellig_km: Mapped[int | None] = mapped_column(Integer, nullable=True)

    intervall_monate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intervall_km: Mapped[int | None] = mapped_column(Integer, nullable=True)

    erledigt: Mapped[bool] = mapped_column(Boolean, default=False)
    letzte_erledigung_am: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    letzte_erledigung_km: Mapped[int | None] = mapped_column(Integer, nullable=True)

    vehicle: Mapped["Vehicle"] = relationship(back_populates="reminders")


class LogbookEntry(Base):
    """Wartungs-/Ereignislogbuch (digitales Serviceheft): was wann bei
    welchem Kilometerstand am Fahrzeug gemacht wurde."""

    __tablename__ = "logbook_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))

    datum: Mapped[datetime.date] = mapped_column(Date)
    kilometerstand: Mapped[int | None] = mapped_column(Integer, nullable=True)
    eintrag: Mapped[str] = mapped_column(String(300))
    notiz: Mapped[str | None] = mapped_column(Text, nullable=True)

    erstellt_am: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    vehicle: Mapped["Vehicle"] = relationship(back_populates="logbook_entries")


class Trip(Base):
    """Eine Fahrt im Fahrtenbuch. Nicht als steuerlich anerkanntes
    elektronisches Fahrtenbuch gedacht - Eintraege sind nachtraeglich
    aenderbar/loeschbar."""

    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))

    datum: Mapped[datetime.date] = mapped_column(Date)
    start: Mapped[str] = mapped_column(String(200))
    ziel: Mapped[str] = mapped_column(String(200))
    km_start: Mapped[int] = mapped_column(Integer)
    km_ende: Mapped[int] = mapped_column(Integer)
    zweck: Mapped[Fahrtzweck] = mapped_column(Enum(Fahrtzweck), default=Fahrtzweck.PRIVAT)
    notiz: Mapped[str | None] = mapped_column(Text, nullable=True)

    erstellt_am: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    vehicle: Mapped["Vehicle"] = relationship(back_populates="trips")
