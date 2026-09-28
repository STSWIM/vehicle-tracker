"""
Daten fuer die Diagramme: gefahrene km je Tag/Monat/Jahr, Verbrauch und
Spritpreis ueber die Haltedauer.

Gefahrene km: wie in der bisherigen Excel-"Gesamtstatistik" (Spalten
"passender Tageskilometersatz" / "grober Kilometerstand") wird zwischen zwei
bekannten km-Staenden gleichmaessig pro Tag verteilt. Bekannte Staende kommen
aus Tankungen, Fahrten, Logbuch und dem Kauf-km-Stand; einzelne Ausreisser
(Tippfehler) fliegen vorher raus.
"""
from __future__ import annotations

import datetime
from collections import defaultdict

from app.consumption import verbrauch_je_tankung
from app.excel_import import km_ausreisser
from app.models import Vehicle


def km_staende(vehicle: Vehicle) -> list[tuple[datetime.date, int]]:
    """Bekannte km-Staende ohne Ausreisser, nach Datum und km sortiert. Mehrere
    Staende am selben Tag bleiben erhalten (z.B. Kauf und erste Tankung) -
    sonst gingen die dazwischen gefahrenen km verloren."""
    punkte: set[tuple[datetime.date, int]] = set()
    if vehicle.kaufdatum is not None and vehicle.kaufkilometerstand is not None:
        punkte.add((vehicle.kaufdatum, vehicle.kaufkilometerstand))
    punkte.update((e.datum, e.kilometerstand) for e in vehicle.fuel_entries)
    punkte.update((t.datum, km) for t in vehicle.trips for km in (t.km_start, t.km_ende))
    punkte.update((e.datum, e.kilometerstand) for e in vehicle.logbook_entries if e.kilometerstand is not None)

    folge = sorted(punkte)
    ausreisser = km_ausreisser([(d, km, True) for d, km in folge])
    return [p for i, p in enumerate(folge) if i not in ausreisser]


def km_pro_tag(staende: list[tuple[datetime.date, int]]) -> dict[datetime.date, float]:
    """Gefahrene km je Kalendertag, zwischen zwei Staenden gleichmaessig
    verteilt; km zwischen zwei Staenden desselben Tages zaehlen zu diesem Tag."""
    tage: dict[datetime.date, float] = defaultdict(float)
    for (d1, km1), (d2, km2) in zip(staende, staende[1:]):
        anzahl = (d2 - d1).days
        if anzahl <= 0:
            if km2 > km1:
                tage[d2] += km2 - km1
            continue
        rate = (km2 - km1) / anzahl
        for i in range(1, anzahl + 1):
            tage[d1 + datetime.timedelta(days=i)] += rate
    return dict(tage)


def chart_data(vehicle: Vehicle) -> dict:
    tage = km_pro_tag(km_staende(vehicle))
    monate: dict[str, float] = defaultdict(float)
    jahre: dict[str, float] = defaultdict(float)
    for tag, km in tage.items():
        monate[f"{tag:%Y-%m}"] += km
        jahre[f"{tag:%Y}"] += km

    start_km = vehicle.kaufkilometerstand if vehicle.bei_kauf_vollgetankt else None
    verbrauch_je_eintrag = verbrauch_je_tankung(vehicle.fuel_entries, start_km)
    verbrauch: dict[str, list] = defaultdict(list)
    preis: dict[str, list] = defaultdict(list)
    for e in sorted(vehicle.fuel_entries, key=lambda e: (e.datum, e.kilometerstand)):
        art = e.kraftstoffart.value
        preis[art].append([e.datum.isoformat(), round(e.preis_pro_liter, 3)])
        if e.id in verbrauch_je_eintrag:
            verbrauch[art].append([e.datum.isoformat(), verbrauch_je_eintrag[e.id]])

    return {
        "km": {
            "tag": [[t.isoformat(), round(km, 1)] for t, km in sorted(tage.items())],
            "monat": [[m, round(km, 1)] for m, km in sorted(monate.items())],
            "jahr": [[j, round(km, 1)] for j, km in sorted(jahre.items())],
        },
        "verbrauch": dict(verbrauch),
        "preis": dict(preis),
    }
