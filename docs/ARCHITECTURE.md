# Architektur & Konzept

Zusammenfassung der Entscheidungen aus der Konzeptphase, als Referenz für
die Weiterentwicklung.

## Ausgangslage

Die bisherige Excel-Datei (`Kraftstoffkosten LPG`, `Kraftstoffkosten
Benzin`, `Gesamtstatistik`, `Sonstige Kosten`, `Grafik`, `Anleitung`)
verwaltet pro Fahrzeug: Stammdaten (Hersteller, Modell, Variante,
Kennzeichen, Tankvolumen, Kaufdatum), Tankeinträge getrennt nach LPG/
Benzin, sonstige Kosten (Versicherung, Steuer, Finanzierung, Reifen/Teile,
Service/TÜV, Waschen, Einmalkosten) sowie daraus abgeleitete Kennzahlen
(Ø-Verbrauch, €/km, €/Monat). Die Gesamtstatistik nutzt dafür eine
komplexe Tages-Interpolation zwischen LPG- und Benzin-Einträgen, die in
diesem Projekt durch die einfachere, aber gut nachvollziehbare
"Voll-zu-Voll"-Methode ersetzt wurde (`app/routers/stats.py`).

## Kernentscheidungen

**Nextcloud-Integration:** volle ExApp-Integration über die offizielle
AppAPI (`app_api`/ExApps), nicht nur lose Anbindung. Die App läuft als
eigener Docker-Container (beliebiger Tech-Stack, hier Python/FastAPI),
erscheint aber wie eine native Nextcloud-App und kann auf Files,
Notifications und Talk zugreifen. Referenz: genau so baut Nextcloud auch
seine eigenen KI-Funktionen (z.B. die "Local large language model"-App),
das AppAPI-Muster ist also etabliert, nicht experimentell.

**Foto-Erfassung:** über einen Nextcloud-Talk-Bot (offizielle Bot-Webhook-
API), damit die gesamte Kette – Chat, Verarbeitung, Speicherung – auf
eigener Infrastruktur bleibt, ohne WhatsApp/Meta, Threema-Gateway-Kosten
oder die Signal-Grauzone. Bekannter Schwachpunkt: das Auflösen von Bild-
Anhängen aus dem Talk-Webhook-Payload ist laut Community-Berichten je
nach Talk-Version noch nicht durchgängig zuverlässig – im Code klar als
TODO markiert (`app/talk_bot/webhook.py`). Falls sich das in der Praxis
als zu unzuverlässig erweist: WhatsApp Cloud API oder Threema Gateway als
Ausweich-Kanal, die restliche Pipeline (OCR, Parsing, Speicherung) bleibt
identisch.

**Bilderkennung:** komplett lokal, CPU-only (keine GPU verfügbar).
Zweistufig:
1. PaddleOCR für die reine Texterkennung – dieselbe Engine, die Immich
   seit Version 2.2 für seine eigene Foto-Textsuche nutzt. Immichs
   Machine-Learning-Container selbst wird NICHT mitbenutzt, da er intern
   fest an Immichs eigene Pipeline gekoppelt und nicht als allgemeine API
   für andere Apps gedacht ist – stattdessen läuft ein eigener, aber
   technologisch identischer Dienst nebenher.
2. Regelbasiertes Parsing des erkannten Texts in strukturierte Felder
   (Datum, Menge, Preis/Liter, Gesamtpreis, Kraftstoffart) –
   `app/ocr/parser.py`. Bewusst ohne Vision-Sprachmodell, weil das auf
   CPU-Hardware zu langsam wäre.
3. Optionaler Fallback auf ein kleines lokales Text-LLM (z.B. über
   Ollama), falls die Regeln zu unsicher sind – standardmäßig
   deaktiviert (`app/ocr/llm_fallback.py`), da CPU-Inferenz Zeit kostet
   und der Bestätigungsschritt im Chat Fehler ohnehin abfängt.

Wichtig: **nichts wird ungeprüft gespeichert**. Der Talk-Bot schickt die
erkannten Werte immer erst als Vorschlag zurück in den Chat; erst nach
Bestätigung ("ja") landet der Eintrag in der Datenbank
(`app/talk_bot/session.py`).

**Karte:** OpenStreetMap + Leaflet statt Google Maps – keine API-Kosten,
kein Vendor-Lock-in, passt zum Self-Hosting-Ansatz. Standort pro
Tankfüllung kommt nach Möglichkeit automatisch aus den EXIF-GPS-Daten des
Fotos (`app/geocoding.py`), keine manuelle Eingabe nötig.

