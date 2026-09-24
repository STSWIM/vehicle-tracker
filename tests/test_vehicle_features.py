"""Fahrzeug bearbeiten, Wartungslogbuch, Fahrtenbuch und Kostenauswertung."""

VEHICLE = {
    "kennzeichen": "RT-WI 14",
    "hersteller": "Toyota",
    "modell": "Previa",
    "kaufdatum": "2022-06-01",
    "kaufpreis": 5000.0,
    "kaufkilometerstand": 158_000,
}


def _vehicle(client, **overrides):
    response = client.post("/api/vehicles", json={**VEHICLE, **overrides})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _fuel(client, vehicle_id, datum, km, gesamt, nicht_voll=False):
    response = client.post(
        "/api/fuel-entries",
        json={
            "vehicle_id": vehicle_id, "datum": datum, "kilometerstand": km,
            "kraftstoffart": "LPG", "fuellmenge_liter": 30.0, "preis_pro_liter": 1.0,
            "gesamtpreis": gesamt, "nicht_voll": nicht_voll,
        },
    )
    assert response.status_code == 201, response.text


def _cost(client, vehicle_id, datum, kategorie, betrag):
    response = client.post(
        "/api/other-costs",
        json={"vehicle_id": vehicle_id, "datum": datum, "kategorie": kategorie, "betrag": betrag},
    )
    assert response.status_code == 201, response.text


# --- Fahrzeug bearbeiten ---------------------------------------------------

