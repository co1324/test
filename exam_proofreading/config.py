"""Configuration data structures for the exam proofreading pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class KnowledgeBaseConfig:
    """Configuration for building and persisting the knowledge base."""

    law_pdf_path: Path
    output_path: Path = Path("knowledge_base.pkl")
    chunk_size: int = 750
    chunk_overlap: int = 50
    min_chunk_length: int = 120


@dataclass
class OCRConfig:
    """Options controlling OCR behavior."""

    language: str = "kor+eng"
    dpi: int = 300
    tesseract_cmd: Optional[str] = None


@dataclass
class LayoutConfig:
    """Options for the column detector."""

    minimum_column_width: int = 350
    maximum_columns: int = 3
    whitespace_threshold: float = 0.85


@dataclass
class RetrievalConfig:
    """Configuration for the RAG retrieval stage."""

    top_k: int = 4
    min_similarity: float = 0.15


@dataclass
class LLMConfig:
    """Configuration for the language model interface."""

    provider: str = "local"
    model: str = "gpt-neo-125M"
    temperature: float = 0.2
    max_tokens: int = 768
    api_key: Optional[str] = None


@dataclass
class PipelineConfig:
    """Top-level pipeline configuration."""

    exam_pdf_path: Path
    knowledge_base: KnowledgeBaseConfig
    ocr: OCRConfig = field(default_factory=OCRConfig)
    layout: LayoutConfig = field(default_factory=LayoutConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    output_dir: Path = Path("reports")
    page_range: Optional[range] = None


__all__ = [
    "KnowledgeBaseConfig",
    "OCRConfig",
    "LayoutConfig",
    "RetrievalConfig",
    "LLMConfig",
    "PipelineConfig",
]
