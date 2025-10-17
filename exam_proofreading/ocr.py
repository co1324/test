"""OCR utilities for converting column images to text."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, List

try:  # pragma: no cover - optional dependency
    import pytesseract
except Exception:  # pragma: no cover - optional dependency
    pytesseract = None  # type: ignore

from PIL import Image

from .config import OCRConfig

logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    """Stores OCR output for a single column."""

    text: str
    confidence: float
    column_index: int


class OCRProcessor:
    """Run OCR over page columns in sequence."""

    def __init__(self, config: OCRConfig):
        if pytesseract is None:
            raise RuntimeError("pytesseract is required for OCR operations.")
        self.config = config
        if config.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = config.tesseract_cmd

    def ocr_columns(self, columns: Iterable[Image.Image]) -> List[OCRResult]:
        results: List[OCRResult] = []
        for idx, column_image in enumerate(columns):
            logger.debug("Running OCR on column %d", idx)
            data = pytesseract.image_to_data(column_image, lang=self.config.language, output_type=pytesseract.Output.DICT)
            text = " ".join(word for word in data.get("text", []) if word.strip())
            confidences = [float(conf) for conf in data.get("conf", []) if conf != "-1"]
            confidence = sum(confidences) / len(confidences) if confidences else 0.0
            results.append(OCRResult(text=text.strip(), confidence=confidence, column_index=idx))
        return results


__all__ = ["OCRProcessor", "OCRResult"]
