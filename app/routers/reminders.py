import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import CurrentUser, accessible_vehicle_ids, get_accessible_vehicle, get_current_user
from app.db import get_db
from app.models import MaintenanceReminder
from app.reminder_notifications import (
    STAGE_FAELLIG,
    STAGE_VORAB,
    aktueller_kilometerstand,
    reminder_status,
    reset_markers,
)
from app.schemas import ReminderCreate, ReminderOut, ReminderStatusOut

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


@router.get("", response_model=list[ReminderOut])
def list_reminders(
    vehicle_id: int | None = None,
    nur_offene: bool = True,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    q = select(MaintenanceReminder).where(MaintenanceReminder.vehicle_id.in_(accessible_vehicle_ids(user)))
    if vehicle_id is not None:
        q = q.where(MaintenanceReminder.vehicle_id == vehicle_id)
    if nur_offene:
        q = q.where(MaintenanceReminder.erledigt.is_(False))
    return db.execute(q).scalars().all()


@router.get("/faellig", response_model=list[ReminderOut])
def list_due_reminders(
    innerhalb_tage: int = 30, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
):
    """Erinnerungen, die in den naechsten X Tagen faellig werden – Basis fuer
    die geplante Benachrichtigung ueber Nextcloud Notifications / den
    Talk-Bot (siehe app/talk_bot)."""
    grenze = datetime.date.today() + datetime.timedelta(days=innerhalb_tage)
    q = select(MaintenanceReminder).where(
        MaintenanceReminder.vehicle_id.in_(accessible_vehicle_ids(user)),
        MaintenanceReminder.erledigt.is_(False),
        MaintenanceReminder.faellig_am.is_not(None),
        MaintenanceReminder.faellig_am <= grenze,
    )
    return db.execute(q).scalars().all()


@router.post("", response_model=ReminderOut, status_code=201)
def create_reminder(
    payload: ReminderCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
):
    get_accessible_vehicle(db, payload.vehicle_id, user)
    reminder = MaintenanceReminder(**payload.model_dump())
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder


@router.post("/{reminder_id}/erledigt", response_model=ReminderOut)
def mark_done(
    reminder_id: int,
    km: int | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    reminder = db.get(MaintenanceReminder, reminder_id)
    if reminder is None:
        raise HTTPException(404, "Erinnerung nicht gefunden")
    get_accessible_vehicle(db, reminder.vehicle_id, user)
    if reminder.intervall_km and km is None:
        raise HTTPException(
            400,
            "Für diese Erinnerung ist ein Kilometer-Intervall hinterlegt - bitte den "
            "aktuellen Kilometerstand über den Query-Parameter 'km' angeben.",
        )

    reminder.letzte_erledigung_am = datetime.date.today()
    reminder.letzte_erledigung_km = km

    # Bei wiederkehrenden Intervallen direkt die naechste Faelligkeit anlegen,
    # sonst bleibt die Erinnerung endgueltig erledigt.
    wiederkehrend = False
    if reminder.intervall_monate:
        reminder.faellig_am = datetime.date.today() + datetime.timedelta(
            days=reminder.intervall_monate * 30.44
        )
        wiederkehrend = True
    if reminder.intervall_km and km is not None:
        reminder.faellig_km = km + reminder.intervall_km
        wiederkehrend = True
    reminder.erledigt = not wiederkehrend
    reset_markers(reminder)

    db.commit()
    db.refresh(reminder)
    return reminder


def _get_reminder(db: Session, reminder_id: int, user: CurrentUser) -> MaintenanceReminder:
    reminder = db.get(MaintenanceReminder, reminder_id)
    if reminder is None:
        raise HTTPException(404, "Erinnerung nicht gefunden")
    get_accessible_vehicle(db, reminder.vehicle_id, user)
    return reminder


@router.get("/status", response_model=list[ReminderStatusOut])
def list_reminders_with_status(
    vehicle_id: int | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Offene Erinnerungen mit berechnetem Status (faellig/bald) fuer die
    Oberflaeche - ohne vehicle_id ueber alle zugaenglichen Fahrzeuge."""
    q = (
        select(MaintenanceReminder)
        .where(
            MaintenanceReminder.vehicle_id.in_(accessible_vehicle_ids(user)),
            MaintenanceReminder.erledigt.is_(False),
        )
        .order_by(MaintenanceReminder.faellig_am.is_(None), MaintenanceReminder.faellig_am, MaintenanceReminder.id)
    )
    if vehicle_id is not None:
        q = q.where(MaintenanceReminder.vehicle_id == vehicle_id)
    today = datetime.date.today()
    km_cache: dict[int, int | None] = {}
    result = []
    for reminder in db.execute(q).scalars().all():
        if reminder.vehicle_id not in km_cache:
            km_cache[reminder.vehicle_id] = aktueller_kilometerstand(db, reminder.vehicle)
        km = km_cache[reminder.vehicle_id]
        status = reminder_status(reminder, km, today)
        result.append(
            ReminderStatusOut.model_validate(reminder).model_copy(
                update={
                    "status": {STAGE_FAELLIG: "faellig", STAGE_VORAB: "bald"}.get(status.stage),
                    "rest_tage": status.rest_tage,
                    "rest_km": status.rest_km,
                    "aktueller_km": km,
                }
            )
        )
    return result


@router.put("/{reminder_id}", response_model=ReminderOut)
def update_reminder(
    reminder_id: int,
    payload: ReminderCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    reminder = _get_reminder(db, reminder_id, user)
    get_accessible_vehicle(db, payload.vehicle_id, user)
    for key, value in payload.model_dump().items():
        setattr(reminder, key, value)
    reset_markers(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder


@router.delete("/{reminder_id}", status_code=204)
def delete_reminder(reminder_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    reminder = _get_reminder(db, reminder_id, user)
    db.delete(reminder)
    db.commit()
