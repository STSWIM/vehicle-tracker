import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import MaintenanceReminder
from app.schemas import ReminderCreate, ReminderOut

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


@router.get("", response_model=list[ReminderOut])
def list_reminders(
    vehicle_id: int | None = None,
    nur_offene: bool = True,
    db: Session = Depends(get_db),
):
    q = select(MaintenanceReminder)
    if vehicle_id is not None:
        q = q.where(MaintenanceReminder.vehicle_id == vehicle_id)
    if nur_offene:
        q = q.where(MaintenanceReminder.erledigt.is_(False))
    return db.execute(q).scalars().all()


@router.get("/faellig", response_model=list[ReminderOut])
def list_due_reminders(innerhalb_tage: int = 30, db: Session = Depends(get_db)):
    """Erinnerungen, die in den naechsten X Tagen faellig werden – Basis fuer
    die geplante Benachrichtigung ueber Nextcloud Notifications / den
    Talk-Bot (siehe app/talk_bot)."""
    grenze = datetime.date.today() + datetime.timedelta(days=innerhalb_tage)
    q = select(MaintenanceReminder).where(
        MaintenanceReminder.erledigt.is_(False),
        MaintenanceReminder.faellig_am.is_not(None),
        MaintenanceReminder.faellig_am <= grenze,
    )
    return db.execute(q).scalars().all()


@router.post("", response_model=ReminderOut, status_code=201)
def create_reminder(payload: ReminderCreate, db: Session = Depends(get_db)):
    reminder = MaintenanceReminder(**payload.model_dump())
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder


@router.post("/{reminder_id}/erledigt", response_model=ReminderOut)
def mark_done(reminder_id: int, km: int | None = None, db: Session = Depends(get_db)):
    reminder = db.get(MaintenanceReminder, reminder_id)
    if reminder is None:
        raise HTTPException(404, "Erinnerung nicht gefunden")
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

    db.commit()
    db.refresh(reminder)
    return reminder
