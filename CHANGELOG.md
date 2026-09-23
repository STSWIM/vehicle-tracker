# Changelog

Format angelehnt an [Keep a Changelog](https://keepachangelog.com/).
Solange die Version < 1.0.0 ist, können sich Datenmodell und API noch
ändern.

## [0.1.0] - Unveröffentlicht

Erstes Gerüst, noch nicht gegen eine echte Nextcloud-Instanz getestet.

### Hinzugefügt
- Datenmodell für Fahrzeuge, Tankeinträge, sonstige Kosten und
  Wartungserinnerungen (`app/models.py`)
- REST-API (CRUD + Statistik-Berechnung) via FastAPI
- Regelbasierte OCR-Auswertung für Tacho-/Belegfotos (PaddleOCR, CPU)
  mit optionalem lokalem LLM-Fallback
- Nextcloud-Talk-Bot-Skeleton mit Bestätigungs-Workflow
- Einfache Karten-/Übersichtsseite (Leaflet/OpenStreetMap)
- ExApp-Grundgerüst (AppAPI/nc_py_api) für die Integration als
  vollwertige Nextcloud-App
- Standalone-Entwicklungsmodus ohne Nextcloud-Abhängigkeit
- Leichtgewichtige i18n-Struktur für Bot-Nachrichten (`app/i18n.py`,
  bisher nur Deutsch)

### Bekannte Lücken
- ExApp-Lifecycle (`main.py`, ExApp-Zweig) ungetestet gegen echte AppAPI
- Talk-Webhook-Anhangsauflösung ungetestet gegen echte Talk-Instanz
- Kein Upload der Belegfotos nach Nextcloud Files (nur lokaler Pfad)
- Keine Anbindung an Nextcloud Notifications für Erinnerungen
