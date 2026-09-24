"""Erinnerungen: CRUD, Zugriffsrechte und Auswahl der Benachrichtigungen."""
import datetime

import pytest

from app.access import CurrentUser, get_current_user
from app.models import FuelEntry, Kraftstoffart, MaintenanceReminder, Vehicle
from app.reminder_notifications import (
    STAGE_FAELLIG,
    STAGE_VORAB,
    due_notifications,
    mark_notified,
    ui_link,
)

ALICE = CurrentUser("alice")
CAROL = CurrentUser("carol")
TODAY = datetime.date(2026, 9, 17)


@pytest.fixture()
def as_user(client):
    from main import app

    def switch(user):
        app.dependency_overrides[get_current_user] = lambda: user
        return client

    yield switch
    app.dependency_overrides.pop(get_current_user, None)


def _vehicle(client):
    response = client.post("/api/vehicles", json={"kennzeichen": "RT-WI 14", "hersteller": "Toyota", "modell": "Previa"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _reminder(client, vehicle_id, **fields):
    payload = {"vehicle_id": vehicle_id, "typ": "TÜV/HU", "faellig_am": "2026-10-01", **fields}
    return client.post("/api/reminders", json=payload)


# --- CRUD + Zugriff ----------------------------------------------------------


def test_reminder_bearbeiten_und_loeschen(as_user):
    alice = as_user(ALICE)
    vehicle_id = _vehicle(alice)
    reminder = _reminder(alice, vehicle_id).json()

    response = alice.put(
        f"/api/reminders/{reminder['id']}",
        json={"vehicle_id": vehicle_id, "typ": "Service/Inspektion", "faellig_km": 180_000, "beschreibung": "Ölwechsel"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["typ"] == "Service/Inspektion"
    assert response.json()["faellig_am"] is None

    assert alice.delete(f"/api/reminders/{reminder['id']}").status_code == 204
    assert alice.get("/api/reminders", params={"vehicle_id": vehicle_id}).json() == []


def test_reminder_ohne_faelligkeit_abgelehnt(as_user):
    alice = as_user(ALICE)
    vehicle_id = _vehicle(alice)
    assert _reminder(alice, vehicle_id, faellig_am=None).status_code == 422


def test_fremder_nutzer_bekommt_404(as_user):
    vehicle_id = _vehicle(as_user(ALICE))
    reminder = _reminder(as_user(ALICE), vehicle_id).json()

    carol = as_user(CAROL)
    assert _reminder(carol, vehicle_id).status_code == 404
    assert carol.get("/api/reminders/status").json() == []
    assert carol.delete(f"/api/reminders/{reminder['id']}").status_code == 404
    assert carol.post(f"/api/reminders/{reminder['id']}/erledigt").status_code == 404
    response = carol.put(f"/api/reminders/{reminder['id']}", json={"vehicle_id": vehicle_id, "typ": "TÜV/HU", "faellig_am": "2027-01-01"})
    assert response.status_code == 404


def test_freigegebener_nutzer_darf_alles(as_user):
    alice = as_user(ALICE)
    vehicle_id = _vehicle(alice)
    alice.put(f"/api/vehicles/{vehicle_id}/shares", json=[{"share_type": "user", "share_with": "carol"}])

    carol = as_user(CAROL)
    reminder = _reminder(carol, vehicle_id).json()
    assert [r["id"] for r in carol.get("/api/reminders/status", params={"vehicle_id": vehicle_id}).json()] == [reminder["id"]]
    assert carol.post(f"/api/reminders/{reminder['id']}/erledigt").json()["erledigt"] is True
    assert carol.delete(f"/api/reminders/{reminder['id']}").status_code == 204


def test_status_endpunkt_berechnet_faelligkeit(as_user, db_session):
    alice = as_user(ALICE)
    vehicle_id = _vehicle(alice)
    heute = datetime.date.today()
    _reminder(alice, vehicle_id, faellig_am=(heute - datetime.timedelta(days=3)).isoformat())
    _reminder(alice, vehicle_id, faellig_am=(heute + datetime.timedelta(days=10)).isoformat())
    _reminder(alice, vehicle_id, faellig_am=(heute + datetime.timedelta(days=100)).isoformat())
    db_session.add(FuelEntry(vehicle_id=vehicle_id, datum=heute, kilometerstand=179_700, kraftstoffart=Kraftstoffart.LPG,
                             fuellmenge_liter=30, preis_pro_liter=1, gesamtpreis=30))
    db_session.commit()
    _reminder(alice, vehicle_id, faellig_am=None, faellig_km=180_000)

    status = alice.get("/api/reminders/status", params={"vehicle_id": vehicle_id}).json()
    assert [r["status"] for r in status] == ["faellig", "bald", None, "bald"]
    assert status[0]["rest_tage"] == -3
    assert status[3]["rest_km"] == 300
    assert status[3]["aktueller_km"] == 179_700


def test_erledigt_mit_intervall_setzt_marker_zurueck(as_user, db_session):
    alice = as_user(ALICE)
    vehicle_id = _vehicle(alice)
    reminder = _reminder(alice, vehicle_id, intervall_monate=24).json()
    db_session.get(MaintenanceReminder, reminder["id"]).benachrichtigt_vorab_am = TODAY
    db_session.commit()

    assert alice.post(f"/api/reminders/{reminder['id']}/erledigt").json()["erledigt"] is False
    db_session.expire_all()
    assert db_session.get(MaintenanceReminder, reminder["id"]).benachrichtigt_vorab_am is None


# --- Auswahl der Benachrichtigungen --------------------------------------------


def _db_vehicle(db, owner="alice", kennzeichen="RT-WI 14", kaufkilometerstand=None):
    vehicle = Vehicle(kennzeichen=kennzeichen, hersteller="Toyota", modell="Previa", owner=owner,
                      kaufkilometerstand=kaufkilometerstand)
    db.add(vehicle)
    db.commit()
    return vehicle


def _db_reminder(db, vehicle, **fields):
    reminder = MaintenanceReminder(vehicle_id=vehicle.id, typ=fields.pop("typ", "TÜV/HU"), **fields)
    db.add(reminder)
    db.commit()
    return reminder


def test_datumsfenster(db_session):
    vehicle = _db_vehicle(db_session)
    bald = _db_reminder(db_session, vehicle, faellig_am=datetime.date(2026, 10, 1))  # in 14 Tagen
    _db_reminder(db_session, vehicle, faellig_am=datetime.date(2026, 10, 2))  # in 15 Tagen
    ueberfaellig = _db_reminder(db_session, vehicle, faellig_am=datetime.date(2026, 9, 1))
    _db_reminder(db_session, vehicle, faellig_am=datetime.date(2026, 9, 1), erledigt=True)

    result = due_notifications(db_session, TODAY)
    assert [(n.reminder_id, n.stage, n.owner) for n in result] == [
        (bald.id, STAGE_VORAB, "alice"),
        (ueberfaellig.id, STAGE_FAELLIG, "alice"),
    ]
    assert result[0].subject == "TÜV/HU für RT-WI 14 fällig am 01.10.2026"
    assert result[1].subject == "TÜV/HU für RT-WI 14 überfällig seit 01.09.2026"


def test_kilometerfenster(db_session):
    vehicle = _db_vehicle(db_session, kaufkilometerstand=179_600)
    bald = _db_reminder(db_session, vehicle, typ="Service/Inspektion", faellig_km=180_000)
    _db_reminder(db_session, vehicle, typ="Service/Inspektion", faellig_km=180_200)
    erreicht = _db_reminder(db_session, vehicle, typ="Reifenwechsel", faellig_km=179_000)

    result = due_notifications(db_session, TODAY)
    assert [(n.reminder_id, n.stage) for n in result] == [(bald.id, STAGE_VORAB), (erreicht.id, STAGE_FAELLIG)]
    assert result[0].subject == "Service/Inspektion für RT-WI 14 fällig bei 180.000 km"
    assert "noch 400 km" in result[0].message


def test_ohne_besitzer_oder_deaktiviert_keine_benachrichtigung(db_session):
    ohne = _db_vehicle(db_session, owner=None)
    _db_reminder(db_session, ohne, faellig_am=TODAY)
    inaktiv = _db_vehicle(db_session, kennzeichen="RT-XX 1")
    inaktiv.aktiv = False
    db_session.commit()
    _db_reminder(db_session, inaktiv, faellig_am=TODAY)

    assert due_notifications(db_session, TODAY) == []


def test_keine_doppelte_benachrichtigung_und_erneut_bei_faelligkeit(db_session):
    vehicle = _db_vehicle(db_session)
    reminder = _db_reminder(db_session, vehicle, faellig_am=datetime.date(2026, 10, 1))

    [vorab] = due_notifications(db_session, TODAY)
    assert vorab.stage == STAGE_VORAB
    mark_notified(db_session, reminder.id, vorab.stage, TODAY)
    assert due_notifications(db_session, TODAY) == []
    assert due_notifications(db_session, datetime.date(2026, 9, 30)) == []

    [faellig] = due_notifications(db_session, datetime.date(2026, 10, 1))
    assert faellig.stage == STAGE_FAELLIG
    assert faellig.subject == "TÜV/HU für RT-WI 14 heute fällig"
    mark_notified(db_session, reminder.id, faellig.stage, datetime.date(2026, 10, 1))
    assert due_notifications(db_session, datetime.date(2026, 10, 20)) == []


def test_bearbeiten_setzt_benachrichtigung_zurueck(as_user, db_session):
    alice = as_user(ALICE)
    vehicle_id = _vehicle(alice)
    reminder = _reminder(alice, vehicle_id).json()
    mark_notified(db_session, reminder["id"], STAGE_FAELLIG, TODAY)
    assert due_notifications(db_session, datetime.date(2026, 10, 5)) == []

    alice.put(f"/api/reminders/{reminder['id']}", json={"vehicle_id": vehicle_id, "typ": "TÜV/HU", "faellig_am": "2026-10-10"})
    db_session.expire_all()
    [n] = due_notifications(db_session, datetime.date(2026, 10, 5))
    assert n.stage == STAGE_VORAB


def test_ui_link(monkeypatch):
    monkeypatch.setenv("NEXTCLOUD_URL", "https://cloud.example.org/index.php/")
    assert ui_link() == "https://cloud.example.org/index.php/apps/app_api/embedded/vehicle_tracker/ui"
    monkeypatch.delenv("NEXTCLOUD_URL")
    assert ui_link() == ""


def test_senden_setzt_marker_nur_bei_erfolg(db_session, monkeypatch):
    import asyncio

    import nc_py_api

    from app.reminder_notifications import send_due_notifications

    ok = _db_reminder(db_session, _db_vehicle(db_session, owner="alice"), faellig_am=TODAY)
    kaputt = _db_reminder(db_session, _db_vehicle(db_session, owner="bob", kennzeichen="RT-XX 2"), faellig_am=TODAY)
    gesendet = []

    class FakeNotifications:
        def __init__(self, user):
            self.user = user

        async def create(self, subject, message="", link=""):
            if self.user == "bob":
                raise RuntimeError("Nutzer unbekannt")
            gesendet.append((self.user, subject, link))
            return "id"

    class FakeApp:
        def __init__(self, user=""):
            self.notifications = FakeNotifications(user)

        @property
        async def enabled_state(self):
            return True

    monkeypatch.setattr(nc_py_api, "AsyncNextcloudApp", FakeApp)
    monkeypatch.setenv("NEXTCLOUD_URL", "https://cloud.example.org")

    assert asyncio.run(send_due_notifications(TODAY)) == 1
    assert gesendet == [
        ("alice", "TÜV/HU für RT-WI 14 heute fällig",
         "https://cloud.example.org/index.php/apps/app_api/embedded/vehicle_tracker/ui")
    ]
    db_session.expire_all()
    assert db_session.get(MaintenanceReminder, ok.id).benachrichtigt_faellig_am == TODAY
    assert db_session.get(MaintenanceReminder, kaputt.id).benachrichtigt_faellig_am is None
