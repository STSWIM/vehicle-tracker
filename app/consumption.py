"""
Verbrauchsberechnung (Voll-zu-Voll-Methode), gemeinsam genutzt von den
Statistik-Endpunkten (app/routers/stats.py) und der Plausibilitaetspruefung
neuer Tankeintraege (app/validation.py).
"""
from __future__ import annotations

from app.models import FuelEntry


def verbrauch_l_pro_100km(entries: list[FuelEntry]) -> float | None:
    """entries muss nach kilometerstand aufsteigend sortiert sein. Nur
    Tankungen mit nicht_voll=False gelten als verlaessliche Referenzpunkte,
    weil nur dann klar ist, wie viel Kraftstoff seit der letzten
    Volltankung tatsaechlich verbraucht wurde."""
    volltankungen_idx = [i for i, e in enumerate(entries) if not e.nicht_voll]
    if len(volltankungen_idx) < 2:
        return None

    gesamt_liter = 0.0
    gesamt_km = 0
    for a, b in zip(volltankungen_idx, volltankungen_idx[1:]):
        segment = entries[a + 1 : b + 1]  # alles bis inkl. der naechsten Volltankung
        liter = sum(e.fuellmenge_liter for e in segment)
        km = entries[b].kilometerstand - entries[a].kilometerstand
        if km > 0:
            gesamt_liter += liter
            gesamt_km += km

    if gesamt_km == 0:
        return None
    return gesamt_liter / gesamt_km * 100
