"""
Export fuer Steuerberater bzw. Fahrzeugverkauf (Issue #14): alle Eintraege
eines Zeitraums als CSV (fuer ein deutsches Excel: Semikolon, UTF-8 mit BOM,
Dezimalkomma, Datum TT.MM.JJJJ) und als A4-PDF-Bericht mit denselben
Kennzahlen wie die Auswertung (app.routers.stats.compute_vehicle_stats) plus
vollstaendiger Wartungshistorie.

Der PDF-Bericht nutzt fpdf2 mit einer Unicode-TTF-Schrift (DejaVu Sans, im
Docker-Image ueber das Paket fonts-dejavu-core). Fehlt sie (z.B. in der
Test-Umgebung), faellt er auf die Core-Schrift Helvetica in Windows-1252
zurueck - Umlaute, ß und € gehen damit weiterhin, nur exotischere Zeichen
werden ersetzt.
"""
from __future__ import annotations

import csv
import datetime
import io
import os
import re
from collections import defaultdict
from dataclasses import dataclass

from app.models import FuelEntry, Kostenkategorie, LogbookEntry, OtherCost, Trip, Vehicle
from app.schemas import VehicleStats

# --- Zeitraum ----------------------------------------------------------------


@dataclass
class ExportData:
    vehicle: Vehicle
    von: datetime.date | None
    bis: datetime.date | None
    fuel_entries: list[FuelEntry]
    other_costs: list[OtherCost]
    logbook: list[LogbookEntry]
    trips: list[Trip]


def collect(vehicle: Vehicle, von: datetime.date | None, bis: datetime.date | None) -> ExportData:
    """Eintraege im Zeitraum (gleiche Grenzen wie die Statistik: inklusive)."""

    def im_zeitraum(datum: datetime.date) -> bool:
        return (von is None or datum >= von) and (bis is None or datum <= bis)

    return ExportData(
        vehicle=vehicle,
        von=von,
        bis=bis,
        fuel_entries=sorted(
            (e for e in vehicle.fuel_entries if im_zeitraum(e.datum)), key=lambda e: (e.datum, e.kilometerstand)
        ),
        other_costs=sorted((c for c in vehicle.other_costs if im_zeitraum(c.datum)), key=lambda c: c.datum),
        logbook=sorted(
            (entry for entry in vehicle.logbook_entries if im_zeitraum(entry.datum)),
            key=lambda entry: (entry.datum, entry.kilometerstand or 0),
        ),
        trips=sorted((t for t in vehicle.trips if im_zeitraum(t.datum)), key=lambda t: (t.datum, t.km_start)),
    )


def export_filename(vehicle: Vehicle, von: datetime.date | None, bis: datetime.date | None, ext: str) -> str:
    """z.B. RT-WI_14_2024-01-01_bis_2024-12-31.csv - nur ASCII, damit der
    Name in jedem Browser/Betriebssystem ohne Umkodierung ankommt."""
    kennzeichen = re.sub(r"[^A-Za-z0-9-]+", "_", vehicle.kennzeichen or "fahrzeug").strip("_") or "fahrzeug"
    if von is None and bis is None:
        zeitraum = "gesamt"
    else:
        zeitraum = f"{von.isoformat() if von else 'anfang'}_bis_{bis.isoformat() if bis else 'heute'}"
    return f"{kennzeichen}_{zeitraum}.{ext}"


# --- Formatierung (deutsch) --------------------------------------------------


