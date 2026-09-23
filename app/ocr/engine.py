"""
Duenner Wrapper um PaddleOCR (CPU). PaddleOCR ist dieselbe Engine, die
Immich seit Version 2.2 fuer seine Foto-Textsuche nutzt – hier separat
betrieben, weil Immichs eigener ML-Dienst nicht als allgemeine API fuer
andere Apps gedacht ist.
"""
from __future__ import annotations

import functools
import os
from dataclasses import dataclass


@dataclass
class OcrLine:
    text: str
    confidence: float


@dataclass
class OcrResult:
    lines: list[OcrLine]

    @property
    def full_text(self) -> str:
        return "\n".join(l.text for l in self.lines)

    @property
    def mean_confidence(self) -> float:
        if not self.lines:
            return 0.0
        return sum(l.confidence for l in self.lines) / len(self.lines)


@functools.lru_cache(maxsize=1)
def _get_engine():
    # Lazy-Import + Caching: PaddleOCR laedt beim ersten Aufruf Modelle nach
    # (~100-200 MB), das soll nicht schon beim App-Start passieren.
    from paddleocr import PaddleOCR

    lang = os.environ.get("OCR_LANG", "de")
    return PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)


def run_ocr(image_path: str) -> OcrResult:
    engine = _get_engine()
    raw = engine.ocr(image_path, cls=True)

    lines: list[OcrLine] = []
    # PaddleOCR-Rueckgabeformat: Liste pro Bild -> Liste von [box, (text, konfidenz)]
    for page in raw or []:
        for entry in page or []:
            _box, (text, confidence) = entry
            lines.append(OcrLine(text=text, confidence=float(confidence)))

    return OcrResult(lines=lines)
