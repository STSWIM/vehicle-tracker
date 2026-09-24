from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import LogbookEntry, Vehicle
from app.schemas import LogbookEntryCreate, LogbookEntryOut

router = APIRouter(prefix="/api/logbook", tags=["logbook"])


@router.get("", response_model=list[LogbookEntryOut])
def list_logbook_entries(vehicle_id: int | None = None, db: Session = Depends(get_db)):
    q = select(LogbookEntry).order_by(LogbookEntry.datum.desc(), LogbookEntry.id.desc())
    if vehicle_id is not None:
        q = q.where(LogbookEntry.vehicle_id == vehicle_id)
    return db.execute(q).scalars().all()


@router.post("", response_model=LogbookEntryOut, status_code=201)
def create_logbook_entry(payload: LogbookEntryCreate, db: Session = Depends(get_db)):
    if db.get(Vehicle, payload.vehicle_id) is None:
        raise HTTPException(404, "Fahrzeug nicht gefunden")
    entry = LogbookEntry(**payload.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
def delete_logbook_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(LogbookEntry, entry_id)
    if entry is None:
        raise HTTPException(404, "Eintrag nicht gefunden")
    db.delete(entry)
    db.commit()