def fmt_date(value: datetime.date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def fmt_num(value: float | int | None, digits: int = 2, thousands: bool = False) -> str:
    """Dezimalkomma; Tausenderpunkte nur fuer die Anzeige im PDF - in der CSV
    ohne, damit Excel die Zahl sicher als Zahl erkennt."""
    if value is None:
        return ""
    text = f"{value:,.{digits}f}" if thousands else f"{value:.{digits}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _erfasst_von(entry) -> str:
    # Spalte kommt ggf. erst mit einer spaeteren Migration dazu.
    return getattr(entry, "erfasst_von", None) or ""


def _hat_erfasst_von() -> bool:
    return any(hasattr(model, "erfasst_von") for model in (FuelEntry, OtherCost, LogbookEntry, Trip))


# --- CSV -----------------------------------------------------------------------

CSV_HEADER = [
    "Typ",
    "Datum",
    "km-Stand",
    "Kategorie/Kraftstoff",
    "Liter",
    "Preis/Liter (EUR)",
    "Betrag (EUR)",
    "Strecke (km)",
    "Beschreibung/Notiz",
]

_TYP_REIHENFOLGE = {"Tankung": 0, "Kosten": 1, "Logbuch": 2, "Fahrt": 3}


def build_csv(data: ExportData) -> bytes:
    mit_erfasst_von = _hat_erfasst_von()
    rows: list[tuple[datetime.date, str, list[str]]] = []

    for e in data.fuel_entries:
        notiz = [e.tankstelle_name or ""]
        if e.nicht_voll:
            notiz.append("nicht vollgetankt")
        rows.append((e.datum, "Tankung", [
            fmt_num(e.kilometerstand, 0), e.kraftstoffart.value, fmt_num(e.fuellmenge_liter, 2),
            fmt_num(e.preis_pro_liter, 3), fmt_num(e.gesamtpreis, 2), "",
            ", ".join(n for n in notiz if n), _erfasst_von(e),
        ]))
    for c in data.other_costs:
        rows.append((c.datum, "Kosten", [
            "", c.kategorie.value, "", "", fmt_num(c.betrag, 2), "", c.beschreibung or "", _erfasst_von(c),
        ]))
    for entry in data.logbook:
        text = entry.eintrag + (f" – {entry.notiz}" if entry.notiz else "")
        rows.append((entry.datum, "Logbuch", [
            fmt_num(entry.kilometerstand, 0), "", "", "", "", "", text, _erfasst_von(entry),
        ]))
    for t in data.trips:
        text = f"{t.start} – {t.ziel}" + (f" ({t.notiz})" if t.notiz else "")
        rows.append((t.datum, "Fahrt", [
            fmt_num(t.km_ende, 0), t.zweck.value, "", "", "", fmt_num(t.km_ende - t.km_start, 0), text,
            _erfasst_von(t),
        ]))

    rows.sort(key=lambda r: (r[0], _TYP_REIHENFOLGE[r[1]]))

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(CSV_HEADER + (["Erfasst von"] if mit_erfasst_von else []))
    for datum, typ, rest in rows:
        values = rest if mit_erfasst_von else rest[:-1]
        writer.writerow([typ, fmt_date(datum), *(_csv_safe(v) for v in values)])
    return buffer.getvalue().encode("utf-8-sig")


def _csv_safe(value: str) -> str:
    """Freitext, der mit =, +, - oder @ beginnt, wuerde Excel als Formel
    ausfuehren (CSV-Injection) - ein vorangestelltes Apostroph verhindert das.
    Zahlen (auch negative Betraege wie -12,50) bleiben unveraendert."""
    if value and value[0] in "=+-@" and not re.fullmatch(r"-?[\d.]+(,\d+)?", value):
        return "'" + value
    return value


# --- PDF -------------------------------------------------------------------------

FONT_DIRS = (
    "/usr/share/fonts/truetype/dejavu",  # Debian/Ubuntu (fonts-dejavu-core)
    "/usr/share/fonts/dejavu",
    "/usr/share/fonts/TTF",
    "/Library/Fonts",
    "C:/Windows/Fonts",
)


def find_unicode_font() -> tuple[str, str] | None:
    """(regular, bold) von DejaVu Sans, falls installiert. VT_PDF_FONT_DIR
    erlaubt ein anderes Verzeichnis."""
    dirs = [os.environ["VT_PDF_FONT_DIR"]] if os.environ.get("VT_PDF_FONT_DIR") else []
    for directory in [*dirs, *FONT_DIRS]:
        regular = os.path.join(directory, "DejaVuSans.ttf")
        bold = os.path.join(directory, "DejaVuSans-Bold.ttf")
        if os.path.isfile(regular):
            return regular, bold if os.path.isfile(bold) else regular
    return None


def _eur(value: float | None) -> str:
    return "–" if value is None else f"{fmt_num(value, 2, thousands=True)} €"


def build_pdf(data: ExportData, stats: VehicleStats) -> bytes:
    from fpdf import FPDF
    from fpdf.fonts import FontFace

    erstellt = datetime.datetime.now()
    font = find_unicode_font()

    class Report(FPDF):
        def footer(self) -> None:
            self.set_y(-12)
            self.set_font(family, "", 8)
            self.set_text_color(110)
            self.cell(0, 5, txt(f"Fahrzeugbericht {data.vehicle.kennzeichen} · erstellt am "
                                f"{erstellt.strftime('%d.%m.%Y %H:%M')}"), align="L")
            self.set_x(self.l_margin)
            self.cell(0, 5, txt(f"Seite {self.page_no()} von {{nb}}"), align="R")
            self.set_text_color(0)

    pdf = Report(format="A4", unit="mm")
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(True, margin=18)
    pdf.set_title(f"Fahrzeugbericht {data.vehicle.kennzeichen}")
    pdf.set_creator("Fahrzeug Buchführung (Nextcloud)")

    if font:
        family = "DejaVu"
        pdf.add_font(family, "", font[0])
        pdf.add_font(family, "B", font[1])

        def txt(value: str) -> str:
            return value
    else:
        family = "Helvetica"
        pdf.core_fonts_encoding = "windows-1252"

        def txt(value: str) -> str:
            return value.encode("cp1252", "replace").decode("cp1252")

    heading_style = FontFace(family=family, emphasis="BOLD", fill_color=(225, 230, 236))
    grau = (245, 246, 248)

    def h1(text: str) -> None:
        pdf.set_font(family, "B", 17)
        pdf.cell(0, 9, txt(text), new_x="LMARGIN", new_y="NEXT")

    def h2(text: str) -> None:
        if pdf.get_y() > pdf.h - 45:  # Ueberschrift nicht allein unten auf der Seite
            pdf.add_page()
        pdf.ln(4)
        pdf.set_font(family, "B", 12)
        pdf.cell(0, 7, txt(text), new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(160)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(2)

    def hinweis(text: str) -> None:
        pdf.set_font(family, "", 9)
        pdf.set_text_color(90)
        pdf.multi_cell(0, 5, txt(text), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0)

    def table(header: list[str], rows: list[list[str]], widths: tuple, align: tuple, width: float | None = None,
              font_size: float = 8.5) -> None:
        pdf.set_font(family, "", font_size)
        pdf.set_draw_color(200)
        with pdf.table(
            width=width or pdf.epw,
            col_widths=widths,
            text_align=align,
            align="LEFT",
            headings_style=heading_style,
            borders_layout="HORIZONTAL_LINES",
            cell_fill_color=grau,
            cell_fill_mode="ROWS",
            line_height=font_size * 0.55,
            padding=(1, 1.5),
        ) as t:
            for values in [header, *rows]:
                row = t.row()
                for value in values:
                    row.cell(txt(value))
        pdf.ln(1)

    def kv_table(rows: list[tuple[str, str]], width: float = 120) -> None:
        pdf.set_font(family, "", 9.5)
        pdf.set_draw_color(215)
        with pdf.table(
            width=width, col_widths=(55, 65), text_align=("LEFT", "RIGHT"), align="LEFT",
            first_row_as_headings=False, borders_layout="HORIZONTAL_LINES", line_height=5.2,
            padding=(0.8, 1.5),
        ) as t:
            for label, value in rows:
                row = t.row()
                row.cell(txt(label))
                row.cell(txt(value))

    v = data.vehicle
    pdf.add_page()

    # --- Kopf -------------------------------------------------------------------
    h1(f"Fahrzeugbericht {v.kennzeichen}")
    pdf.set_font(family, "", 11)
    pdf.cell(0, 6, txt(" ".join(p for p in (v.hersteller, v.modell, v.variante) if p)),
             new_x="LMARGIN", new_y="NEXT")
    if stats.zeitraum_von:
        zeitraum = f"{fmt_date(stats.zeitraum_von)} – {fmt_date(stats.zeitraum_bis)}"
    else:
        zeitraum = "keine Einträge"
    if data.von is None and data.bis is None:
        zeitraum = f"Gesamter Zeitraum ({zeitraum})"
    pdf.set_font(family, "", 10)
    pdf.cell(0, 6, txt(f"Auswertungszeitraum: {zeitraum}"), new_x="LMARGIN", new_y="NEXT")

    h2("Fahrzeugdaten")
    fahrzeug = [
        ("Kennzeichen", v.kennzeichen),
        ("Hersteller / Modell", " ".join(p for p in (v.hersteller, v.modell) if p)),
    ]
    if v.variante:
        fahrzeug.append(("Variante", v.variante))
    fahrzeug += [
        ("Kaufdatum", fmt_date(v.kaufdatum) or "–"),
        ("Kaufpreis", _eur(v.kaufpreis)),
        ("km-Stand bei Kauf", f"{fmt_num(v.kaufkilometerstand, 0, thousands=True)} km"
         if v.kaufkilometerstand is not None else "–"),
    ]
    if v.verkauft_am:
        fahrzeug.append(("Verkauft am", fmt_date(v.verkauft_am)))
    km_werte = [e.kilometerstand for e in v.fuel_entries] + [t.km_ende for t in v.trips]
    km_werte += [e.kilometerstand for e in v.logbook_entries if e.kilometerstand is not None]
    if km_werte:
        fahrzeug.append(("Letzter erfasster km-Stand", f"{fmt_num(max(km_werte), 0, thousands=True)} km"))
    kv_table(fahrzeug)

    # --- Zusammenfassung --------------------------------------------------------
    h2("Zusammenfassung")
    anschaffung_label = "Anschaffungskosten" + ("" if stats.mit_anschaffung else " (nicht in Gesamtkosten)")
    zusammenfassung = [
        ("Gesamtkosten", _eur(stats.gesamtkosten)),
        ("Kraftstoffkosten", _eur(stats.gesamt_kraftstoffkosten)),
        ("Laufende Kosten", _eur(stats.gesamt_sonstige_kosten)),
        (anschaffung_label, _eur(stats.anschaffungskosten)),
        ("Gefahrene km", f"{fmt_num(stats.gefahrene_km, 0, thousands=True)} km"),
        ("Kosten pro km", f"{fmt_num(stats.kosten_pro_km, 3)} €" if stats.kosten_pro_km is not None else "–"),
        ("Kosten pro Monat", _eur(stats.kosten_pro_monat)),
    ]
    kv_table(zusammenfassung)

    if stats.kosten_nach_kategorie:
        h2("Laufende Kosten nach Kategorie")
        kategorien = sorted(stats.kosten_nach_kategorie.items(), key=lambda kv: -kv[1])
        table(["Kategorie", "Betrag"], [[k, _eur(b)] for k, b in kategorien],
              (70, 40), ("LEFT", "RIGHT"), width=110, font_size=9)

    if data.fuel_entries:
        h2("Kraftstoff und Verbrauch")
        je_art: dict[str, list[FuelEntry]] = defaultdict(list)
        for e in data.fuel_entries:
            je_art[e.kraftstoffart.value].append(e)
        rows = []
        for art, entries in je_art.items():
            liter = sum(e.fuellmenge_liter for e in entries)
            kosten = sum(e.gesamtpreis for e in entries)
            verbrauch = stats.verbrauch_nach_kraftstoff.get(art)
            rows.append([
                art, str(len(entries)), f"{fmt_num(liter, 2, thousands=True)} l", _eur(kosten),
                f"{fmt_num(kosten / liter, 3)} €" if liter else "–",
                fmt_num(verbrauch, 2) if verbrauch is not None else "–",
            ])
        table(["Kraftstoff", "Tankungen", "Menge", "Kosten", "Ø Preis/l", "Ø l/100 km"], rows,
              (26, 24, 30, 30, 24, 26), ("LEFT", "RIGHT", "RIGHT", "RIGHT", "RIGHT", "RIGHT"), font_size=9)
        if len(stats.verbrauch_nach_kraftstoff) < len(je_art):
            hinweis("Verbrauch nach der Voll-zu-Voll-Methode – braucht mindestens zwei Volltankungen "
                    "desselben Kraftstoffs im Zeitraum.")

    # --- Einzelaufstellungen ----------------------------------------------------
    h2(f"Tankungen ({len(data.fuel_entries)})")
    if data.fuel_entries:
        table(
            ["Datum", "km-Stand", "Kraftstoff", "Liter", "€/l", "Betrag", "Tankstelle / Hinweis"],
            [[
                fmt_date(e.datum), fmt_num(e.kilometerstand, 0, thousands=True), e.kraftstoffart.value,
                fmt_num(e.fuellmenge_liter, 2), fmt_num(e.preis_pro_liter, 3), _eur(e.gesamtpreis),
                ", ".join(p for p in (e.tankstelle_name, "nicht voll" if e.nicht_voll else None) if p),
            ] for e in data.fuel_entries]
            + [["Summe", "", "", fmt_num(sum(e.fuellmenge_liter for e in data.fuel_entries), 2, thousands=True),
                "", _eur(sum(e.gesamtpreis for e in data.fuel_entries)), ""]],
            (19, 18, 20, 15, 13, 21, 54), ("LEFT", "RIGHT", "LEFT", "RIGHT", "RIGHT", "RIGHT", "LEFT"),
        )
    else:
        hinweis("Keine Tankungen im Zeitraum.")

    h2(f"Sonstige Kosten ({len(data.other_costs)})")
    if data.other_costs:
        table(
            ["Datum", "Kategorie", "Betrag", "Beschreibung"],
            [[fmt_date(c.datum), c.kategorie.value, _eur(c.betrag), c.beschreibung or ""] for c in data.other_costs]
            + [["Summe", "", _eur(sum(c.betrag for c in data.other_costs)), ""]],
            (19, 28, 22, 91), ("LEFT", "LEFT", "RIGHT", "LEFT"),
        )
        if any(c.kategorie == Kostenkategorie.EINMALIG for c in data.other_costs):
            hinweis("Kosten der Kategorie „Einmalig“ zählen in der Zusammenfassung zu den Anschaffungskosten, "
                    "nicht zu den laufenden Kosten.")
    else:
        hinweis("Keine sonstigen Kosten im Zeitraum.")

    h2(f"Wartungslogbuch ({len(data.logbook)})")
    if data.logbook:
        table(
            ["Datum", "km-Stand", "Eintrag", "Notiz"],
            [[fmt_date(entry.datum), fmt_num(entry.kilometerstand, 0, thousands=True), entry.eintrag,
              entry.notiz or ""] for entry in data.logbook],
            (19, 19, 55, 67), ("LEFT", "RIGHT", "LEFT", "LEFT"),
        )
    else:
        hinweis("Keine Logbucheinträge im Zeitraum.")

    h2(f"Fahrtenbuch ({len(data.trips)} Fahrten)")
    if data.trips:
        je_zweck: dict[str, list[Trip]] = defaultdict(list)
        for t in data.trips:
            je_zweck[t.zweck.value].append(t)
        gesamt_km = sum(t.km_ende - t.km_start for t in data.trips)
        rows = []
        for zweck, trips in sorted(je_zweck.items()):
            km = sum(t.km_ende - t.km_start for t in trips)
            rows.append([zweck, str(len(trips)), f"{fmt_num(km, 0, thousands=True)} km",
                         f"{fmt_num(km / gesamt_km * 100, 1)} %" if gesamt_km else "–"])
        rows.append(["Gesamt", str(len(data.trips)), f"{fmt_num(gesamt_km, 0, thousands=True)} km", ""])
        table(["Zweck", "Fahrten", "Strecke", "Anteil"], rows, (40, 20, 30, 20),
              ("LEFT", "RIGHT", "RIGHT", "RIGHT"), width=110, font_size=9)
        pdf.ln(2)
        table(
            ["Datum", "Start", "Ziel", "km Start", "km Ende", "Strecke", "Zweck"],
            [[fmt_date(t.datum), t.start, t.ziel, fmt_num(t.km_start, 0, thousands=True),
              fmt_num(t.km_ende, 0, thousands=True), fmt_num(t.km_ende - t.km_start, 0, thousands=True),
              t.zweck.value] for t in data.trips],
            (19, 36, 36, 18, 18, 17, 20), ("LEFT", "LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT", "LEFT"),
        )
    else:
        hinweis("Keine Fahrten im Zeitraum.")

    return bytes(pdf.output())
