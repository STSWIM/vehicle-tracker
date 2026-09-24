"""Zugriffsrechte: Besitzer, Nutzer- und Gruppenfreigaben, Besitzuebernahme."""
import pytest

from app.access import CurrentUser, get_current_user
from app.db import SessionLocal
from app.models import Vehicle

ALICE = CurrentUser("alice")
BOB = CurrentUser("bob", groups=frozenset({"familie"}))
CAROL = CurrentUser("carol")


@pytest.fixture()
def as_user(client):
    from main import app

    def switch(user):
        app.dependency_overrides[get_current_user] = lambda: user
        return client

    yield switch
    app.dependency_overrides.pop(get_current_user, None)


def _vehicle(client, kennzeichen="RT-WI 14"):
    response = client.post("/api/vehicles", json={"kennzeichen": kennzeichen, "hersteller": "Toyota", "modell": "Previa"})
    assert response.status_code == 201, response.text
    return response.json()


def test_nur_besitzer_sieht_eigenes_fahrzeug(as_user):
    vehicle = _vehicle(as_user(ALICE))
    assert vehicle["owner"] == "alice"

    carol = as_user(CAROL)
    assert carol.get("/api/vehicles").json() == []
    assert carol.get(f"/api/vehicles/{vehicle['id']}").status_code == 404
    assert carol.get(f"/api/vehicles/{vehicle['id']}/stats").status_code == 404
    response = carol.post(
        "/api/fuel-entries",
        json={"vehicle_id": vehicle["id"], "datum": "2024-01-01", "kilometerstand": 1000, "kraftstoffart": "LPG",
              "fuellmenge_liter": 30, "preis_pro_liter": 1, "gesamtpreis": 30},
    )
    assert response.status_code == 404


def test_nutzerfreigabe_gibt_volle_nutzung(as_user):
    vehicle = _vehicle(as_user(ALICE))
    response = as_user(ALICE).put(f"/api/vehicles/{vehicle['id']}/shares", json=[{"share_type": "user", "share_with": "carol"}])
    assert response.status_code == 200, response.text

    carol = as_user(CAROL)
    assert [v["id"] for v in carol.get("/api/vehicles").json()] == [vehicle["id"]]
    response = carol.post("/api/logbook", json={"vehicle_id": vehicle["id"], "datum": "2024-01-01", "eintrag": "Ölwechsel"})
    assert response.status_code == 201


def test_gruppenfreigabe(as_user):
    vehicle = _vehicle(as_user(ALICE))
    as_user(ALICE).put(f"/api/vehicles/{vehicle['id']}/shares", json=[{"share_type": "group", "share_with": "familie"}])

    assert [v["id"] for v in as_user(BOB).get("/api/vehicles").json()] == [vehicle["id"]]
    assert as_user(CAROL).get("/api/vehicles").json() == []


def test_nur_besitzer_verwaltet_freigaben(as_user):
    vehicle = _vehicle(as_user(ALICE))
    as_user(ALICE).put(f"/api/vehicles/{vehicle['id']}/shares", json=[{"share_type": "user", "share_with": "carol"}])

    response = as_user(CAROL).put(f"/api/vehicles/{vehicle['id']}/shares", json=[])
    assert response.status_code == 403
    assert as_user(CAROL).delete(f"/api/vehicles/{vehicle['id']}").status_code == 403


def test_fahrzeug_ohne_besitzer_geht_an_ersten_nutzer(as_user, db_session):
    db_session.add(Vehicle(kennzeichen="ALT 1", hersteller="VW", modell="Bus"))
    db_session.commit()

    vehicles = as_user(ALICE).get("/api/vehicles").json()
    assert [(v["kennzeichen"], v["owner"]) for v in vehicles] == [("ALT 1", "alice")]
    assert as_user(CAROL).get("/api/vehicles").json() == []


def test_talk_codewort_nur_mit_zugriff(as_user):
    from app.talk_bot.session import resolve_vehicle_by_codewort

    vehicle = _vehicle(as_user(ALICE))
    as_user(ALICE).put(
        f"/api/vehicles/{vehicle['id']}",
        json={"kennzeichen": "RT-WI 14", "hersteller": "Toyota", "modell": "Previa", "bot_codewort": "previa"},
    )
    db = SessionLocal()
    try:
        assert resolve_vehicle_by_codewort(db, "Previa", ALICE).id == vehicle["id"]
        assert resolve_vehicle_by_codewort(db, "Previa", CAROL) is None
    finally:
        db.close()
