# Fahrzeug Buchführung

Ersatz für die Excel-basierte Fahrzeug-Buchführung (Kraftstoffkosten LPG/
Benzin, Sonstige Kosten, Gesamtstatistik) als Nextcloud-App (AppAPI/ExApp),
mit Belegerfassung per Foto über einen Nextcloud-Talk-Bot und lokaler
OCR-Auswertung (CPU).

Der volle Hintergrund/die Architekturentscheidungen stehen in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Diese Datei hier ist der
Schnellstart.

## Status & Weg zur Veröffentlichung

Aktuell: **offenes Repo**, lizenziert unter AGPLv3+ ([LICENSE](LICENSE)),
gedacht zum Selbst-Hosten und Mitentwickeln – noch nicht im offiziellen
Nextcloud App Store gelistet.

Für eine spätere Einreichung bei [apps.nextcloud.com](https://apps.nextcloud.com)
wäre zusätzlich nötig:
- Entwickler-Account im App Store registrieren
- die App gegen eine echte Nextcloud-Instanz durchtesten (insbesondere
  die beiden in [CHANGELOG.md](CHANGELOG.md) unter "Bekannte Lücken"
  genannten Punkte)
- klären, ob/wie der übliche `occ integrity:sign-app`-Signaturprozess auf
  Docker-basierte ExApps angewendet wird, oder ob dafür ein anderer Weg
  (Registry-basiert) vorgesehen ist – dazu liefert die aktuelle
  Nextcloud-Dokumentation keine eindeutige Aussage, das müsste direkt mit
  der Nextcloud-Community geklärt werden
- Screenshots und eine App-Store-Beschreibung
- den Code-Check (`occ app:check-code`) durchlaufen lassen
- optional: weitere Sprachen neben Deutsch (`app/i18n.py` ist dafür
  vorbereitet)

## Stand dieses Gerüsts

Das ist ein **Ausgangspunkt**, kein fertiges Produkt: Datenmodell, REST-API,
Verbrauchs-/Kostenberechnung, OCR-Pipeline (regelbasiert) und der grobe
Talk-Bot-Ablauf sind lauffähiger Code. Nicht gegen eine echte Nextcloud-
Instanz getestet sind bisher: die nc_py_api-Integration in `main.py`
(ExApp-Modus) und die Anhang-Auflösung im Talk-Webhook
(`app/talk_bot/webhook.py::_extract_attached_image_url`) – beide Stellen
sind im Code klar als TODO markiert.

## Schnellstart (Standalone-Modus, ohne Nextcloud)

Damit lässt sich die Kernlogik – API, Datenbank, Statistik – sofort
testen, ganz ohne AppAPI-Setup und ohne die (recht große) OCR-Engine:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-core.txt   # ohne PaddleOCR, siehe unten
cp .env.example .env

python -m migrations.init_db      # legt SQLite-DB + Beispiel-Fahrzeug "Previa" an
python main.py                    # startet auf http://localhost:23000
```

Danach:
- API-Doku: http://localhost:23000/docs
- Weboberfläche (einfacher Stand, siehe unten): http://localhost:23000/ui/

Für die volle Funktionalität inkl. Fotoauswertung: `pip install -r
requirements.txt` (zieht zusätzlich PaddleOCR/PaddlePaddle, ca. 200+ MB).
Für Tests/CI reicht `requirements-dev.txt`.

Alternativ mit Docker: `docker compose up --build`.

### Tests ausführen

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

Läuft auch automatisch per GitHub Actions bei jedem Push/PR
(`.github/workflows/ci.yml`).

## Als echte Nextcloud-App betreiben

1. `STANDALONE_MODE=false` setzen.
2. Für die Entwicklung: `scripts/register_dev.sh` auf dem Nextcloud-Server
   ausführen (registriert die App über `manual_install`, die App läuft dabei
   lokal via `python main.py`).
3. Für den produktiven Betrieb auf witt14.de: Docker-Image bauen, in eine
   (ggf. private) Registry pushen, `appinfo/info.xml` mit den echten
   Image-Angaben aktualisieren, dann über `occ app_api:daemon:register`
   (docker-install) + `occ app_api:app:register` registrieren.
4. Talk-Bot registrieren und `TALK_BOT_SECRET` setzen (Details siehe
   `docs/ARCHITECTURE.md`, Abschnitt "Talk-Bot einrichten").

## Projektstruktur

```
appinfo/info.xml         ExApp-Manifest
main.py                  Einstiegspunkt (Standalone- vs. ExApp-Modus)
app/models.py             SQLAlchemy-Modelle (Vehicle, FuelEntry, OtherCost, Reminder)
app/i18n.py                Übersetzungsschicht für Bot-/Chat-Texte (bisher nur Deutsch)
app/routers/              REST-API (CRUD + Statistik)
app/ocr/                  PaddleOCR-Wrapper, regelbasierter Parser, optionaler LLM-Fallback
app/talk_bot/              Talk-Bot-Webhook, Session-Pairing (Tacho+Beleg), Antwort-Versand
app/geocoding.py           EXIF-GPS-Auslesung + Reverse-Geocoding (Nominatim/OSM)
frontend/static/           Minimale Weboberfläche mit Karte (Leaflet/OSM)
tests/                     Pytest-Tests (API/Statistik, OCR-Parser)
docs/ARCHITECTURE.md       Gesamtkonzept und offene Entscheidungen
migrations/init_db.py      DB-Setup + Beispiel-Fahrzeug
scripts/register_dev.sh    Dev-Registrierung bei Nextcloud
.github/workflows/ci.yml   GitHub Actions: Syntax-Check + Tests
LICENSE                    AGPLv3+
CONTRIBUTING.md            Hinweise für Beiträge
CHANGELOG.md                Versionshistorie
```

## Nächste sinnvolle Schritte

1. `_extract_attached_image_url` gegen eine echte Talk-Unterhaltung testen
   und anpassen.
2. `app/ocr/parser.py` mit echten Fotos deiner Belege kalibrieren (die
   Regex-Heuristiken sind ein erster Wurf, keine trainierten Modelle).
3. Erinnerungen (`app/routers/reminders.py`) an Nextcloud Notifications
   anbinden, statt sie nur über die API abzufragen.
4. Frontend ausbauen (Fahrzeug-Stammdaten anlegen/bearbeiten,
   Sonstige-Kosten-Formular, Jahres-/Export-Ansicht).