def test_fahrzeug_bearbeiten(client):
    vehicle_id = _vehicle(client, kaufkilometerstand=None, bot_codewort="Previa")
    response = client.put(
        f"/api/vehicles/{vehicle_id}",
        json={**VEHICLE, "kaufkilometerstand": 157_500, "bot_codewort": "Bus"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kaufkilometerstand"] == 157_500
    assert body["bot_codewort"] == "bus"


def test_bearbeiten_mit_vergebenem_kennzeichen_scheitert(client):
    _vehicle(client)
    other_id = _vehicle(client, kennzeichen="RT-XY 1")
    response = client.put(f"/api/vehicles/{other_id}", json=VEHICLE)
    assert response.status_code == 400


def test_doppeltes_codewort_gibt_400_statt_500(client):
    _vehicle(client, bot_codewort="previa")
    response = client.post("/api/vehicles", json={**VEHICLE, "kennzeichen": "RT-XY 1", "bot_codewort": "Previa"})
    assert response.status_code == 400


def test_kaufkilometerstand_nicht_ueber_vorhandenen_tankeintraegen(client):
    vehicle_id = _vehicle(client)
    _fuel(client, vehicle_id, "2022-07-01", 158_500, 40.0)
    response = client.put(f"/api/vehicles/{vehicle_id}", json={**VEHICLE, "kaufkilometerstand": 159_000})
    assert response.status_code == 400


# --- Logbuch & Fahrtenbuch ---------------------------------------------------

def test_wartungslogbuch_anlegen_auflisten_loeschen(client):
    vehicle_id = _vehicle(client)
    response = client.post(
        "/api/logbook",
        json={"vehicle_id": vehicle_id, "datum": "2024-03-02", "kilometerstand": 161_200, "eintrag": "Ölwechsel"},
    )
    assert response.status_code == 201, response.text
    entry_id = response.json()["id"]

    entries = client.get(f"/api/logbook?vehicle_id={vehicle_id}").json()
    assert [e["eintrag"] for e in entries] == ["Ölwechsel"]

    assert client.delete(f"/api/logbook/{entry_id}").status_code == 204
    assert client.get(f"/api/logbook?vehicle_id={vehicle_id}").json() == []


def test_fahrt_mit_km_ende_vor_start_wird_abgelehnt(client):
    vehicle_id = _vehicle(client)
    response = client.post(
        "/api/trips",
        json={"vehicle_id": vehicle_id, "datum": "2024-03-02", "start": "A", "ziel": "B",
              "km_start": 161_245, "km_ende": 161_200},
    )
    assert response.status_code == 422


def test_fahrt_unter_kaufkilometerstand_wird_abgelehnt(client):
    vehicle_id = _vehicle(client)
    response = client.post(
        "/api/trips",
        json={"vehicle_id": vehicle_id, "datum": "2024-03-02", "start": "A", "ziel": "B",
              "km_start": 157_000, "km_ende": 157_050},
    )
    assert response.status_code == 400


def test_fahrt_anlegen(client):
    vehicle_id = _vehicle(client)
    response = client.post(
        "/api/trips",
        json={"vehicle_id": vehicle_id, "datum": "2024-03-02", "start": "Reutlingen", "ziel": "Stuttgart",
              "km_start": 161_200, "km_ende": 161_245, "zweck": "Dienstlich"},
    )
    assert response.status_code == 201, response.text
    assert client.get(f"/api/trips?vehicle_id={vehicle_id}").json()[0]["zweck"] == "Dienstlich"


# --- Verbrauch ---------------------------------------------------------------

def _fuel_art(client, vehicle_id, datum, km, liter, art):
    response = client.post(
        "/api/fuel-entries",
        json={"vehicle_id": vehicle_id, "datum": datum, "kilometerstand": km, "kraftstoffart": art,
              "fuellmenge_liter": liter, "preis_pro_liter": 1.0, "gesamtpreis": liter},
    )
    assert response.status_code == 201, response.text


def test_verbrauch_getrennt_nach_kraftstoff(client):
    """LPG- und Benzin-Tankungen eines bivalenten Fahrzeugs duerfen nicht in
    eine gemeinsame Voll-zu-Voll-Kette geraten."""
    vehicle_id = _vehicle(client, kaufkilometerstand=None)
    _fuel_art(client, vehicle_id, "2023-01-01", 1_000, 40.0, "LPG")
    _fuel_art(client, vehicle_id, "2023-01-05", 1_100, 10.0, "Benzin")
    _fuel_art(client, vehicle_id, "2023-01-20", 1_300, 42.0, "LPG")
    _fuel_art(client, vehicle_id, "2023-02-01", 1_600, 6.0, "Benzin")

    s = client.get(f"/api/vehicles/{vehicle_id}/stats").json()
    assert s["verbrauch_nach_kraftstoff"] == {"LPG": 14.0, "Benzin": 1.2}
    assert s["ø_verbrauch_l_100km"] is None  # mehrere Kraftstoffe -> kein Einzelwert


def test_bei_kauf_vollgetankt_liefert_verbrauch_ab_erster_tankung(client):
    vehicle_id = _vehicle(client, bei_kauf_vollgetankt=True)  # Kauf bei 158.000 km
    _fuel_art(client, vehicle_id, "2022-07-01", 158_220, 30.37, "LPG")

    s = client.get(f"/api/vehicles/{vehicle_id}/stats").json()
    assert s["verbrauch_nach_kraftstoff"] == {"LPG": round(30.37 / 220 * 100, 2)}
    assert s["ø_verbrauch_l_100km"] == round(30.37 / 220 * 100, 2)


def test_ohne_vollgetankt_bei_kauf_kein_verbrauch_aus_einer_tankung(client):
    vehicle_id = _vehicle(client)
    _fuel_art(client, vehicle_id, "2022-07-01", 158_220, 30.37, "LPG")
    assert client.get(f"/api/vehicles/{vehicle_id}/stats").json()["verbrauch_nach_kraftstoff"] == {}


# --- Kostenauswertung --------------------------------------------------------

def _setup_kosten(client):
    vehicle_id = _vehicle(client)
    _cost(client, vehicle_id, "2022-06-02", "Einmalig", 150.0)      # Zulassung
    _fuel(client, vehicle_id, "2022-07-01", 158_500, 40.0)
    _cost(client, vehicle_id, "2023-01-15", "Versicherung", 300.0)
    _fuel(client, vehicle_id, "2023-02-01", 160_000, 60.0)
    return vehicle_id


def test_gesamtzeitraum_mit_anschaffung(client):
    vehicle_id = _setup_kosten(client)
    s = client.get(f"/api/vehicles/{vehicle_id}/stats").json()
    assert s["anschaffungskosten"] == 5150.0
    assert s["gesamt_sonstige_kosten"] == 300.0
    assert s["kosten_nach_kategorie"] == {"Versicherung": 300.0}
    assert s["gesamtkosten"] == 5000 + 150 + 40 + 300 + 60
    # km ab Kauf-km-Stand, nicht erst ab der ersten Tankung
    assert s["gefahrene_km"] == 2000.0
    assert s["zeitraum_von"] == "2022-06-01"


def test_gesamtzeitraum_ohne_anschaffung(client):
    vehicle_id = _setup_kosten(client)
    s = client.get(f"/api/vehicles/{vehicle_id}/stats?mit_anschaffung=false").json()
    assert s["anschaffungskosten"] == 5150.0  # wird weiter ausgewiesen ...
    assert s["gesamtkosten"] == 40 + 300 + 60  # ... aber nicht mitgerechnet
    assert s["kosten_pro_km"] == round(400 / 2000, 3)


def test_zeitraum_ohne_kauf_zaehlt_kaufpreis_nicht(client):
    vehicle_id = _setup_kosten(client)
    s = client.get(f"/api/vehicles/{vehicle_id}/stats?von=2023-01-01&bis=2023-12-31").json()
    assert s["anschaffungskosten"] == 0.0
    assert s["gesamtkosten"] == 300 + 60
    assert s["zeitraum_von"] == "2023-01-01"
    assert s["zeitraum_bis"] == "2023-12-31"
