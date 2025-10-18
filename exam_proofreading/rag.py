"""Retrieval augmented generation for proofreading reports."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, List

from .config import LLMConfig, RetrievalConfig
from .knowledge_base import KnowledgeBase, KnowledgeBaseEntry

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """Represents a retrieved law snippet with similarity metadata."""

    entry: KnowledgeBaseEntry
    similarity: float


class BaseLLMClient:
    """Abstract interface for talking to a language model."""

    def generate(self, prompt: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class LocalTemplateLLM(BaseLLMClient):
    """Fallback LLM that crafts templated reports for offline usage."""

    def __init__(self, config: LLMConfig):
        self.config = config

    def generate(self, prompt: str) -> str:
        logger.debug("LocalTemplateLLM invoked with prompt length %d", len(prompt))
        header = "검수 리포트 (샘플)\n----------------------"
        body = (
            "다음은 제공된 법규 근거와 페이지 텍스트를 기반으로 한 자동 생성 리포트입니다.\n"
            "실제 LLM 응답을 사용하려면 `LLMConfig.provider` 설정을 변경하고 맞춤형 클라이언트를 구현하세요."
        )
        return f"{header}\n{body}\n\n{prompt.strip()}"


class RAGValidator:
    """Combine retrieval results with an LLM to generate proofreading reports."""

    def __init__(self, retrieval_config: RetrievalConfig, llm_config: LLMConfig, knowledge_base: KnowledgeBase,
                 llm_client: BaseLLMClient | None = None):
        self.retrieval_config = retrieval_config
        self.llm_config = llm_config
        self.knowledge_base = knowledge_base
        self.llm_client = llm_client or LocalTemplateLLM(llm_config)

    def retrieve(self, page_text: str) -> List[RetrievalResult]:
        matches = self.knowledge_base.search(
            query=page_text,
            top_k=self.retrieval_config.top_k,
            min_similarity=self.retrieval_config.min_similarity,
        )
        return [RetrievalResult(entry=entry, similarity=score) for entry, score in matches]

    def build_prompt(self, page_text: str, retrievals: Iterable[RetrievalResult]) -> str:
        context_parts = []
        for result in retrievals:
            context_parts.append(
                f"[법규 출처: {result.entry.source} / 페이지 {result.entry.page_number} / 유사도 {result.similarity:.2f}]\n"
                f"{result.entry.text}\n"
            )
        context = "\n".join(context_parts) if context_parts else "(관련 법규를 찾지 못했습니다.)"
        prompt = (
            "너는 산업안전보건 관련 법규의 전문 검수관이다. 아래 제공된 법령 조항만을 근거로 "
            "수험서 페이지 내용의 사실성 오류를 찾아내고, 필요한 경우 수정 제안을 제시하라.\n\n"
            "[법령 컨텍스트]\n"
            f"{context}\n\n"
            "[검수 대상 텍스트]\n"
            f"{page_text}\n\n"
            "[응답 형식]\n- 사실과 다른 부분\n- 관련 법령 근거\n- 수정 제안"
        )
        return prompt

    def generate_report(self, page_text: str) -> str:
        retrievals = self.retrieve(page_text)
        prompt = self.build_prompt(page_text, retrievals)
        logger.info("Generating proofreading report with %d retrieved contexts", len(retrievals))
        return self.llm_client.generate(prompt)


__all__ = ["RAGValidator", "RetrievalResult", "BaseLLMClient", "LocalTemplateLLM"]
