# OCR reliability implementation plan

**Goal:** Improve transcript extraction without deleting zero-credit or uncertain courses or overwriting confirmed records.

**Architecture:** Local OCR adapters return text, bounding boxes and engine confidence. A geometric table parser binds cells by position, not independent text-line order. Saved-source reanalysis creates a revisioned draft, with explicit confirmation required to replace confirmed data.

**Tech stack:** Flask, Pillow, Tesseract, optional PaddleOCR PP-OCRv5, PDFium, pytest.

**Scope:** User-approved five limitations and zero-credit retention from this conversation. No cloud document upload, no claims of measured accuracy without labelled evaluation.

## Tasks and contracts

- [x] `ocr_engines.py`: `recognize(image, engine)` returns dictionaries with text, bbox in input pixels, confidence 0..1 or None. Tests cover both actual provider response shapes, missing dependencies and errors. Optional pinned requirements and setup guide.
- [x] `ocr_pipeline.py`: load images/PDF pages with limits; detect printed grids and largest body gap; identify each semester's credit/score cells separately. Preserve missing fields, distinct rows and 0 credits; attach source coordinates and review reasons. Unknown layouts use conservative traceable fallback rather than guessed column zips. Regression tests in `test_ocr_pipeline.py`.
- [x] `document_analysis_service.py`: route ocr/tesseract/paddleocr to pipeline, preserve fake provider. Remove unsafe semantic deduplication. Configuration and base requirements updated. Existing upload tests adapted to new contract.
- [x] student routes/templates: owner-only source preview and reanalysis; maintain prior draft on failure; revision token blocks stale confirmations; maintain confirmed records until explicit confirmation. Five editable fields, field confidence clearly labelled not accuracy. Tests cover ownership, failure, revision conflict, 0 credits and unknown grade.
- [x] Integrate, run targeted tests then full suite, exercise actual saved source without logging personal data. Record residual deployment/model-download limitations honestly.

## Review focus

1. Equal scores/credits on different rows are distinct courses.
2. Low scores 0..9 must not become credits; never choose maximum number as score.
3. Empty/low-confidence fields must not silently shift later rows.
4. Multi-page malformed/encrypted/oversized PDFs fail clearly with bounded resource use.
5. Reanalysis/crop access must enforce ownership, preserve confirmed data, and reject stale drafts.

## Verification baseline

Before changes: 97 tests passed, two existing migration tests fail because `student_profiles` is absent. Sandbox pytest temp permissions require elevated execution. These unrelated migrations are not modified by the OCR work.

## Final verification

182 passed, two pre-existing migration failures (`student_profiles` absent). `pip check` passed. Local website launched using the OCR virtual environment with PaddleOCR; `/login` returned HTTP 200. Native full-document test completed; accuracy is not certified and CPU latency remains approximately eight minutes per tested image. See `docs/ocr-setup.md` for limitations and startup instructions.
