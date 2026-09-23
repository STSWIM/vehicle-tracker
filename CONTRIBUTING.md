# Contributing

Danke für dein Interesse an diesem Projekt. Es befindet sich noch in einer
frühen Phase (siehe Status in [README.md](README.md)) – Beiträge sind
trotzdem willkommen, besonders in folgenden Bereichen:

- **Übersetzungen**: neue Sprache in [`app/i18n.py`](app/i18n.py)
  ergänzen (einfaches Key→Text-Wörterbuch, siehe Kommentare dort).
- **OCR-Kalibrierung**: der regelbasierte Parser
  ([`app/ocr/parser.py`](app/ocr/parser.py)) wurde bisher nur mit
  synthetischen Testdaten geprüft, nicht mit einer breiten Menge echter
  Kassenbons/Tacho-Fotos. Beispiele für Fälle, in denen er scheitert, sind
  sehr hilfreich.
- **Talk-Bot-Anhänge**: das Auflösen von Bild-Anhängen aus dem
  Nextcloud-Talk-Webhook (`app/talk_bot/webhook.py`,
  `_extract_attached_image_url`) ist als bekannte Schwachstelle markiert –
  wer das gegen eine echte Talk-Instanz verifiziert hat, gerne einen PR
  oder zumindest ein Issue mit den Details öffnen.
- **Frontend**: aktuell eine bewusst minimale statische Seite
  (`frontend/static/index.html`). Eine echte Vue-Anwendung nach
  ExApp-Konventionen (`ex_app/src/`) wäre der nächste sinnvolle Schritt.

## Vor einem Pull Request

```bash
python -m py_compile app/*.py app/**/*.py main.py   # Syntax-Check
# optional, falls installiert:
ruff check .
```

Bitte in der Commit-Message/PR-Beschreibung kurz beschreiben, *was* sich
ändert und *warum* – besonders bei Änderungen an der OCR-Heuristik oder
den Statistik-Berechnungen, da die dort verwendeten Annahmen (z.B. die
"Voll-zu-Voll"-Verbrauchsberechnung) nicht immer offensichtlich sind.

## Lizenz

Beiträge werden unter derselben Lizenz wie das Projekt (AGPLv3+, siehe
[LICENSE](LICENSE)) angenommen.
