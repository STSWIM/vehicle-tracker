"""
Tests fuer den regelbasierten Beleg-/Tacho-Parser (app/ocr/parser.py).
Nutzt synthetische OcrResult-Objekte statt echter Fotos/PaddleOCR, damit
die Tests ohne die schwere OCR-Engine laufen (siehe requirements-dev.txt).
"""
from app.models import Kraftstoffart
from app.ocr.engine import OcrLine, OcrResult
from app.ocr.parser import parse_beleg, parse_tacho


def _ocr(lines: list[str], confidence: float = 0.95) -> OcrResult:
    return OcrResult(lines=[OcrLine(text=t, confidence=confidence) for t in lines])


def test_parse_beleg_erkennt_alle_felder():
    ocr = _ocr(
        ["TOTAL TANKSTELLE", "24.06.2022", "LPG", "30,37 l", "1,099 EUR/l", "Gesamt 33,38 EUR"]
    )
    vorschlag = parse_beleg(ocr)

    assert vorschlag.datum.isoformat() == "2022-06-24"
    assert vorschlag.fuellmenge_liter == 30.37
    assert vorschlag.preis_pro_liter == 1.099
    assert vorschlag.gesamtpreis == 33.38
    assert vorschlag.kraftstoffart == Kraftstoffart.LPG
    assert vorschlag.warnungen == []


def test_parse_beleg_verwechselt_datum_nicht_mit_geldbetrag():
    """Regressionstest: '24.06' (Teil des Datums) wurde frueher faelschlich
    als Geldbetrag 2406,0 interpretiert, weil die Money-Regex auch Punkt
    als Dezimaltrennzeichen akzeptiert hat."""
    ocr = _ocr(["24.06.2022", "Gesamt 33,38 EUR"])
    vorschlag = parse_beleg(ocr)
    assert vorschlag.gesamtpreis == 33.38


def test_parse_beleg_warnt_bei_unplausibler_menge_mal_preis():
    ocr = _ocr(["24.06.2022", "30,37 l", "1,099 EUR/l", "Gesamt 99,99 EUR"])
    vorschlag = parse_beleg(ocr)
    assert any("passt nicht" in w for w in vorschlag.warnungen)


def test_parse_tacho_findet_laengste_zahl():
    ocr = _ocr(["158947", "km", "12:45"])
    vorschlag = parse_tacho(ocr)
    assert vorschlag.kilometerstand == 158947


def test_parse_tacho_ohne_zahl_gibt_warnung():
    ocr = _ocr(["kein Text mit Ziffern"])
    vorschlag = parse_tacho(ocr)
    assert vorschlag.kilometerstand is None
    assert vorschlag.warnungen
