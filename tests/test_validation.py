"""
Tests fuer die Plausibilitaetspruefungen aus app/validation.py: der
Kilometerstand darf der bestehenden Fahrhistorie nicht widersprechen, und
stark abweichender Verbrauch soll als Warnung im Response landen statt
unbemerkt in der Statistik zu verschwinden. Ausserdem ein Regressionstest
fuer den reminders.mark_done-Bug bei rein kilometerbasierten Intervallen.
"""


def _seed_vehicle(client):
    response = client.post(
        "/api/vehicles",
        json={
            "kennzeichen": "RT-WI 99",
            "hersteller": "Toyota",
            "modell": "Previa",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _post_entry(client, vehicle_id, datum, km, menge=30.0, preis=1.5, nicht_voll=False):
    return client.post(
        "/api/fuel-entries",
        json={
            "vehicle_id": vehicle_id,
            "datum": datum,
            "kilometerstand": km,
            "kraftstoffart": "Benzin",
            "fuellmenge_liter": menge,
            "preis_pro_liter": preis,
            "gesamtpreis": round(menge * preis, 2),
            "nicht_voll": nicht_voll,
        },
    )


def test_kilometerstand_darf_an_spaeterem_datum_nicht_sinken(client):
    vehicle_id = _seed_vehicle(client)
    assert _post_entry(client, vehicle_id, "2024-01-01", 10_000).status_code == 201

    response = _post_entry(client, vehicle_id, "2024-02-01", 9_500)
    assert response.status_code == 400
    assert "10000" in response.text


def test_kilometerstand_darf_nicht_ueber_spaeter_erfasstem_stand_liegen(client):
    """Nachtraeglich eingefuegter (fruehdatierter) Eintrag muss ebenfalls
    zur bereits vorhandenen, spaeter datierten Historie passen."""
    vehicle_id = _seed_vehicle(client)
    assert _post_entry(client, vehicle_id, "2024-03-01", 20_000).status_code == 201

    response = _post_entry(client, vehicle_id, "2024-01-01", 25_000)
    assert response.status_code == 400
    assert "20000" in response.text


def test_kilometerstand_darf_nicht_unter_kaufkilometerstand_liegen(client):
    response = client.post(
        "/api/vehicles",
        json={"kennzeichen": "RT-WI 98", "hersteller": "Toyota", "modell": "Previa", "kaufkilometerstand": 150_000},
    )
    assert response.status_code == 201, response.text
    vehicle_id = response.json()["id"]

    response = _post_entry(client, vehicle_id, "2024-01-01", 149_000)
    assert response.status_code == 400
    assert "150000" in response.text
    assert _post_entry(client, vehicle_id, "2024-01-01", 150_500).status_code == 201


def test_verbrauch_ausreisser_wird_als_warnung_gemeldet(client):
    vehicle_id = _seed_vehicle(client)
    # Baseline: ca. 6 l/100km ueber mehrere Volltankungen.
    assert _post_entry(client, vehicle_id, "2024-01-01", 0, menge=30.0).status_code == 201
    assert _post_entry(client, vehicle_id, "2024-02-01", 500, menge=30.0).status_code == 201
    assert _post_entry(client, vehicle_id, "2024-03-01", 1_000, menge=30.0).status_code == 201

    # Deutlicher Ausreisser: nur 50 km mit 30 l getankt (60 l/100km).
    response = _post_entry(client, vehicle_id, "2024-04-01", 1_050, menge=30.0)
    assert response.status_code == 201
    assert response.json()["warnungen"]


def test_verbrauch_im_rahmen_erzeugt_keine_warnung(client):
    vehicle_id = _seed_vehicle(client)
    assert _post_entry(client, vehicle_id, "2024-01-01", 0, menge=30.0).status_code == 201
    response = _post_entry(client, vehicle_id, "2024-02-01", 500, menge=30.0)
    assert response.status_code == 201
    assert response.json()["warnungen"] == []


def test_reminder_mit_km_intervall_verlangt_km_bei_erledigt(client):
    vehicle_id = _seed_vehicle(client)
    reminder = client.post(
        "/api/reminders",
        json={
            "vehicle_id": vehicle_id,
            "typ": "Service/Inspektion",
            "intervall_km": 10_000,
        },
    ).json()

    ohne_km = client.post(f"/api/reminders/{reminder['id']}/erledigt")
    assert ohne_km.status_code == 400

    mit_km = client.post(f"/api/reminders/{reminder['id']}/erledigt", params={"km": 50_000})
    assert mit_km.status_code == 200
    body = mit_km.json()
    assert body["erledigt"] is False
    assert body["faellig_km"] == 60_000
