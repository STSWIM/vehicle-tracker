"""
Regelbasierte Strukturierung des OCR-Rohtexts in die Felder, die der
Tank-Log braucht. Bewusst als erster, deterministischer Durchlauf ohne
LLM gebaut, weil das auf CPU-only-Hardware schnell und kostenlos ist.

Wichtig: das Ergebnis ist ein *Vorschlag* mit Konfidenzwert. Der Talk-Bot
schickt ihn zur Bestaetigung zurueck (app/talk_bot/session.py) – nichts
wird ungeprueft gespeichert. Faelle, die der Parser nicht sicher genug
einordnen kann, sollten spaeter an app/ocr/llm_fallback.py weitergereicht
werden (aktuell deaktiviert, siehe README).
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field

from app.models import Kraftstoffart
from app.ocr.engine import OcrResult

_DATE_RE = re.compile(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})\b")

# Bewusst nur Komma als Dezimaltrennzeichen (deutsches Format auf Bons).
# Mit Punkt wuerde z.B. "24.06" aus einem Datum faelschlich als Geldbetrag
# 2406,0 interpretiert werden.
_MONEY_RE = re.compile(r"(\d{1,4},\d{2})\s*(?:€|EUR)?")
_PRICE_PER_LITER_RE = re.compile(r"(\d,\d{3})\s*(?:€|EUR)?\s*/?\s*[lL]")
_LITER_RE = re.compile(r"(\d{1,3},\d{2})\s*[lL](?:iter)?\b")
_DIGITS_RE = re.compile(r"\b(\d{4,7})\b")

_FUEL_KEYWORDS = {
    Kraftstoffart.LPG: ("LPG", "AUTOGAS", "GAS"),
    Kraftstoffart.BENZIN: ("SUPER", "BENZIN", "E10", "E5"),
    Kraftstoffart.DIESEL: ("DIESEL",),
}


def _to_float(value: str) -> float:
    return float(value.replace(".", "").replace(",", "."))


@dataclass
class BelegVorschlag:
    datum: datetime.date | None = None
    gesamtpreis: float | None = None
    preis_pro_liter: float | None = None
    fuellmenge_liter: float | None = None
    kraftstoffart: Kraftstoffart | None = None
    tankstelle_name: str | None = None
    konfidenz: float = 0.0
    warnungen: list[str] = field(default_factory=list)


def parse_beleg(ocr: OcrResult) -> BelegVorschlag:
    text = ocr.full_text
    text_upper = text.upper()
    vorschlag = BelegVorschlag(konfidenz=ocr.mean_confidence)

    # Datum: nimm das erste plausible Datum (meist oben auf dem Bon)
    m = _DATE_RE.search(text)
    if m:
        tag, monat, jahr = (int(g) for g in m.groups())
        if jahr < 100:
            jahr += 2000
        try:
            vorschlag.datum = datetime.date(jahr, monat, tag)
        except ValueError:
            vorschlag.warnungen.append(f"Unplausibles Datum erkannt: {m.group(0)}")

    # Preis pro Liter: typischerweise 3 Nachkommastellen (z.B. 1,749)
    m = _PRICE_PER_LITER_RE.search(text)
    if m:
        vorschlag.preis_pro_liter = _to_float(m.group(1))

    # Füllmenge in Litern
    m = _LITER_RE.search(text)
    if m:
        vorschlag.fuellmenge_liter = _to_float(m.group(1))

    # Gesamtpreis: groesster gefundener Geldbetrag (typische Bon-Heuristik)
    betraege = [_to_float(g) for g in _MONEY_RE.findall(text)]
    if betraege:
        vorschlag.gesamtpreis = max(betraege)

    # Plausibilitaets-Check / Korrektur: wenn Menge * Preis/Liter deutlich
    # vom erkannten Gesamtpreis abweicht, eher der Rechnung vertrauen und
    # warnen statt stillschweigend zu uebernehmen.
    if vorschlag.fuellmenge_liter and vorschlag.preis_pro_liter and vorschlag.gesamtpreis:
        erwartet = round(vorschlag.fuellmenge_liter * vorschlag.preis_pro_liter, 2)
        if abs(erwartet - vorschlag.gesamtpreis) > 0.5:
            vorschlag.warnungen.append(
                f"Menge×Preis ({erwartet}€) passt nicht zum erkannten "
                f"Gesamtpreis ({vorschlag.gesamtpreis}€) – bitte pruefen."
            )

    for art, keywords in _FUEL_KEYWORDS.items():
        if any(kw in text_upper for kw in keywords):
            vorschlag.kraftstoffart = art
            break

    if not vorschlag.gesamtpreis or not vorschlag.datum:
        vorschlag.warnungen.append("Nicht alle Pflichtfelder sicher erkannt.")

    return vorschlag


@dataclass
class TachoVorschlag:
    kilometerstand: int | None = None
    konfidenz: float = 0.0
    warnungen: list[str] = field(default_factory=list)


def parse_tacho(ocr: OcrResult) -> TachoVorschlag:
    """Odometer-Fotos zeigen oft mehrere Zahlengruppen (Gesamt-km,
    Tageskilometerzaehler, Uhrzeit). Heuristik: die laengste Ziffernfolge
    ist meistens der Gesamtkilometerstand."""
    vorschlag = TachoVorschlag(konfidenz=ocr.mean_confidence)

    kandidaten = _DIGITS_RE.findall(ocr.full_text)
    if not kandidaten:
        vorschlag.warnungen.append("Keine Zahl erkannt – Foto ggf. erneut aufnehmen.")
        return vorschlag

    kandidaten.sort(key=len, reverse=True)
    vorschlag.kilometerstand = int(kandidaten[0])

    if len(kandidaten) > 1:
        vorschlag.warnungen.append(
            "Mehrere Zahlengruppen erkannt – bitte Kilometerstand im Chat bestätigen."
        )

    return vorschlag
