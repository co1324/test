"""Knowledge base construction and retrieval utilities."""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

import numpy as np

try:  # pragma: no cover - optional dependency
    from PyPDF2 import PdfReader
except Exception:  # pragma: no cover - optional dependency
    PdfReader = None  # type: ignore

try:  # pragma: no cover - optional dependency
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except Exception:  # pragma: no cover - optional dependency
    TfidfVectorizer = None  # type: ignore
    cosine_similarity = None  # type: ignore

from .config import KnowledgeBaseConfig

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeBaseEntry:
    """Single chunk of law text stored in the knowledge base."""

    text: str
    source: str
    page_number: int


@dataclass
class KnowledgeBase:
    """Container for vectorized law text entries."""

    entries: Sequence[KnowledgeBaseEntry]
    vectorizer: "TfidfVectorizer"
    matrix: np.ndarray

    def save(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as fh:
            pickle.dump(self, fh)
        logger.info("Saved knowledge base with %d entries to %s", len(self.entries), output_path)

    @classmethod
    def load(cls, path: Path) -> "KnowledgeBase":
        with path.open("rb") as fh:
            kb = pickle.load(fh)
        if not isinstance(kb, cls):  # pragma: no cover - defensive check
            raise TypeError(f"Unexpected object type in knowledge base file: {type(kb)!r}")
        return kb

    def search(self, query: str, top_k: int, min_similarity: float) -> List[Tuple[KnowledgeBaseEntry, float]]:
        if not query.strip():
            return []
        query_vec = self.vectorizer.transform([query])
        scores = cosine_similarity(query_vec, self.matrix)[0]
        ranked = sorted(zip(self.entries, scores), key=lambda item: item[1], reverse=True)
        return [item for item in ranked[:top_k] if item[1] >= min_similarity]


class KnowledgeBaseBuilder:
    """Builds a knowledge base from a reference law PDF."""

    def __init__(self, config: KnowledgeBaseConfig):
        self.config = config
        if PdfReader is None:
            raise RuntimeError("PyPDF2 is required to build the knowledge base.")
        if TfidfVectorizer is None:
            raise RuntimeError("scikit-learn is required to build the knowledge base.")

    def build(self) -> KnowledgeBase:
        logger.info("Loading law PDF from %s", self.config.law_pdf_path)
        reader = PdfReader(str(self.config.law_pdf_path))
        pages = [page.extract_text() or "" for page in reader.pages]
        entries = list(self._chunk_pages(pages))
        logger.info("Chunked law text into %d entries", len(entries))
        vectorizer = TfidfVectorizer(stop_words="english")
        matrix = vectorizer.fit_transform(entry.text for entry in entries)
        knowledge_base = KnowledgeBase(entries=entries, vectorizer=vectorizer, matrix=matrix)
        knowledge_base.save(self.config.output_path)
        return knowledge_base

    def _chunk_pages(self, pages: Sequence[str]) -> Iterable[KnowledgeBaseEntry]:
        chunk_size = self.config.chunk_size
        overlap = self.config.chunk_overlap
        min_length = self.config.min_chunk_length
        for idx, text in enumerate(pages, start=1):
            cleaned = "\n".join(line.strip() for line in text.splitlines() if line.strip())
            words = cleaned.split()
            if not words:
                continue
            start = 0
            while start < len(words):
                end = min(len(words), start + chunk_size)
                chunk_words = words[start:end]
                if len(chunk_words) < min_length and start != 0:
                    break
                chunk_text = " ".join(chunk_words)
                yield KnowledgeBaseEntry(text=chunk_text, source=str(self.config.law_pdf_path.name), page_number=idx)
                start = max(end - overlap, end)


__all__ = ["KnowledgeBaseEntry", "KnowledgeBase", "KnowledgeBaseBuilder"]
