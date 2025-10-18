"""Knowledge base construction and retrieval utilities."""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from collections import Counter
import math

try:  # pragma: no cover - optional dependency
    from PyPDF2 import PdfReader
except Exception:  # pragma: no cover - optional dependency
    PdfReader = None  # type: ignore

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
    vocabulary: Sequence[str]
    matrix: Sequence[Sequence[float]]

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
        if not hasattr(kb, "_KnowledgeBase__idf_cache"):
            kb.set_idf_cache({})
        return kb

    def search(self, query: str, top_k: int, min_similarity: float) -> List[Tuple[KnowledgeBaseEntry, float]]:
        if not query.strip():
            return []
        query_vec = self._vectorize_text(query)
        scores = [self._cosine_similarity(query_vec, vector) for vector in self.matrix]
        ranked = sorted(zip(self.entries, scores), key=lambda item: item[1], reverse=True)
        return [item for item in ranked[:top_k] if item[1] >= min_similarity]

    def _vectorize_text(self, text: str) -> List[float]:
        tokens = self._tokenize(text)
        counter = Counter(tokens)
        vector = []
        for term in self.vocabulary:
            tf = counter.get(term, 0)
            idf = self._idf_cache[term]
            vector.append(tf * idf)
        return vector

    def _cosine_similarity(self, vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return [token.lower() for token in text.split() if token]

    @property
    def _idf_cache(self) -> dict[str, float]:
        if not hasattr(self, "__idf_cache"):
            raise AttributeError("KnowledgeBase missing IDF cache")
        return getattr(self, "__idf_cache")

    def set_idf_cache(self, cache: dict[str, float]) -> None:
        setattr(self, "__idf_cache", cache)


class KnowledgeBaseBuilder:
    """Builds a knowledge base from a reference law PDF."""

    def __init__(self, config: KnowledgeBaseConfig):
        self.config = config

    def build(self) -> KnowledgeBase:
        pages = self._load_law_pages()
        entries = list(self._chunk_pages(pages))
        logger.info("Chunked law text into %d entries", len(entries))
        vocabulary, matrix, idf_cache = self._build_vector_space(entries)
        knowledge_base = KnowledgeBase(entries=entries, vocabulary=vocabulary, matrix=matrix)
        knowledge_base.set_idf_cache(idf_cache)
        knowledge_base.save(self.config.output_path)
        return knowledge_base

    def _load_law_pages(self) -> Sequence[str]:
        path = self.config.law_pdf_path
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            if PdfReader is None:
                raise RuntimeError("PyPDF2 is required to read PDF files. Please convert the law document to text.")
            logger.info("Loading law PDF from %s", path)
            reader = PdfReader(str(path))
            return [page.extract_text() or "" for page in reader.pages]
        logger.info("Loading law text from %s", path)
        text = path.read_text(encoding="utf-8")
        return list(self._split_text_document(text))

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

    def _build_vector_space(
        self, entries: Sequence[KnowledgeBaseEntry]
    ) -> Tuple[List[str], List[List[float]], dict[str, float]]:
        documents = [self._tokenize(entry.text) for entry in entries]
        vocabulary = sorted({token for doc in documents for token in doc})
        if not vocabulary:
            return [], [], {}
        doc_freq = {term: 0 for term in vocabulary}
        for doc in documents:
            unique_terms = set(doc)
            for term in unique_terms:
                doc_freq[term] += 1
        num_docs = len(documents)
        idf_cache = {
            term: math.log((1 + num_docs) / (1 + df)) + 1.0
            for term, df in doc_freq.items()
        }
        matrix: List[List[float]] = []
        for doc in documents:
            counts = Counter(doc)
            vector = [counts.get(term, 0) * idf_cache[term] for term in vocabulary]
            matrix.append(vector)
        return vocabulary, matrix, idf_cache

    def _split_text_document(self, text: str) -> Iterable[str]:
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

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return [token.lower() for token in text.split() if token]


__all__ = ["KnowledgeBaseEntry", "KnowledgeBase", "KnowledgeBaseBuilder"]
