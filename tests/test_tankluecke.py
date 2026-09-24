"""
Tankluecken-Erkennung (Issue #12): springt der Kilometerstand aus Fahrten
oder Logbuch weiter, als das Fahrzeug seit der letzten Tankung plausibel
fahren kann, gibt es eine (nicht blockierende) Warnung "fehlt ein
Tankbeleg?" - beim Speichern und dauerhaft als Hinweis in den Kennzahlen.
"""
from app.validation import REICHWEITE_FALLBACK_KM, max_reichweite_km


def _vehicle(client):
    response = client.post(
        "/api/vehicles", json={"kennzeichen": "RT-TL 12", "hersteller": "Toyota", "modell": "Previa"}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _fuel(client, vehicle_id, datum, km, liter=30.0):
    response = client.post(
        "/api/fuel-entries",
        json={"vehicle_id": vehicle_id, "datum": datum, "kilometerstand": km, "kraftstoffart": "Benzin",
              "fuellmenge_liter": liter, "preis_pro_liter": 1.5, "gesamtpreis": round(liter * 1.5, 2)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _trip(client, vehicle_id, datum, km_start, km_ende):
    response = client.post(
        "/api/trips",
        json={"vehicle_id": vehicle_id, "datum": datum, "start": "A", "ziel": "B",
              "km_start": km_start, "km_ende": km_ende},
    )
    assert response.status_code == 201, response.text  # Warnungen blockieren nie
    return response.json()


def _logbook(client, vehicle_id, datum, km):
    response = client.post(
        "/api/logbook",
        json={"vehicle_id": vehicle_id, "datum": datum, "kilometerstand": km, "eintrag": "Ölwechsel"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _regelmaessig_getankt(client):
    """Alle 500 km getankt -> plausible Reichweite 500 x 1,2 = 600 km."""
    vehicle_id = _vehicle(client)
    for datum, km in [("2024-01-01", 10_000), ("2024-01-15", 10_500), ("2024-02-01", 11_000),
                      ("2024-02-15", 11_500)]:
        _fuel(client, vehicle_id, datum, km)
    return vehicle_id


def test_fahrt_mit_tankluecke_warnt(client):
    vehicle_id = _regelmaessig_getankt(client)
    body = _trip(client, vehicle_id, "2024-03-01", 11_600, 12_300)
    assert body["warnungen"] == [
        "Seit der letzten Tankung am 15.02.2024 (11.500 km) sind 800 km vergangen – fehlt ein Tankbeleg?"
    ]


def test_fahrt_ohne_tankluecke_warnt_nicht(client):
    vehicle_id = _regelmaessig_getankt(client)
    assert _trip(client, vehicle_id, "2024-03-01", 11_600, 11_900)["warnungen"] == []
    assert client.get(f"/api/vehicles/{vehicle_id}/stats").json()["hinweise"] == []


def test_logbuch_mit_tankluecke_und_ohne_kilometerstand(client):
    vehicle_id = _regelmaessig_getankt(client)
    assert _logbook(client, vehicle_id, "2024-03-01", 12_200)["warnungen"]
    assert _logbook(client, vehicle_id, "2024-03-02", None)["warnungen"] == []


def test_ausweichwert_bei_wenigen_tankungen(client, db_session):
    vehicle_id = _vehicle(client)
    _fuel(client, vehicle_id, "2024-01-01", 10_000)
    _fuel(client, vehicle_id, "2024-01-15", 10_300)
    assert max_reichweite_km(db_session, vehicle_id) == REICHWEITE_FALLBACK_KM == 900

    # datengetrieben waeren 300 x 1,2 = 360 km -> hier noch keine Warnung
    assert _logbook(client, vehicle_id, "2024-02-01", 11_100)["warnungen"] == []
    assert _logbook(client, vehicle_id, "2024-02-02", 11_300)["warnungen"]


def test_reichweite_robust_gegen_einzelne_alte_luecke(client, db_session):
    """90. Perzentil statt Maximum: eine alte Luecke von 2.000 km blaeht die
    plausible Reichweite nicht auf."""
    vehicle_id = _vehicle(client)
    km = 10_000
    for tag in range(1, 11):
        _fuel(client, vehicle_id, f"2024-01-{tag:02d}", km)
        km += 500
    _fuel(client, vehicle_id, "2024-01-20", km + 1_500)  # 2.000 km nach der vorigen
    assert max_reichweite_km(db_session, vehicle_id) == 600


def test_stats_hinweis_bis_tankung_nachgetragen(client):
    vehicle_id = _regelmaessig_getankt(client)
    _trip(client, vehicle_id, "2024-03-01", 11_600, 12_300)

    hinweise = client.get(f"/api/vehicles/{vehicle_id}/stats").json()["hinweise"]
    assert len(hinweise) == 1 and "fehlt ein Tankbeleg?" in hinweise[0]
    # Hinweis gilt unabhaengig vom gewaehlten Auswertungszeitraum
    s = client.get(f"/api/vehicles/{vehicle_id}/stats?von=2024-01-01&bis=2024-01-31").json()
    assert s["hinweise"] == hinweise

    # Naechste Tankung nach 850 km mit nur 30 l: Verbrauchswarnung bekommt den
    # Tankluecken-Zusatz statt einer zweiten, doppelten Warnung.
    entry = _fuel(client, vehicle_id, "2024-03-02", 12_350)
    assert len(entry["warnungen"]) == 1
    assert "weicht stark" in entry["warnungen"][0]
    assert "Seit der vorigen Tankung sind 850 km vergangen" in entry["warnungen"][0]

    assert client.get(f"/api/vehicles/{vehicle_id}/stats").json()["hinweise"] == []
