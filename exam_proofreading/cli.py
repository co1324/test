"""Command line interface for the exam proofreading workflow."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .config import KnowledgeBaseConfig, LLMConfig, LayoutConfig, OCRConfig, PipelineConfig, RetrievalConfig
from .pipeline import ExamProofreader

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="다단 편집 수험서 자동 검수 프로그램")
    parser.add_argument("exam_pdf", type=Path, help="검수할 수험서 PDF 경로")
    parser.add_argument("law_pdf", type=Path, help="참조할 법령 PDF 경로")
    parser.add_argument("--knowledge-base", type=Path, default=Path("knowledge_base.pkl"), help="지식 베이스 캐시 파일 경로")
    parser.add_argument("--output", type=Path, default=Path("reports"), help="검수 리포트를 저장할 디렉토리")
    parser.add_argument("--dpi", type=int, default=300, help="PDF 페이지 렌더링 DPI")
    parser.add_argument("--language", type=str, default="kor+eng", help="OCR 언어 설정")
    parser.add_argument("--max-pages", type=int, default=None, help="처리할 최대 페이지 수")
    parser.add_argument("--log-level", type=str, default="INFO", help="로깅 레벨")
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> PipelineConfig:
    knowledge_base_cfg = KnowledgeBaseConfig(
        law_pdf_path=args.law_pdf,
        output_path=args.knowledge_base,
    )
    ocr_cfg = OCRConfig(language=args.language, dpi=args.dpi)
    layout_cfg = LayoutConfig()
    retrieval_cfg = RetrievalConfig()
    llm_cfg = LLMConfig()
    page_range = None
    if args.max_pages is not None:
        page_range = range(args.max_pages)
    config = PipelineConfig(
        exam_pdf_path=args.exam_pdf,
        knowledge_base=knowledge_base_cfg,
        ocr=ocr_cfg,
        layout=layout_cfg,
        retrieval=retrieval_cfg,
        llm=llm_cfg,
        output_dir=args.output,
        page_range=page_range,
    )
    return config


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    config = build_config(args)
    proofreader = ExamProofreader(config)
    results = proofreader.run()
    summary_path = config.output_dir / "summary.json"
    summary = {
        "exam_pdf": str(config.exam_pdf_path),
        "law_pdf": str(config.knowledge_base.law_pdf_path),
        "pages": [
            {
                "page": result.page_number,
                "ocr_confidence": result.ocr_confidence,
                "report_file": str(result.output_path),
            }
            for result in results
        ],
    }
    with summary_path.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    logger.info("검수 요약 파일 생성: %s", summary_path)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
