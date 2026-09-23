"""
End-to-End-Test ueber die REST-API: repliziert das Szenario, mit dem die
Statistik-Berechnung waehrend der Entwicklung manuell verifiziert wurde
(drei Tankeintraege + eine sonstige Kostenposition), diesmal als
automatisierter Regressionstest.
"""


def _seed_vehicle(client):
    response = client.post(
        "/api/vehicles",
        json={
            "kennzeichen": "RT-WI 14",
            "hersteller": "Toyota",
            "modell": "Previa",
            "tankvolumen_lpg_l": 54,
            "tankvolumen_benzin_l": 75,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_stats_verbrauch_und_kosten(client):
    vehicle_id = _seed_vehicle(client)

    entries = [
        # (datum, km, menge, preis_pro_liter, gesamtpreis, nicht_voll)
        ("2022-06-24", 158947, 30.37, 1.099, 33.38, False),
        ("2022-07-10", 159131, 16.96, 1.079, 16.96, True),
        ("2022-08-05", 159514, 48.99, 1.039, 48.99, False),
    ]
    for datum, km, menge, preis, gesamt, nicht_voll in entries:
        response = client.post(
            "/api/fuel-entries",
            json={
                "vehicle_id": vehicle_id,
                "datum": datum,
                "kilometerstand": km,
                "kraftstoffart": "LPG",
                "fuellmenge_liter": menge,
                "preis_pro_liter": preis,
                "gesamtpreis": gesamt,
                "nicht_voll": nicht_voll,
            },
        )
        assert response.status_code == 201, response.text

    response = client.post(
        "/api/other-costs",
        json={
            "vehicle_id": vehicle_id,
            "datum": "2022-07-25",
            "kategorie": "Versicherung",
            "betrag": 259.41,
            "beschreibung": "KFZ Versicherung",
        },
    )
    assert response.status_code == 201, response.text

    stats = client.get(f"/api/vehicles/{vehicle_id}/stats").json()

    assert stats["gefahrene_km"] == 567.0
    assert stats["gesamt_kraftstoffkosten"] == 99.33
    assert stats["gesamt_sonstige_kosten"] == 259.41
    assert stats["gesamtkosten"] == 358.74
    # Voll-zu-Voll: (16.96 + 48.99) l / 567 km * 100
    assert stats["ø_verbrauch_l_100km"] == 11.63
    assert stats["anteil_lpg"] == 1.0
    assert stats["anteil_benzin"] == 0.0


def test_stats_ohne_eintraege_wirft_keinen_fehler(client):
    vehicle_id = _seed_vehicle(client)
    response = client.get(f"/api/vehicles/{vehicle_id}/stats")
    assert response.status_code == 200
    stats = response.json()
    assert stats["gefahrene_km"] == 0.0
    assert stats["ø_verbrauch_l_100km"] is None
    assert stats["kosten_pro_km"] is None
