"""
Faelligkeit von Wartungserinnerungen und Nextcloud-Benachrichtigungen.

Zweigeteilt, damit die Auswahl-Logik ohne Nextcloud testbar bleibt:

- reine Funktionen (aktueller_kilometerstand, reminder_status,
  due_notifications, mark_notified) arbeiten nur auf der Datenbank;
- send_due_notifications / notification_loop sind der duenne asynchrone
  Teil, der im ExApp-Modus einmal taeglich ueber nc_py_api als der jeweilige
  Fahrzeug-Besitzer eine Benachrichtigung anlegt (nie im Standalone-Modus).

Gegen Spam gibt es je Erinnerung hoechstens zwei Benachrichtigungen: eine
beim Eintritt ins Vorwarnfenster (VORWARN_TAGE bzw. VORWARN_KM) und eine
bei Faelligkeit. Die Marker dafuer (benachrichtigt_vorab_am,
benachrichtigt_faellig_am) setzt erst das erfolgreiche Senden; Bearbeiten
oder Erledigen der Erinnerung setzt sie zurueck.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import os
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ErinnerungsTyp, FuelEntry, LogbookEntry, MaintenanceReminder, Trip, Vehicle

LOGGER = logging.getLogger(__name__)

VORWARN_TAGE = 14
VORWARN_KM = 500

STAGE_VORAB = "vorab"
STAGE_FAELLIG = "faellig"

APP_ID = "vehicle_tracker"
# Route der AppAPI fuer Top-Menue-Eintraege: /embedded/{appId}/{name}, hier
# der in main.py registrierte Eintrag "ui".
UI_PATH = f"/index.php/apps/app_api/embedded/{APP_ID}/ui"

ERSTER_LAUF_NACH_S = 120
INTERVALL_S = 24 * 60 * 60


def aktueller_kilometerstand(db: Session, vehicle: Vehicle) -> int | None:
    """Hoechster bekannter km-Stand aus Tankungen, Fahrten, Logbuch und Kauf."""
    werte = [
        db.execute(select(func.max(FuelEntry.kilometerstand)).where(FuelEntry.vehicle_id == vehicle.id)).scalar_one(),
        db.execute(select(func.max(Trip.km_ende)).where(Trip.vehicle_id == vehicle.id)).scalar_one(),
        db.execute(
            select(func.max(LogbookEntry.kilometerstand)).where(LogbookEntry.vehicle_id == vehicle.id)
        ).scalar_one(),
        vehicle.kaufkilometerstand,
    ]
    werte = [w for w in werte if w is not None]
    return max(werte) if werte else None


@dataclass(frozen=True)
class ReminderStatus:
    stage: str | None  # STAGE_FAELLIG, STAGE_VORAB oder None
    datum_faellig: bool = False  # faellig_am erreicht/ueberschritten
    datum_bald: bool = False
    km_faellig: bool = False  # faellig_km erreicht/ueberschritten
    km_bald: bool = False
    rest_tage: int | None = None
    rest_km: int | None = None


def reminder_status(reminder: MaintenanceReminder, aktueller_km: int | None, today: datetime.date) -> ReminderStatus:
    rest_tage = (reminder.faellig_am - today).days if reminder.faellig_am else None
    rest_km = reminder.faellig_km - aktueller_km if reminder.faellig_km is not None and aktueller_km is not None else None

    datum_faellig = rest_tage is not None and rest_tage <= 0
    datum_bald = rest_tage is not None and 0 < rest_tage <= VORWARN_TAGE
    km_faellig = rest_km is not None and rest_km <= 0
    km_bald = rest_km is not None and 0 < rest_km <= VORWARN_KM

    if reminder.erledigt:
        stage = None
    elif datum_faellig or km_faellig:
        stage = STAGE_FAELLIG
    elif datum_bald or km_bald:
        stage = STAGE_VORAB
    else:
        stage = None
    return ReminderStatus(stage, datum_faellig, datum_bald, km_faellig, km_bald, rest_tage, rest_km)


@dataclass(frozen=True)
class DueNotification:
    owner: str
    subject: str
    message: str
    reminder_id: int
    stage: str


def _datum(d: datetime.date) -> str:
    return d.strftime("%d.%m.%Y")


def _km(value: int) -> str:
    return f"{value:,}".replace(",", ".") + " km"


def _bezeichnung(reminder: MaintenanceReminder) -> str:
    if reminder.typ == ErinnerungsTyp.SONSTIGES and reminder.beschreibung:
        return reminder.beschreibung
    return reminder.typ.value


def _texte(
    reminder: MaintenanceReminder, vehicle: Vehicle, status: ReminderStatus, aktueller_km: int | None, today: datetime.date
) -> tuple[str, str]:
    wer = f"{_bezeichnung(reminder)} für {vehicle.kennzeichen}"
    if status.datum_faellig:
        subject = f"{wer} heute fällig" if reminder.faellig_am == today else f"{wer} überfällig seit {_datum(reminder.faellig_am)}"
    elif status.km_faellig:
        subject = f"{wer} fällig: {_km(reminder.faellig_km)} erreicht"
    elif status.datum_bald:
        subject = f"{wer} fällig am {_datum(reminder.faellig_am)}"
    else:
        subject = f"{wer} fällig bei {_km(reminder.faellig_km)}"

    teile = []
    if reminder.beschreibung and reminder.beschreibung != _bezeichnung(reminder):
        teile.append(reminder.beschreibung)
    if reminder.faellig_am and not (status.datum_faellig or status.datum_bald):
        teile.append(f"Fällig am {_datum(reminder.faellig_am)}.")
    if reminder.faellig_km is not None and aktueller_km is not None:
        if status.rest_km is not None and status.rest_km > 0:
            teile.append(f"Fällig bei {_km(reminder.faellig_km)}, aktuell {_km(aktueller_km)} (noch {_km(status.rest_km)}).")
        else:
            teile.append(f"Fällig bei {_km(reminder.faellig_km)}, aktuell {_km(aktueller_km)}.")
    teile.append("Nach Erledigung in der Fahrzeug Buchführung als erledigt markieren.")
    return subject, " ".join(teile)


def due_notifications(db: Session, today: datetime.date) -> list[DueNotification]:
    """Welche Benachrichtigungen heute faellig sind - ohne etwas zu aendern.
    Nur an den Fahrzeug-Besitzer; Fahrzeuge ohne Besitzer und deaktivierte
    Fahrzeuge werden uebersprungen."""
    rows = db.execute(
        select(MaintenanceReminder, Vehicle)
        .join(Vehicle, MaintenanceReminder.vehicle_id == Vehicle.id)
        .where(
            MaintenanceReminder.erledigt.is_(False),
            Vehicle.owner.is_not(None),
            Vehicle.aktiv.is_(True),
        )
        .order_by(MaintenanceReminder.id)
    ).all()

    km_cache: dict[int, int | None] = {}
    result = []
    for reminder, vehicle in rows:
        if vehicle.id not in km_cache:
            km_cache[vehicle.id] = aktueller_kilometerstand(db, vehicle)
        aktueller_km = km_cache[vehicle.id]
        status = reminder_status(reminder, aktueller_km, today)
        if status.stage == STAGE_FAELLIG and reminder.benachrichtigt_faellig_am is None:
            stage = STAGE_FAELLIG
        elif status.stage == STAGE_VORAB and reminder.benachrichtigt_vorab_am is None:
            stage = STAGE_VORAB
        else:
            continue
        subject, message = _texte(reminder, vehicle, status, aktueller_km, today)
        result.append(DueNotification(vehicle.owner, subject, message, reminder.id, stage))
    return result


def mark_notified(db: Session, reminder_id: int, stage: str, today: datetime.date) -> None:
    reminder = db.get(MaintenanceReminder, reminder_id)
    if reminder is None:
        return
    if stage == STAGE_FAELLIG:
        reminder.benachrichtigt_faellig_am = today
        # direkt faellig angelegt: keine nachtraegliche Vorab-Meldung
        reminder.benachrichtigt_vorab_am = reminder.benachrichtigt_vorab_am or today
    else:
        reminder.benachrichtigt_vorab_am = today
    db.commit()


def reset_markers(reminder: MaintenanceReminder) -> None:
    reminder.benachrichtigt_vorab_am = None
    reminder.benachrichtigt_faellig_am = None


# --- Senden (nur ExApp-Modus) ----------------------------------------------


def ui_link() -> str:
    """Absoluter Link auf die App-Oberflaeche. NEXTCLOUD_URL setzt AppAPI fuer
    jede ExApp; ohne sie geht die Benachrichtigung ohne Link raus."""
    base = os.environ.get("NEXTCLOUD_URL", "").rstrip("/")
    if not base:
        return ""
    base = base.removesuffix("/index.php")
    return base + UI_PATH


async def send_due_notifications(today: datetime.date | None = None) -> int:
    """Einmaliger Durchlauf; gibt die Zahl gesendeter Benachrichtigungen zurueck.
    Ein Fehler bei einem Nutzer haelt die uebrigen nicht auf; ohne Erfolg
    bleibt der Marker leer und der naechste Lauf versucht es erneut."""
    from nc_py_api import AsyncNextcloudApp

    from app.db import SessionLocal

    if not await AsyncNextcloudApp().enabled_state:
        LOGGER.info("App ist deaktiviert - keine Erinnerungs-Benachrichtigungen")
        return 0

    today = today or datetime.date.today()
    link = ui_link()
    sent = 0
    db = SessionLocal()
    try:
        for n in due_notifications(db, today):
            try:
                nc = AsyncNextcloudApp(user=n.owner)
                await nc.notifications.create(n.subject, n.message, link=link)
            except Exception:  # noqa: BLE001 - z.B. Nutzer geloescht, Nextcloud nicht erreichbar
                LOGGER.exception("Benachrichtigung fuer Erinnerung %s an %s fehlgeschlagen", n.reminder_id, n.owner)
                continue
            mark_notified(db, n.reminder_id, n.stage, today)
            sent += 1
    finally:
        db.close()
    return sent


async def notification_loop(first_delay: float = ERSTER_LAUF_NACH_S, interval: float = INTERVALL_S) -> None:
    await asyncio.sleep(first_delay)
    while True:
        try:
            sent = await send_due_notifications()
            LOGGER.info("Erinnerungs-Benachrichtigungen gesendet: %s", sent)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - der Hintergrundjob darf nie sterben
            LOGGER.exception("Erinnerungs-Benachrichtigungen fehlgeschlagen")
        await asyncio.sleep(interval)


def start_notification_task() -> asyncio.Task | None:
    """Startet den taeglichen Job - nie im Standalone-Modus (und damit nie in Tests)."""
    from app.access import standalone_mode

    if standalone_mode():
        return None
    return asyncio.create_task(notification_loop(), name="vehicle_tracker_reminder_notifications")