**Fahrtziele:** noch offen, ob eine reine Tankstellen-Historie auf der
Karte reicht oder ein echtes Fahrtenbuch (Start/Ziel pro Fahrt) gewünscht
ist – Letzteres bräuchte zusätzlich eine manuelle Zieleingabe, da sie
nicht aus dem Beleg-Foto ableitbar ist. Bisher nicht implementiert.

## Datenmodell

Siehe `app/models.py`. Vier Tabellen: `vehicles` (Stammdaten inkl.
Bot-Codewort zur automatischen Fahrzeug-Zuordnung im Chat), `fuel_entries`
(Tank-Log), `other_costs` (Versicherung/Steuer/Service/etc.),
`maintenance_reminders` (neu gegenüber der Excel-Datei: aktive
Erinnerungen statt reiner Rückschau, nach Datum oder Kilometerstand,
optional wiederkehrend).

## Offene Punkte / bewusst nicht in diesem Gerüst

- Nextcloud-Login/SSO für das Frontend (OpenID Connect über Nextclouds
  `user_oidc`/OIDC-Provider-Fähigkeiten) – aktuell keine Auth im
  Standalone-Modus.
- Belege dauerhaft in Nextcloud Files ablegen statt nur als lokaler Pfad
  (`beleg_foto_pfad`/`tacho_foto_pfad` in den Modellen sind vorbereitet,
  der Upload über WebDAV fehlt noch).
- Anbindung der Erinnerungen an Nextcloud Notifications.
- Export für Steuerberater/Verkauf (PDF/CSV-Jahresübersicht).
- Mehrbenutzer-Feinschliff (aktuell: ein Bot-Codewort pro Fahrzeug, keine
  Unterscheidung, wer aus der Familie den Eintrag geschickt hat).

## Talk-Bot einrichten (Kurzfassung)

Der Bot registriert sich seit der Umstellung auf `nc_py_api.talk_bot.AsyncTalkBot`
(siehe `app/talk_bot/bot.py`) automatisch selbst bei AppAPI, sobald die
ExApp aktiviert wird - AppAPI generiert dabei sein Secret selbst, es muss
nichts mehr manuell in `.env`/`TALK_BOT_SECRET` gepflegt werden.

1. ExApp in Nextcloud aktivieren (`occ app_api:app:register` bzw. über die
   Verwaltungsoberfläche) - der Bot meldet sich dabei automatisch an.
2. Bot in der gewünschten Talk-Unterhaltung hinzufügen (Konversation →
   Unterhaltungseinstellungen → Bots).
3. Fahrzeug in der DB mit `bot_codewort` anlegen (siehe
   `migrations/init_db.py` für ein Beispiel).
4. Im Talk-Chat: Codewort schicken → Tacho-Foto → Beleg-Foto → Vorschlag
   im Chat mit "ja" bestätigen.

Vor Schritt 1 unbedingt die aktuelle AppAPI-/Talk-Dokumentation prüfen, da
sich Befehle und Header-Namen zwischen Versionen leicht unterscheiden
können:
- https://nextcloud-talk.readthedocs.io/en/latest/bots/
- https://docs.nextcloud.com/server/stable/developer_manual/exapp_development/tech_details/api/talkbots.html

## Deployment über HaRP (Stolperfallen)

Erprobt auf Nextcloud 34 (nativ, PHP-FPM/nginx) mit HaRP als Deploy-Daemon:

- **nginx: `location ^~ /exapps/`** (mit `^~`) für die Weiterleitung an HaRP.
  Ohne `^~` gewinnt Nextclouds Standard-Regel für statische Dateien
  (`location ~ \.(?:css|js|svg|...)$`), und alle `/exapps/...`-Pfade mit
  Dateiendung (Menü-Icon, Skripte) landen bei Nextcloud statt bei HaRP.
  AppAPI spricht die ExApp auch intern über diese öffentliche URL an.
- **`--env` nur für deklarierte Variablen**: `occ app_api:app:register --env`
  übernimmt nur Variablen, die in `appinfo/info.xml` unter
  `<environment-variables>` mit nicht-leerem `<default>` stehen.
- **Registry-Pull ist Pflicht**: AppAPI zieht das Image bei jeder
  Registrierung aus der Registry, auch wenn es lokal gebaut vorliegt. Image
  daher *vor* `app_api:app:register` pushen, sonst setzt der Pull den lokalen
  Tag auf den alten Registry-Stand zurück.
- **Top-Menü-Skript ohne `.js` registrieren** (`set_script(..., "js/app")`):
  AppAPI hängt die Endung beim Einsetzen selbst an.
- **Routes**: `/ui`, `/api`, `/img`, `/js` müssen in `appinfo/info.xml` unter
  `<routes>` deklariert sein, sonst lehnen HaRP bzw. der AppAPI-Proxy die
  Anfragen ab.
