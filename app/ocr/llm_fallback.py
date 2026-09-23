"""
Optionaler Fallback fuer Belege, die der regelbasierte Parser nicht sicher
genug auswerten konnte (viele Warnungen / niedrige Konfidenz).

Standardmaessig DEAKTIVIERT (LLM_FALLBACK_ENABLED=false in .env) – auf
CPU-only-Hardware kostet ein zusaetzliches LLM spuerbar Zeit, und die
regelbasierte Auswertung plus Bestaetigung im Chat sollte fuer die meisten
Faelle reichen. Wer trotzdem mehr Automatisierung will: ein kleines,
quantisiertes lokales Modell (z.B. ueber Ollama) reicht hier voellig,
da nur Text (nicht das Bild) strukturiert werden muss – deutlich
leichtgewichtiger als ein volles Vision-Modell.

Dies ist ein Stub: die Funktion ist lauffaehig, ersetzt aber keine echte
Kalibrierung/Tests mit echten Belegen.
"""
from __future__ import annotations

import json
import os

import httpx

from app.ocr.parser import BelegVorschlag

_PROMPT_TEMPLATE = """\
Du bekommst den OCR-Rohtext eines Tankbelegs. Extrahiere folgende Felder
als JSON (Werte auf null setzen, wenn nicht sicher erkennbar):
datum (YYYY-MM-DD), gesamtpreis (float), preis_pro_liter (float),
fuellmenge_liter (float), kraftstoffart (LPG|Benzin|Diesel|Strom|null).

OCR-Text:
---
{text}
---
Antworte NUR mit dem JSON-Objekt, ohne weitere Erklaerung.
"""


def is_enabled() -> bool:
    return os.environ.get("LLM_FALLBACK_ENABLED", "false").lower() == "true"


def refine_with_local_llm(rohtext: str, vorschlag: BelegVorschlag) -> BelegVorschlag:
    if not is_enabled():
        return vorschlag

    base_url = os.environ.get("LLM_FALLBACK_URL", "http://localhost:11434")
    model = os.environ.get("LLM_FALLBACK_MODEL", "qwen2.5:1.5b-instruct")

    try:
        response = httpx.post(
            f"{base_url}/api/generate",
            json={
                "model": model,
                "prompt": _PROMPT_TEMPLATE.format(text=rohtext),
                "stream": False,
                "format": "json",
            },
            timeout=30.0,
        )
        response.raise_for_status()
        daten = json.loads(response.json()["response"])
    except Exception as exc:  # noqa: BLE001 - bewusst breit, ist nur ein Fallback
        vorschlag.warnungen.append(f"LLM-Fallback fehlgeschlagen: {exc}")
        return vorschlag

    # Nur Felder uebernehmen, die der regelbasierte Parser NICHT gefunden hat –
    # der deterministische Parser bleibt die primaere Quelle.
    if vorschlag.gesamtpreis is None and daten.get("gesamtpreis"):
        vorschlag.gesamtpreis = float(daten["gesamtpreis"])
    if vorschlag.preis_pro_liter is None and daten.get("preis_pro_liter"):
        vorschlag.preis_pro_liter = float(daten["preis_pro_liter"])
    if vorschlag.fuellmenge_liter is None and daten.get("fuellmenge_liter"):
        vorschlag.fuellmenge_liter = float(daten["fuellmenge_liter"])

    vorschlag.warnungen.append("Werte teilweise durch lokales LLM ergaenzt – bitte pruefen.")
    return vorschlag
