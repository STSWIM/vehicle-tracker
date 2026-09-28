"""Diagramm-Daten: km je Tag/Monat/Jahr, Verbrauch, Spritpreis."""
import datetime

from app.charts import km_pro_tag

D = datetime.date


def test_km_gleichmaessig_auf_tage_verteilt():
    tage = km_pro_tag([(D(2024, 1, 30), 1000), (D(2024, 2, 2), 1300)])
    assert tage == {D(2024, 1, 31): 100.0, D(2024, 2, 1): 100.0, D(2024, 2, 2): 100.0}


def _fuel(client, vehicle_id, datum, km, liter, preis, art="LPG"):
    response = client.post("/api/fuel-entries", json={
        "vehicle_id": vehicle_id, "datum": datum, "kilometerstand": km, "kraftstoffart": art,
        "fuellmenge_liter": liter, "preis_pro_liter": preis, "gesamtpreis": round(liter * preis, 2),
    })
    assert response.status_code == 201, response.text


def test_chart_endpunkt(client):
    vehicle = client.post("/api/vehicles", json={
        "kennzeichen": "RT-WI 14", "hersteller": "Toyota", "modell": "Previa",
        "kaufdatum": "2023-12-31", "kaufkilometerstand": 10_000,
    }).json()
    _fuel(client, vehicle["id"], "2024-01-10", 10_900, 40.0, 1.0)
    _fuel(client, vehicle["id"], "2024-02-09", 11_500, 60.0, 1.1)

    data = client.get(f"/api/vehicles/{vehicle['id']}/charts").json()
    assert data["km"]["jahr"] == [["2024", 1500.0]]
    monate = dict(data["km"]["monat"])
    assert round(monate["2024-01"] + monate["2024-02"], 1) == 1500.0
    assert data["preis"]["LPG"] == [["2024-01-10", 1.0], ["2024-02-09", 1.1]]
    assert data["verbrauch"]["LPG"] == [["2024-02-09", 10.0]]


def test_chart_nur_mit_zugriff(client):
    from app.access import CurrentUser, get_current_user
    from main import app

    vehicle = client.post("/api/vehicles", json={"kennzeichen": "X 1", "hersteller": "VW", "modell": "Bus"}).json()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser("fremd")
    try:
        assert client.get(f"/api/vehicles/{vehicle['id']}/charts").status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_km_am_selben_tag_gehen_nicht_verloren():
    # Kauf bei 1000 km und erste Tankung bei 1220 km am selben Tag
    tage = km_pro_tag([(D(2024, 1, 1), 1000), (D(2024, 1, 1), 1220), (D(2024, 1, 3), 1420)])
    assert tage == {D(2024, 1, 1): 220.0, D(2024, 1, 2): 100.0, D(2024, 1, 3): 100.0}
