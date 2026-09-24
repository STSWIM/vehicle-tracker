"""Export fuer Steuerberater / Fahrzeugverkauf: CSV und PDF-Bericht (Issue #14)."""
import csv
import io

import pytest

from app.access import CurrentUser, get_current_user

VEHICLE = {
    "kennzeichen": "RT-WI 14",
    "hersteller": "Toyota",
    "modell": "Previa",
    "kaufdatum": "2022-06-01",
    "kaufpreis": 5000.0,
    "kaufkilometerstand": 158_000,
}


def _post(client, path, payload):
    response = client.post(path, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _seed(client):
    vehicle_id = _post(client, "/api/vehicles", VEHICLE)["id"]
    _post(client, "/api/fuel-entries", {
        "vehicle_id": vehicle_id, "datum": "2023-12-30", "kilometerstand": 160_000, "kraftstoffart": "LPG",
        "fuellmenge_liter": 40.0, "preis_pro_liter": 0.999, "gesamtpreis": 39.96,
    })
    _post(client, "/api/fuel-entries", {
        "vehicle_id": vehicle_id, "datum": "2024-02-03", "kilometerstand": 160_500, "kraftstoffart": "LPG",
        "fuellmenge_liter": 45.5, "preis_pro_liter": 1.049, "gesamtpreis": 47.73, "tankstelle_name": "Aral Süd",
    })
    _post(client, "/api/other-costs", {
        "vehicle_id": vehicle_id, "datum": "2024-03-01", "kategorie": "Versicherung", "betrag": 1234.5,
        "beschreibung": "Kfz-Haftpflicht; Teilkasko",
    })
    _post(client, "/api/logbook", {
        "vehicle_id": vehicle_id, "datum": "2024-04-10", "kilometerstand": 161_000, "eintrag": "Ölwechsel",
        "notiz": "5W-30, Filter neu",
    })
    _post(client, "/api/trips", {
        "vehicle_id": vehicle_id, "datum": "2024-05-02", "start": "Reutlingen", "ziel": "Stuttgart",
        "km_start": 161_200, "km_ende": 161_245, "zweck": "Dienstlich",
    })
    return vehicle_id


def _csv_rows(response):
    assert response.content.startswith(b"\xef\xbb\xbf"), "UTF-8-BOM fuer Excel fehlt"
    text = response.content.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text), delimiter=";"))


def test_csv_enthaelt_alle_typen_mit_deutscher_formatierung(client):
    vehicle_id = _seed(client)
    response = client.get(f"/api/vehicles/{vehicle_id}/export.csv")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert 'attachment; filename="RT-WI_14_gesamt.csv"' in response.headers["content-disposition"]

    rows = _csv_rows(response)
    header = rows[0]
    assert header[:9] == ["Typ", "Datum", "km-Stand", "Kategorie/Kraftstoff", "Liter", "Preis/Liter (EUR)",
                          "Betrag (EUR)", "Strecke (km)", "Beschreibung/Notiz"]
    body = [dict(zip(header, row)) for row in rows[1:]]
    assert [r["Typ"] for r in body] == ["Tankung", "Tankung", "Kosten", "Logbuch", "Fahrt"]

    tankung = body[1]
    assert tankung["Datum"] == "03.02.2024"
    assert tankung["km-Stand"] == "160500"
    assert tankung["Kategorie/Kraftstoff"] == "LPG"
    assert tankung["Liter"] == "45,50"
    assert tankung["Preis/Liter (EUR)"] == "1,049"
    assert tankung["Betrag (EUR)"] == "47,73"
    assert tankung["Beschreibung/Notiz"] == "Aral Süd"

    kosten = body[2]
    assert kosten["Betrag (EUR)"] == "1234,50"
    assert kosten["Kategorie/Kraftstoff"] == "Versicherung"
    assert kosten["Beschreibung/Notiz"] == "Kfz-Haftpflicht; Teilkasko"  # Semikolon korrekt gequotet

    assert body[3]["Beschreibung/Notiz"] == "Ölwechsel – 5W-30, Filter neu"
    assert body[4]["Strecke (km)"] == "45"
    assert body[4]["Kategorie/Kraftstoff"] == "Dienstlich"


def test_csv_filtert_nach_zeitraum(client):
    vehicle_id = _seed(client)
    response = client.get(f"/api/vehicles/{vehicle_id}/export.csv?von=2024-01-01&bis=2024-03-31")
    assert response.status_code == 200
    assert 'filename="RT-WI_14_2024-01-01_bis_2024-03-31.csv"' in response.headers["content-disposition"]
    rows = _csv_rows(response)
    assert [(r[0], r[1]) for r in rows[1:]] == [("Tankung", "03.02.2024"), ("Kosten", "01.03.2024")]


def test_csv_verhindert_formel_injection(client):
    vehicle_id = _post(client, "/api/vehicles", VEHICLE)["id"]
    _post(client, "/api/other-costs", {
        "vehicle_id": vehicle_id, "datum": "2024-03-01", "kategorie": "Sonstiges", "betrag": 10,
        "beschreibung": "=HYPERLINK(\"http://x\")",
    })
    rows = _csv_rows(client.get(f"/api/vehicles/{vehicle_id}/export.csv"))
    assert rows[1][8].startswith("'=")


def test_pdf_bericht(client):
    vehicle_id = _seed(client)
    response = client.get(f"/api/vehicles/{vehicle_id}/export.pdf?von=2024-01-01&bis=2024-12-31&mit_anschaffung=false")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert 'filename="RT-WI_14_2024-01-01_bis_2024-12-31.pdf"' in response.headers["content-disposition"]


def test_pdf_ohne_eintraege(client):
    vehicle_id = _post(client, "/api/vehicles", {"kennzeichen": "B-XY 1", "hersteller": "VW", "modell": "Bus"})["id"]
    response = client.get(f"/api/vehicles/{vehicle_id}/export.pdf")
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


def test_pdf_nutzt_statistik_zahlen(client, monkeypatch):
    """Der Bericht bekommt exakt die Kennzahlen des Statistik-Endpunkts."""
    import app.routers.export as export_router

    vehicle_id = _seed(client)
    captured = {}

    def fake_build_pdf(data, stats):
        captured["stats"] = stats
        return b"%PDF-fake"

    monkeypatch.setattr(export_router, "build_pdf", fake_build_pdf)
    client.get(f"/api/vehicles/{vehicle_id}/export.pdf?von=2024-01-01&mit_anschaffung=false")
    expected = client.get(f"/api/vehicles/{vehicle_id}/stats?von=2024-01-01&mit_anschaffung=false").json()
    assert captured["stats"].model_dump(mode="json") == expected


@pytest.fixture()
def as_user(client):
    from main import app

    def switch(user):
        app.dependency_overrides[get_current_user] = lambda: user
        return client

    yield switch
    app.dependency_overrides.pop(get_current_user, None)


def test_export_nur_mit_zugriff(as_user):
    vehicle_id = _post(as_user(CurrentUser("alice")), "/api/vehicles", VEHICLE)["id"]
    carol = as_user(CurrentUser("carol"))
    assert carol.get(f"/api/vehicles/{vehicle_id}/export.csv").status_code == 404
    assert carol.get(f"/api/vehicles/{vehicle_id}/export.pdf").status_code == 404

    as_user(CurrentUser("alice")).put(
        f"/api/vehicles/{vehicle_id}/shares", json=[{"share_type": "user", "share_with": "carol"}]
    )
    assert as_user(CurrentUser("carol")).get(f"/api/vehicles/{vehicle_id}/export.csv").status_code == 200
