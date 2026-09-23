"""
Sehr leichtgewichtige Übersetzungsschicht für die Talk-Bot-/Chat-Texte.

Bewusst kein volles gettext/Babel-Setup, sondern ein einfaches
Key→Text-Wörterbuch pro Sprache – reicht für den überschaubaren Umfang an
Bot-Nachrichten und macht es leicht, weitere Sprachen beizutragen, ohne
Code in webhook.py/session.py anfassen zu müssen (wichtig, sobald das
Repo öffentlich ist und andere mitmachen wollen).

Aktuell nur Deutsch hinterlegt. Neue Sprache hinzufügen: Eintrag in
_STRINGS ergänzen (gleiche Keys, übersetzte Werte) und in .env
APP_LOCALE setzen.
"""
from __future__ import annotations

import os

_STRINGS: dict[str, dict[str, str]] = {
    "de": {
        "vehicle_selected": "Fahrzeug **{hersteller} {modell}** ausgewählt. Bitte jetzt Tacho- und Belegfoto schicken.",
        "ask_codeword": "Bitte zuerst das Fahrzeug-Codewort schicken.",
        "entry_saved": "✅ Eintrag gespeichert.",
        "tacho_recognized": "Tacho erkannt. Jetzt bitte noch den Beleg schicken.",
        "help_text": "Bitte zuerst Fahrzeug-Codewort, dann Tacho- und Belegfoto schicken.",
        "confirmation_header": "📋 Neuer Eintrag für **{hersteller} {modell}** ({kennzeichen}):",
        "field_datum": "Datum",
        "field_kilometerstand": "Kilometerstand",
        "field_kraftstoff": "Kraftstoff",
        "field_menge": "Menge",
        "field_preis_pro_liter": "Preis/Liter",
        "field_gesamtpreis": "Gesamtpreis",
        "unknown_value": "?",
        "confirmation_prompt": "Passt das? Mit **ja** bestätigen oder korrigieren, z.B. „Menge 32,1“.",
        "photo_processing_failed": "❌ Foto konnte nicht verarbeitet werden (Download/OCR fehlgeschlagen). Bitte erneut senden.",
        "missing_fields": "Es fehlen noch Pflichtfelder ({felder}). Bitte Foto(s) erneut senden oder den Eintrag manuell in der Web-Oberfläche ergänzen.",
        "kilometerstand_unplausibel": "⚠️ {fehler} Bitte Kilometerstand prüfen und Foto erneut senden.",
    }
}

DEFAULT_LOCALE = "de"


def t(key: str, *, locale: str | None = None, **kwargs) -> str:
    """Übersetzt 'key' in die gewünschte (oder per APP_LOCALE
    konfigurierte) Sprache. Faellt auf Deutsch zurueck, falls die Sprache
    oder der Key fehlt, damit ein fehlender Übersetzungseintrag nie zu
    einem Absturz im Talk-Bot führt."""
    locale = locale or os.environ.get("APP_LOCALE", DEFAULT_LOCALE)
    strings = _STRINGS.get(locale, _STRINGS[DEFAULT_LOCALE])
    template = strings.get(key) or _STRINGS[DEFAULT_LOCALE].get(key, key)
    return template.format(**kwargs) if kwargs else template
