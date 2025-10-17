"""Orchestration logic for the exam proofreading workflow."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List, Optional

import numpy as np

try:  # pragma: no cover - optional dependency
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover - optional dependency
    fitz = None  # type: ignore

from PIL import Image

from .config import PipelineConfig
from .knowledge_base import KnowledgeBase, KnowledgeBaseBuilder
from .layout import ColumnDetector
from .ocr import OCRProcessor
from .rag import RAGValidator

logger = logging.getLogger(__name__)


@dataclass
class PageResult:
    """Structured result for a single processed page."""

    page_number: int
    text: str
    ocr_confidence: float
    report: str
    output_path: Path


class ExamProofreader:
    """Implements the multi-phase exam proofreading workflow."""

    def __init__(self, config: PipelineConfig):
        if fitz is None:
            raise RuntimeError("PyMuPDF is required for PDF rendering.")
        self.config = config
        self._knowledge_base: Optional[KnowledgeBase] = None

    def run(self) -> List[PageResult]:
        logger.info("Starting exam proofreading for %s", self.config.exam_pdf_path)
        knowledge_base = self._load_or_build_knowledge_base()
        column_detector = ColumnDetector(self.config.layout)
        ocr_processor = OCRProcessor(self.config.ocr)
        rag_validator = RAGValidator(self.config.retrieval, self.config.llm, knowledge_base)

        results: List[PageResult] = []
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        for page_number, page_image in self._iter_page_images():
            logger.info("Processing page %d", page_number)
            columns = column_detector.detect(page_image)
            column_images = [box.crop(page_image) for box in columns]
            ocr_results = ocr_processor.ocr_columns(column_images)
            full_text = self._merge_columns(ocr_results)
            report = rag_validator.generate_report(full_text)
            output_path = self._write_report(page_number, report, ocr_results)
            avg_conf = np.mean([result.confidence for result in ocr_results]) if ocr_results else 0.0
            results.append(
                PageResult(
                    page_number=page_number,
                    text=full_text,
                    ocr_confidence=float(avg_conf),
                    report=report,
                    output_path=output_path,
                )
            )
        logger.info("Finished processing %d pages", len(results))
        return results

    def _load_or_build_knowledge_base(self) -> KnowledgeBase:
        if self._knowledge_base is not None:
            return self._knowledge_base
        kb_path = self.config.knowledge_base.output_path
        if kb_path.exists():
            logger.info("Loading existing knowledge base from %s", kb_path)
            self._knowledge_base = KnowledgeBase.load(kb_path)
        else:
            logger.info("Building knowledge base; no existing file at %s", kb_path)
            builder = KnowledgeBaseBuilder(self.config.knowledge_base)
            self._knowledge_base = builder.build()
        return self._knowledge_base

    def _iter_page_images(self) -> Iterator[tuple[int, Image.Image]]:
        doc = fitz.open(str(self.config.exam_pdf_path))
        try:
            for page_number in self._page_range(doc):
                page = doc.load_page(page_number)
                pix = page.get_pixmap(dpi=self.config.ocr.dpi)
                mode = "RGBA" if pix.alpha else "RGB"
                image = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
                yield page_number + 1, image
        finally:
            doc.close()

    def _page_range(self, doc: "fitz.Document") -> Iterable[int]:
        if self.config.page_range is not None:
            return [idx for idx in self.config.page_range if 0 <= idx < len(doc)]
        return range(len(doc))

    def _merge_columns(self, ocr_results: Iterable) -> str:
        return "\n".join(result.text for result in ocr_results if result.text)

    def _write_report(self, page_number: int, report: str, ocr_results: Iterable) -> Path:
        output_path = self.config.output_dir / f"page_{page_number:03d}.json"
        payload = {
            "page": page_number,
            "ocr": [
                {"column": result.column_index, "confidence": result.confidence, "text": result.text}
                for result in ocr_results
            ],
            "report": report,
        }
        with output_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        logger.debug("Wrote report for page %d to %s", page_number, output_path)
        return output_path


__all__ = ["ExamProofreader", "PageResult"]
