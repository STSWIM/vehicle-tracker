"""Anteilige Kosten: Versicherung/Steuer/Finanzierung ueber die Laufzeit verteilen."""
import datetime
from types import SimpleNamespace

import pytest

from app.cost_allocation import anteil, gueltig_bis, laufzeit_monate, vorausbezahlt
from app.models import Kostenkategorie

D = datetime.date


def cost(kategorie, betrag, datum, laufzeit=None):
    return SimpleNamespace(kategorie=kategorie, betrag=betrag, datum=datum, laufzeit_monate=laufzeit)


def test_vorgaben_je_kategorie():
    assert laufzeit_monate(cost(Kostenkategorie.VERSICHERUNG, 1, D(2024, 1, 1))) == 12
    assert laufzeit_monate(cost(Kostenkategorie.STEUER, 1, D(2024, 1, 1))) == 12
    assert laufzeit_monate(cost(Kostenkategorie.FINANZIERUNG, 1, D(2024, 1, 1))) == 1
    assert laufzeit_monate(cost(Kostenkategorie.WASCHEN, 1, D(2024, 1, 1))) == 0
    # ausdruecklich 0: Zulassung unter "Steuer" zaehlt voll
    assert laufzeit_monate(cost(Kostenkategorie.STEUER, 1, D(2024, 1, 1), laufzeit=0)) == 0


def test_gueltig_bis():
    assert gueltig_bis(cost(Kostenkategorie.VERSICHERUNG, 1, D(2023, 3, 15))) == D(2024, 3, 14)
    assert gueltig_bis(cost(Kostenkategorie.FINANZIERUNG, 1, D(2024, 1, 31))) == D(2024, 2, 28)
    assert gueltig_bis(cost(Kostenkategorie.WASCHEN, 1, D(2024, 1, 1))) is None


def test_versicherung_anteilig_bis_stichtag():
    # 365 € fuer 2023 (365 Tage): bis 30.06. sind 181 Tage vergangen
    c = cost(Kostenkategorie.VERSICHERUNG, 365.0, D(2023, 1, 1))
    assert anteil(c, None, D(2023, 6, 30)) == pytest.approx(181.0)
    assert vorausbezahlt(c, D(2023, 6, 30)) == pytest.approx(184.0)
    # nach Ablauf zaehlt alles, nichts mehr im Voraus bezahlt
    assert anteil(c, None, D(2025, 1, 1)) == pytest.approx(365.0)
    assert vorausbezahlt(c, D(2025, 1, 1)) == 0.0


def test_zeitraum_schneidet_laufzeit():
    # im Dezember 2022 fuer ein Jahr bezahlt - in 2023 fallen 334 von 365 Tagen an
    c = cost(Kostenkategorie.VERSICHERUNG, 365.0, D(2022, 12, 1))
    assert anteil(c, D(2023, 1, 1), D(2023, 12, 31)) == pytest.approx(334.0)
    assert anteil(c, D(2024, 1, 1), D(2024, 12, 31)) == 0.0


def test_einmalige_kosten_voll_am_zahltag():
    c = cost(Kostenkategorie.STEUER, 45.9, D(2022, 6, 24), laufzeit=0)
    assert anteil(c, None, D(2022, 6, 24)) == 45.9
    assert anteil(c, D(2022, 7, 1), D(2022, 12, 31)) == 0.0
    assert vorausbezahlt(c, D(2022, 6, 24)) == 0.0
