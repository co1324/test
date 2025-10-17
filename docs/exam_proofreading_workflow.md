# 다단 편집 수험서 자동 검수 프로그램 워크플로우

본 문서는 다단 편집으로 구성된 수험서의 내용을 자동으로 검수하기 위해 설계된 시스템의 전체 동작 흐름을 정리합니다. 워크플로우는
**준비 단계**와 **실행 단계**의 두 구간으로 나뉘며, 각 단계는 다음과 같이 진행됩니다.

## Phase 1. 준비 단계: 지식 베이스 구축

이 단계는 프로그램 초기화 시 단 한 번만 수행됩니다. 최신 법령 PDF(`latest_safety_laws.pdf`)을 근거로 LLM이 참조할 지식 베이스를
미리 구성합니다.

1. **법령 PDF 로드** – 시스템이 최신 법령 PDF를 읽어 들여 전체 텍스트를 메모리로 가져옵니다.
2. **텍스트 분할** – 법령 텍스트를 의미 단위로 분할해 후속 처리를 위한 청크를 생성합니다.
3. **벡터 임베딩 및 DB 구축** – 각 청크를 임베딩하여 벡터 데이터베이스를 구축함으로써, 관련 조항을 빠르게 검색할 수 있는 기반을
마련합니다.

## Phase 2. 실행 단계: 페이지별 자동 검수 루프

이 단계는 수험서 PDF(`sample_exam_book.pdf`)의 각 페이지에 대해 반복됩니다.

1. **입력 및 이미지 변환** – 수험서 PDF의 페이지를 고해상도 이미지로 변환합니다.
2. **레이아웃 분석** – OpenCV 기반 레이아웃 분석으로 페이지의 단 구조(2단/3단)를 파악하고, 각 단 이미지를 개별적으로 분리합니다.
3. **순차적 OCR 및 텍스트 재조합** – 분리된 단 이미지를 좌측에서 우측 순으로 OCR 처리하고, 추출된 텍스트를 독서 순서에 맞춰 재조
합합니다.
4. **RAG 기반 LLM 검증** – 재조합된 페이지 텍스트를 질의로 사용하여 벡터 데이터베이스에서 관련 법규를 검색(Retrieve)하고, 검색된
 문맥과 페이지 텍스트를 함께 LLM에 제공해 검수 리포트를 생성(Generate)합니다.
5. **결과 출력** – 생성된 검수 리포트를 사용자에게 전달하고, 다음 페이지로 이동해 반복합니다.

## 전체 흐름 다이어그램

```mermaid
graph TD
    subgraph "Phase 1: 준비 (최초 1회)"
        A[법령 PDF 입력] --> B(텍스트 분할)
        B --> C{벡터 임베딩}
        C --> D[벡터 DB 구축]
    end

    subgraph "Phase 2: 실행 (페이지별 반복)"
        E[수험서 PDF 입력] --> F(Loop: For Each Page)
        F --> G[1. 페이지 → 이미지 변환]
        G --> H[2. 레이아웃 분석]
        H --> I[3. OCR 및 텍스트 재조합]
        I --> J{4. RAG 기반 검증}
        D --> J
        J --> K[5. 검수 리포트 출력]
        K --> F
    end
```

## 기대 효과

- **정확한 텍스트 추출**: 다단 편집을 고려한 OCR 순서 제어로 텍스트 순서 뒤바뀜을 방지합니다.
- **신뢰도 높은 검증**: 최신 법령 기반의 RAG 파이프라인을 통해 LLM이 사실에 근거한 검수를 수행합니다.
- **자동화된 반복 처리**: 페이지 단위 루프 구조로 전체 수험서를 자동 검수할 수 있습니다.

## 구현 개요

본 워크플로우는 `exam_proofreading` 패키지로 구현되어 있으며, 다음 구성 요소로 나뉩니다.

- `KnowledgeBaseBuilder` – `PyPDF2`와 `scikit-learn`을 이용해 법령 PDF를 청크 단위로 분할하고 TF-IDF 벡터로 임베딩합니다.
- `ColumnDetector` – OpenCV 기반의 수직 투영 분석으로 2단/3단 레이아웃을 감지합니다.
- `OCRProcessor` – `pytesseract`를 이용해 분리된 단 이미지를 좌에서 우 순으로 OCR 처리합니다.
- `RAGValidator` – 검색된 법령 조각과 페이지 텍스트를 결합해 LLM에게 검수 리포트를 요청합니다.
- `ExamProofreader` – 위 단계 전체를 연결하여 페이지별 리포트를 JSON 형식으로 저장합니다.

CLI 진입점은 `pyproject.toml`의 `exam-proofreader` 스크립트로 노출되며 다음과 같이 실행할 수 있습니다.

```bash
python -m exam_proofreading.cli sample_exam_book.pdf latest_safety_laws.pdf --output reports
```

실행 결과는 `reports/` 디렉터리에 페이지별 JSON 리포트와 요약 파일(`summary.json`)로 저장됩니다.

## 실행 가이드 (차근차근 따라하기)

1. **필수 프로그램 설치**
   - Python 3.10 이상
   - [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) (한국어 학습 데이터 `kor.traineddata` 포함)
   - `poppler` 또는 `mupdf` 기반 PDF 렌더러 (예: Ubuntu에서는 `sudo apt install poppler-utils`)
2. **가상환경(선택)**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows는 .venv\Scripts\activate
   ```
3. **의존성 설치**
   저장소 루트(`/workspace/test`)에서 다음 명령을 실행합니다.
   ```bash
   pip install -e .
   ```
4. **데이터 준비**
   - 검수 대상 수험서 PDF (예: `sample_exam_book.pdf`)
   - 참조할 최신 법령 PDF (예: `latest_safety_laws.pdf`)
5. **기본 실행**
   ```bash
   exam-proofreader sample_exam_book.pdf latest_safety_laws.pdf --output reports
   ```
   - 최초 실행 시 `knowledge_base.pkl`이 생성되며 이후 재사용됩니다.
6. **결과 확인**
   - `reports/` 폴더에 페이지별 `page_XXX.json` 리포트와 `summary.json`이 생성됩니다.
   - 로그는 터미널 또는 `--log-level` 옵션을 통해 조정 가능합니다.
7. **자주 사용하는 옵션**
   - `--dpi 400` : PDF → 이미지 변환 해상도를 높여 OCR 정확도 향상
   - `--max-pages 10` : 앞쪽 10페이지만 시험 실행
   - `--knowledge-base custom_cache.pkl` : 지식 베이스 캐시 파일명 변경
8. **문제 해결 팁**
   - OCR 결과가 비어 있으면 Tesseract 경로가 올바른지 확인합니다.
   - PDF 렌더링 실패 시 `pymupdf`가 설치되어 있는지 또는 `poppler-utils`가 설치되어 있는지 점검합니다.
   - GPU가 필요하지 않으므로 CPU 환경에서도 실행 가능합니다.

필요 시 `exam-proofreader --help`로 전체 옵션을 확인할 수 있습니다.
