"""Orchestration logic for the exam proofreading workflow."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List, Optional

try:  # pragma: no cover - optional dependency
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover - optional dependency
    fitz = None  # type: ignore

try:  # pragma: no cover - optional dependency
    from PIL import Image
except Exception:  # pragma: no cover - optional dependency
    Image = None  # type: ignore

from .config import PipelineConfig
from .knowledge_base import KnowledgeBase, KnowledgeBaseBuilder
from .layout import ColumnDetector
from .ocr import OCRProcessor, OCRResult
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
        self.config = config
        self._knowledge_base: Optional[KnowledgeBase] = None

    def run(self) -> List[PageResult]:
        logger.info("Starting exam proofreading for %s", self.config.exam_pdf_path)
        knowledge_base = self._load_or_build_knowledge_base()
        column_detector = self._build_column_detector()
        ocr_processor = self._build_ocr_processor()
        rag_validator = RAGValidator(self.config.retrieval, self.config.llm, knowledge_base)

        results: List[PageResult] = []
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        for page_number, payload in self._iter_pages():
            logger.info("Processing page %d", page_number)
            ocr_results = self._extract_text(payload, column_detector, ocr_processor)
            full_text = self._merge_columns(ocr_results)
            report = rag_validator.generate_report(full_text)
            output_path = self._write_report(page_number, report, ocr_results)
            confidences = [result.confidence for result in ocr_results]
            if confidences:
                avg_conf = sum(confidences) / len(confidences)
            else:
                avg_conf = 0.0
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

    def _iter_pages(self) -> Iterator[tuple[int, object]]:
        if fitz is not None and Image is not None:
            yield from self._iter_pdf_pages()
            return
        yield from self._iter_text_pages()

    def _iter_pdf_pages(self) -> Iterator[tuple[int, Image.Image]]:
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

    def _iter_text_pages(self) -> Iterator[tuple[int, str]]:
        text = self.config.exam_pdf_path.read_text(encoding="utf-8")
        pages = self._split_text_document(text)
        for idx, page in enumerate(pages, start=1):
            if self.config.page_range is not None and (idx - 1) not in self.config.page_range:
                continue
            yield idx, page

    def _split_text_document(self, text: str) -> List[str]:
        if "\f" in text:
            return [page.strip() for page in text.split("\f") if page.strip()]
        pages: List[str] = []
        current: List[str] = []
        for line in text.splitlines():
            if line.strip().startswith("===") and "page" in line.lower():
                if current:
                    pages.append("\n".join(current).strip())
                    current = []
                continue
            current.append(line)
        if current:
            pages.append("\n".join(current).strip())
        return [page for page in pages if page]

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

    def _build_column_detector(self) -> Optional[ColumnDetector]:
        if ColumnDetector.is_available():
            return ColumnDetector(self.config.layout)
        logger.warning(
            "Column detection dependencies not available; falling back to single-column text processing."
        )
        return None

    def _build_ocr_processor(self) -> Optional[OCRProcessor]:
        if OCRProcessor.is_available():
            return OCRProcessor(self.config.ocr)
        logger.warning(
            "pytesseract not available; assuming input text is already digitized."
        )
        return None

    def _extract_text(
        self,
        payload: object,
        column_detector: Optional[ColumnDetector],
        ocr_processor: Optional[OCRProcessor],
    ) -> List[OCRResult]:
        if Image is not None and isinstance(payload, Image.Image) and column_detector and ocr_processor:
            columns = column_detector.detect(payload)
            column_images = [box.crop(payload) for box in columns]
            return ocr_processor.ocr_columns(column_images)
        text = payload if isinstance(payload, str) else ""
        return [OCRResult(text=text, confidence=1.0, column_index=0)] if text else []


__all__ = ["ExamProofreader", "PageResult"]
