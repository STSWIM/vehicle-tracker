from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import CurrentUser, accessible_vehicle_ids, get_accessible_vehicle, get_current_user
from app.db import get_db
from app.models import FuelEntry
from app.schemas import FuelEntryCreate, FuelEntryOut
from app.validation import KilometerstandUnplausibelError, pruefe_kilometerstand, pruefe_verbrauch

router = APIRouter(prefix="/api/fuel-entries", tags=["fuel-entries"])


@router.get("", response_model=list[FuelEntryOut])
def list_fuel_entries(
    vehicle_id: int | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    q = select(FuelEntry).where(FuelEntry.vehicle_id.in_(accessible_vehicle_ids(user))).order_by(FuelEntry.datum)
    if vehicle_id is not None:
        q = q.where(FuelEntry.vehicle_id == vehicle_id)
    return db.execute(q).scalars().all()


@router.post("", response_model=FuelEntryOut, status_code=201)
def create_fuel_entry(
    payload: FuelEntryCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
):
    get_accessible_vehicle(db, payload.vehicle_id, user)
    try:
        pruefe_kilometerstand(db, payload.vehicle_id, payload.datum, payload.kilometerstand)
    except KilometerstandUnplausibelError as exc:
        raise HTTPException(400, str(exc)) from exc

    entry = FuelEntry(**payload.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    entry.warnungen = pruefe_verbrauch(db, entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
def delete_fuel_entry(entry_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    entry = db.get(FuelEntry, entry_id)
    if entry is None:
        raise HTTPException(404, "Eintrag nicht gefunden")
    get_accessible_vehicle(db, entry.vehicle_id, user)
    db.delete(entry)
    db.commit()
