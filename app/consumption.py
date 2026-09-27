"""
Verbrauchsberechnung (Voll-zu-Voll-Methode), gemeinsam genutzt von den
Statistik-Endpunkten (app/routers/stats.py) und der Plausibilitaetspruefung
neuer Tankeintraege (app/validation.py).
"""
from __future__ import annotations

from collections.abc import Iterable
from types import SimpleNamespace

from app.models import FuelEntry


def verbrauch_l_pro_100km(entries: list[FuelEntry], start_km: int | None = None) -> float | None:
    """entries muss nach kilometerstand aufsteigend sortiert sein und darf nur
    einen Kraftstoff enthalten. Nur Tankungen mit nicht_voll=False gelten als
    verlaessliche Referenzpunkte, weil nur dann klar ist, wie viel Kraftstoff
    seit der letzten Volltankung tatsaechlich verbraucht wurde.

    start_km: optionale zusaetzliche Volltank-Referenz vor allen Eintraegen
    (Kauf-km-Stand bei "bei Kauf vollgetankt")."""
    if start_km is not None:
        referenz = SimpleNamespace(kilometerstand=start_km, fuellmenge_liter=0.0, nicht_voll=False)
        entries = [referenz, *(e for e in entries if e.kilometerstand > start_km)]

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


def verbrauch_je_tankung(entries: Iterable[FuelEntry], start_km: int | None = None) -> dict[int, float]:
    """Verbrauch je Volltankung (entry.id -> l/100 km), Voll-zu-Voll getrennt
    je Kraftstoff: Liter seit der vorigen Volltankung derselben Sorte
    (inkl. Teil-Tankungen dazwischen) geteilt durch die km seitdem."""
    nach_art: dict[str, list] = {}
    for e in sorted(entries, key=lambda e: e.kilometerstand):
        nach_art.setdefault(e.kraftstoffart.value, []).append(e)
    result: dict[int, float] = {}
    for art_entries in nach_art.values():
        kette = list(art_entries)
        if start_km is not None:
            referenz = SimpleNamespace(id=None, kilometerstand=start_km, fuellmenge_liter=0.0, nicht_voll=False)
            kette = [referenz, *(e for e in kette if e.kilometerstand > start_km)]
        letzte_volle = None
        liter_seitdem = 0.0
        for e in kette:
            if letzte_volle is not None:
                liter_seitdem += e.fuellmenge_liter
            if e.nicht_voll:
                continue
            if letzte_volle is not None and e.id is not None:
                km = e.kilometerstand - letzte_volle.kilometerstand
                if km > 0:
                    result[e.id] = round(liter_seitdem / km * 100, 2)
            letzte_volle, liter_seitdem = e, 0.0
    return result


def verbrauch_nach_kraftstoff(entries: Iterable[FuelEntry], start_km: int | None = None) -> dict[str, float]:
    """Voll-zu-Voll getrennt je Kraftstoff - bei bivalenten Fahrzeugen
    (LPG + Benzin) wuerde eine gemeinsame Kette die Tankungen vermischen."""
    nach_art: dict[str, list[FuelEntry]] = {}
    for e in sorted(entries, key=lambda e: e.kilometerstand):
        nach_art.setdefault(e.kraftstoffart.value, []).append(e)
    result = {}
    for art, art_entries in nach_art.items():
        verbrauch = verbrauch_l_pro_100km(art_entries, start_km)
        if verbrauch is not None:
            result[art] = verbrauch
    return result
