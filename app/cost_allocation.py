"""
Anteilige Kosten: im Voraus bezahlte Posten ueber ihre Laufzeit verteilen.

Versicherung und Kfz-Steuer werden fuer ein Jahr im Voraus bezahlt, eine
Finanzierungsrate fuer einen Monat. Wie in der bisherigen Excel-Buchfuehrung
("Versicherungskosten / Tag bis heute") zaehlt in einer Auswertung nur der
Anteil, der auf den betrachteten Zeitraum entfaellt - hoechstens bis heute
bzw. bis zum Verkauf. Der Rest ist im Voraus bezahlt und wuerde bei einem
Verkauf erstattet.

OtherCost.laufzeit_monate: None = Vorgabe der Kategorie, 0 = voll am
Zahltag (z.B. Zulassung unter "Steuer"), n = gleichmaessig ueber n Monate
ab dem Zahltag verteilt.
"""
from __future__ import annotations

import calendar
import datetime

from app.models import Kostenkategorie, OtherCost

STANDARD_LAUFZEIT_MONATE = {
    Kostenkategorie.VERSICHERUNG: 12,
    Kostenkategorie.STEUER: 12,
    Kostenkategorie.FINANZIERUNG: 1,
}


def laufzeit_monate(cost: OtherCost) -> int:
    if cost.laufzeit_monate is not None:
        return cost.laufzeit_monate
    return STANDARD_LAUFZEIT_MONATE.get(cost.kategorie, 0)


def _plus_monate(datum: datetime.date, monate: int) -> datetime.date:
    jahr, monat = divmod(datum.month - 1 + monate, 12)
    jahr += datum.year
    tag = min(datum.day, calendar.monthrange(jahr, monat + 1)[1])
    return datetime.date(jahr, monat + 1, tag)


def gueltig_bis(cost: OtherCost) -> datetime.date | None:
    """Letzter Tag, den die Zahlung abdeckt (None = kein Zeitraum)."""
    monate = laufzeit_monate(cost)
    if monate <= 0:
        return None
    return _plus_monate(cost.datum, monate) - datetime.timedelta(days=1)


def anteil(cost: OtherCost, von: datetime.date | None, bis: datetime.date) -> float:
    """Betrag, der auf die Tage von..bis (jeweils einschliesslich) entfaellt."""
    ende = gueltig_bis(cost)
    if ende is None:
        return cost.betrag if (von is None or cost.datum >= von) and cost.datum <= bis else 0.0
    tage_gesamt = (ende - cost.datum).days + 1
    start = cost.datum if von is None else max(cost.datum, von)
    stop = min(ende, bis)
    tage = (stop - start).days + 1
    if tage <= 0:
        return 0.0
    return cost.betrag * tage / tage_gesamt


def vorausbezahlt(cost: OtherCost, stichtag: datetime.date) -> float:
    """Noch nicht verbrauchter Anteil nach dem Stichtag (bei Verkauf erstattet)."""
    ende = gueltig_bis(cost)
    if ende is None or ende <= stichtag or cost.datum > stichtag:
        return 0.0
    return cost.betrag - anteil(cost, None, stichtag)
