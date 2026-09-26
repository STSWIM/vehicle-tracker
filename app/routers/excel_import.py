"""
Import historischer Daten aus der bisherigen Excel-Buchfuehrung (Issue #16).

POST /api/vehicles/{id}/import/excel?dry_run=true liefert nur die Vorschau
(neu vs. Duplikat, Hinweise), mit dry_run=false wird alles in einer
Transaktion gespeichert.

Die km-Plausibilitaetspruefung der Einzelerfassung (app/validation.py) passt
nicht fuer den Massenimport: sie prueft jede Tankung gegen den bisherigen
DB-Stand, waehrend beim Import ganze Historien auf einmal kommen. Stattdessen
wird hier der Gesamtbestand (vorhandene + neue Tankungen) chronologisch
geprueft - sinkt der km-Stand irgendwo, wird der Import abgelehnt.
"""
from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import CurrentUser, get_accessible_vehicle, get_current_user
from app.db import get_db
from app.excel_import import (
    ExcelImportError,
    ImportFuelEntry,
    ImportOtherCost,
    km_ausreisser,
    km_konflikte,
    parse_workbook,
)
from app.models import FuelEntry, Kostenkategorie, Kraftstoffart, OtherCost, Quelle, Vehicle

router = APIRouter(prefix="/api/vehicles", tags=["excel-import"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
BETRAG_TOLERANZ = 0.01


class ImportFuelRow(BaseModel):
    datum: datetime.date
    kilometerstand: int
    kraftstoffart: Kraftstoffart
    fuellmenge_liter: float
    preis_pro_liter: float
    gesamtpreis: float
    nicht_voll: bool
    quelle: str
    duplikat: bool
    # Grund, falls die Zeile wegen eines unpassenden km-Stands nicht
    # uebernommen wird (vermutlich Tippfehler in der Excel)
    uebersprungen: str | None = None


class ImportCostRow(BaseModel):
    datum: datetime.date
    kategorie: Kostenkategorie
    betrag: float
    beschreibung: str | None
    jaehrlich_wiederkehrend: bool
    quelle: str
    duplikat: bool


class ImportKauf(BaseModel):
    kaufdatum: datetime.date | None
    kaufpreis: float | None
    kaufkilometerstand: int | None
    quelle: str | None
    # Felder, die (bei dry_run: wuerden) uebernommen, weil am Fahrzeug leer
    uebernommen: list[str]


class ImportResult(BaseModel):
    dry_run: bool
    tankungen_neu: int
    tankungen_duplikate: int
    tankungen_uebersprungen: int = 0
    kosten_neu: int
    kosten_duplikate: int
    tankungen: list[ImportFuelRow]
    kosten: list[ImportCostRow]
    kauf: ImportKauf | None
    warnungen: list[str]


def _ist_tank_duplikat(neu: ImportFuelEntry, vorhandene: list[FuelEntry]) -> bool:
    for e in vorhandene:
        if e.datum != neu.datum:
            continue
        # Gleicher Tag + km reicht nur je Kraftstoff: bivalente Fahrzeuge
        # tanken oft LPG und Benzin beim selben Stopp.
        if e.kilometerstand == neu.kilometerstand and e.kraftstoffart == neu.kraftstoffart:
            return True
        if abs(e.gesamtpreis - neu.gesamtpreis) <= BETRAG_TOLERANZ + 1e-9:
            return True
    return False


def _ist_kosten_duplikat(neu: ImportOtherCost, vorhandene: list[OtherCost]) -> bool:
    return any(
        c.datum == neu.datum and c.kategorie == neu.kategorie and abs(c.betrag - neu.betrag) <= BETRAG_TOLERANZ + 1e-9
        for c in vorhandene
    )


def _read_upload(file: UploadFile) -> bytes:
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Datei zu groß (maximal {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).")
    if not data:
        raise HTTPException(400, "Leere Datei.")
    return data


@router.post("/{vehicle_id}/import/excel", response_model=ImportResult)
def import_excel(
    vehicle_id: int,
    dry_run_query: bool | None = Query(None, alias="dry_run"),
    # Der AppAPI-Proxy verwirft bei multipart-Uploads die Query-Parameter,
    # deshalb schickt das Frontend dry_run als Formularfeld mit.
    dry_run_form: bool | None = Form(None, alias="dry_run"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> ImportResult:
    dry_run = next((v for v in (dry_run_form, dry_run_query) if v is not None), True)
    vehicle: Vehicle = get_accessible_vehicle(db, vehicle_id, user)
    try:
        preview = parse_workbook(_read_upload(file))
    except ExcelImportError as exc:
        raise HTTPException(400, str(exc)) from exc

    vorhandene_tankungen = db.execute(select(FuelEntry).where(FuelEntry.vehicle_id == vehicle_id)).scalars().all()
    vorhandene_kosten = db.execute(select(OtherCost).where(OtherCost.vehicle_id == vehicle_id)).scalars().all()

    tank_rows = [
        ImportFuelRow(**vars(e), duplikat=_ist_tank_duplikat(e, vorhandene_tankungen)) for e in preview.fuel_entries
    ]
    cost_rows = [
        ImportCostRow(**vars(c), duplikat=_ist_kosten_duplikat(c, vorhandene_kosten)) for c in preview.other_costs
    ]
    neue_tankungen = [r for r in tank_rows if not r.duplikat]
    neue_kosten = [r for r in cost_rows if not r.duplikat]

    # Kaufdaten nur in leere Fahrzeugfelder uebernehmen
    kauf = None
    kauf_updates: dict[str, object] = {}
    if preview.kauf is not None:
        k = preview.kauf
        if vehicle.kaufpreis is None and k.kaufpreis is not None:
            kauf_updates["kaufpreis"] = k.kaufpreis
        if vehicle.kaufdatum is None and k.kaufdatum is not None:
            kauf_updates["kaufdatum"] = k.kaufdatum
        alle_km = [e.kilometerstand for e in vorhandene_tankungen] + [r.kilometerstand for r in neue_tankungen]
        if (
            vehicle.kaufkilometerstand is None
            and k.kaufkilometerstand is not None
            and (not alle_km or k.kaufkilometerstand <= min(alle_km))
        ):
            kauf_updates["kaufkilometerstand"] = k.kaufkilometerstand
        kauf = ImportKauf(
            kaufdatum=k.kaufdatum,
            kaufpreis=k.kaufpreis,
            kaufkilometerstand=k.kaufkilometerstand,
            quelle=k.quelle,
            uebernommen=sorted(kauf_updates),
        )

    # km-Staende: Gesamtbestand chronologisch pruefen (statt Einzelpruefung).
    # Einzelne Ausreisser (Tippfehler) werden uebersprungen; passt dagegen ein
    # groesserer Teil nicht, stimmt vermutlich grundsaetzlich etwas nicht und
    # der Import wird wie bisher abgelehnt.
    warnungen = list(preview.warnungen)
    kauf_km = kauf_updates.get("kaufkilometerstand", vehicle.kaufkilometerstand)
    for r in neue_tankungen:
        if kauf_km is not None and r.kilometerstand < kauf_km:
            r.uebersprungen = f"liegt unter dem km-Stand beim Kauf ({kauf_km:,} km)".replace(",", ".")
    kandidaten = [r for r in neue_tankungen if r.uebersprungen is None]
    punkte = [(e.datum, e.kilometerstand, False) for e in vorhandene_tankungen]
    punkte += [(r.datum, r.kilometerstand, True) for r in kandidaten]
    for index in km_ausreisser(punkte):
        kandidaten[index - len(vorhandene_tankungen)].uebersprungen = "passt nicht zu den übrigen Kilometerständen"
    uebersprungen = [r for r in neue_tankungen if r.uebersprungen]
    if len(uebersprungen) > max(2, len(neue_tankungen) // 10):
        rest = [r for r in neue_tankungen if not r.uebersprungen]
        punkte = [(e.datum, e.kilometerstand, f"Tankung vom {e.datum:%d.%m.%Y}", False) for e in vorhandene_tankungen]
        punkte += [(r.datum, r.kilometerstand, r.quelle, True) for r in rest + uebersprungen]
        fehler = km_konflikte(punkte) or [f"{r.quelle}: {r.uebersprungen}." for r in uebersprungen[:5]]
        raise HTTPException(400, "Kilometerstände sinken – Import abgelehnt. " + " ".join(fehler))
    for r in uebersprungen:
        warnungen.append(
            f"Übersprungen – {r.quelle}: {r.kilometerstand:,} km am {r.datum:%d.%m.%Y} {r.uebersprungen} "
            "(Tippfehler?). Bitte nach dem Import korrigiert von Hand erfassen.".replace(",", ".")
        )
    neue_tankungen = [r for r in neue_tankungen if not r.uebersprungen]

    if not dry_run:
        try:
            for r in neue_tankungen:
                db.add(
                    FuelEntry(
                        vehicle_id=vehicle_id,
                        **r.model_dump(exclude={"quelle", "duplikat", "uebersprungen"}),
                        quelle=Quelle.MANUELL,
                        erfasst_von=user.uid,
                    )
                )
            for r in neue_kosten:
                db.add(
                    OtherCost(
                        vehicle_id=vehicle_id,
                        **r.model_dump(exclude={"quelle", "duplikat"}),
                        quelle=Quelle.MANUELL,
                        erfasst_von=user.uid,
                    )
                )
            for key, value in kauf_updates.items():
                setattr(vehicle, key, value)
            db.commit()
        except Exception:
            db.rollback()
            raise

    return ImportResult(
        dry_run=dry_run,
        tankungen_neu=len(neue_tankungen),
        tankungen_duplikate=sum(r.duplikat for r in tank_rows),
        tankungen_uebersprungen=len(uebersprungen),
        kosten_neu=len(neue_kosten),
        kosten_duplikate=len(cost_rows) - len(neue_kosten),
        tankungen=tank_rows,
        kosten=cost_rows,
        kauf=kauf,
        warnungen=warnungen,
    )
