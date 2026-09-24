from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import CurrentUser, accessible_vehicle_ids, get_accessible_vehicle, get_current_user
from app.db import get_db
from app.models import LogbookEntry
from app.schemas import LogbookEntryCreate, LogbookEntryOut

router = APIRouter(prefix="/api/logbook", tags=["logbook"])


@router.get("", response_model=list[LogbookEntryOut])
def list_logbook_entries(
    vehicle_id: int | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    q = (
        select(LogbookEntry)
        .where(LogbookEntry.vehicle_id.in_(accessible_vehicle_ids(user)))
        .order_by(LogbookEntry.datum.desc(), LogbookEntry.id.desc())
    )
    if vehicle_id is not None:
        q = q.where(LogbookEntry.vehicle_id == vehicle_id)
    return db.execute(q).scalars().all()


@router.post("", response_model=LogbookEntryOut, status_code=201)
def create_logbook_entry(
    payload: LogbookEntryCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
):
    get_accessible_vehicle(db, payload.vehicle_id, user)
    entry = LogbookEntry(**payload.model_dump(), erfasst_von=user.uid)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
def delete_logbook_entry(
    entry_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
):
    entry = db.get(LogbookEntry, entry_id)
    if entry is None:
        raise HTTPException(404, "Eintrag nicht gefunden")
    get_accessible_vehicle(db, entry.vehicle_id, user)
    db.delete(entry)
    db.commit()
