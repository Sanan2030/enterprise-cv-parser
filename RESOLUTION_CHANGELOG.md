# CV parser stress-failure resolutions

All ten previously failing cases now satisfy their original field expectations. The input PDFs and assertions were preserved; no failing cases were removed or relaxed.

| Cases | Bug resolved | Modified files / functions |
|---|---|---|
| 04 | An old name covered by a later opaque rectangle contaminated the visible wrapped name. Filter fully hidden text using drawing order. | `app/extraction/text_integrity.py`: `hidden_text`, `is_hidden`; `app/extraction/text_extractor.py`: `extract` |
| 06 | The second line of a wrapped company name became a responsibility. Join adjacent company continuations immediately before the date range. | `app/parsing/experience_parser.py`: `parse` |
| 07 | The second and third columns were interleaved after the first column was separated. Recursively order each independent column. | `app/extraction/layout_engine.py`: `sort_reading_order` |
| 11 | PDF display rotation made upright raster text unreadable to OCR. Normalize page coordinates before extraction. | `app/extraction/text_extractor.py`: `extract` |
| 14 | Conflicting alphabetic character mappings silently changed names, contacts and section headings. Detect mapping collisions and read the rendered page with OCR. | `app/extraction/text_integrity.py`: `conflicting_cmap`; `app/extraction/text_extractor.py`: `extract` |
| 15 | Missing font mappings left control characters inside accented names. Recover only the affected region with OCR, retaining native text elsewhere. | `app/extraction/text_integrity.py`: `has_unknown_characters`; `app/extraction/serverless_ocr.py` and `app/extraction/ocr_engine.py`: `extract_region`; `app/extraction/text_extractor.py`: `extract` |
| 16 | Decomposed Unicode accents failed alphabetic name validation. Normalize extracted text to NFC. | `app/extraction/text_extractor.py`: `extract` |
| 17–19 | Career Journey, Professional Background and Employment Record were not recognized as work history. Add explicit header aliases. | `app/parsing/section_classifier.py`: `SECTION_DICTIONARY` |

No response-schema changes were needed. Regional OCR errors use the existing controlled `OCRError` exception.

## Validation

- Original stress corpus: **38 passed, 0 failed** — 32 successful extractions and 6 correct rejections. Previously: 28 passed, 10 failed.
- Full Python suite: **152 passed, 0 failed**, including 20 real-PDF regression cases covering both local Tesseract and Vercel OCR paths, plus background visibility and controlled OCR-error tests.
- Frontend suite: **6 passed, 0 failed**.
- Ruff checks passed. The previously supplied Azerbaijani CV still extracts its name, three jobs and durations, two education records, and language levels.
- The stress replay verifies the original SHA-256 checksums. Its report records hashes of the exact tested application files. Original failure evidence remains unchanged.

These results describe the tested corpus and regression suite; they do not establish universal parsing accuracy or verify a live Vercel deployment.

## Test tooling

- `tests/test_stress_regressions.py`: permanent tests for the observed failures.
- `scripts/stress_test.py`: reusable isolated batch runner, including `--corpus` to replay saved PDFs and assertions without regenerating them.
- `pyproject.toml`: adds ReportLab to the test dependencies for synthetic PDFs.

```bash
python -m pytest -q
node --test tests/frontend.test.cjs
python scripts/stress_test.py --repo . --corpus /path/to/original-results --output ./new-results
```

The output directory must be new. Real OCR tests require the English model and local Tesseract for the non-Vercel path. Fixture generation uses DejaVu Sans, with ReportLab's bundled font as the portable regression-test fallback.
