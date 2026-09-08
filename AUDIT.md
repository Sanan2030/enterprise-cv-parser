# Architecture audit

## Corrections applied

| Supplied implementation problem | Implemented correction |
| --- | --- |
| Layout partitions overlap and omit spanning blocks | Mutually exclusive lane assignment and spanning title/footer bands |
| Entire PDF replaced by OCR based on aggregate text length | Page-level raster/text assessment and mixed extraction metadata |
| OCR flattened to one page-size box | Tesseract word data grouped into lines with PDF coordinate conversion |
| `List` missing in OCR module | Valid imports and typed public extraction interfaces |
| Phone regex returns capture groups rather than a full number | Region-aware PhoneNumberMatcher and validated E.164 output |
| Date split regex splits individual letters and ISO components | Explicit range grammar and precision-preserving multilingual date normalization |
| Name is always the first text block | Conservative header candidate checks, optional spaCy NER, null on uncertainty |
| Fake job/company names and hardcoded confidence | Extracted header values only and explicitly heuristic evidence scores |
| Education and several files absent | Education, detector, URL, hyperlink and provenance modules implemented |
| LLM exists but is not invoked, returns unchecked dictionaries | Service integration, Pydantic response validation, exact evidence checks and disabled-by-default network use |
| Unsupported Ollama configuration appears functional | Removed unsupported provider setting |
| CPU parsing runs inside the async endpoint | Separate killable worker process with capacity limit |
| Whole upload read without an enforced stream cap | Bounded total request body and file limit; multipart part-count controls |
| Temp handles and PDF objects can leak on errors | Context-managed documents/images/uploads and temporary worker directory |
| Internal exceptions returned to clients and logs | Sanitized client errors and structured logs without document contents |
| Docker installs project before copying package and README | Copy valid source before install, explicit package discovery, non-root runtime |
| OCR configured for uninstalled languages | Matching default packs in Docker and explicit runtime warnings |
| Confidence conflates completeness and accuracy | Evidence score labeled uncalibrated; missing fields tracked separately |
| Example output contains unexplained invented candidate facts | Synthetic tests and no reuse of candidate-specific sample assertions |

## Boundaries

This implementation does not establish 100% production readiness, 100% test coverage, or full semantic extraction accuracy. No real-world labeled multilingual CV benchmark, penetration test, production load test, live LLM request, or Docker runtime validation was completed here. Synthetic regression tests cover representative utility/API cases and real English OCR; mocked tests exercise OCR failures and LLM responses.

Two-column layout is a gutter heuristic. Tables, sidebars with overlapping elements, three columns, rotated text, graphical text, same-page images alongside substantial native text, and complex reading orders can still fail. pdfplumber is a native recovery path, not a complete table semantics engine. OCR does not perform dedicated deskew or orientation correction.

Experience grouping uses dated or prominent headers and can misassociate undated/ambiguous entries. Certificate/project lines are preserved but not fully semantically grouped; detailed fine-grained schema fields can remain null. All section text is available for review in `raw_sections`. Source snippets for compound fields identify the first contributing block; the remaining source blocks remain in `raw_sections`. Social URLs are retained but not fetched or ownership verified. Name heuristics can confuse organization/location names, so manual review remains necessary.

Confidence is not calibrated against human labels. Lingua secondary-language reporting requires repeated strong line evidence, but short/noisy language identification can still be wrong. Ambiguous numeric dates are unresolved and do not have individual field warning codes. Optional spaCy NER requires separately installed, evaluated language models. Native parsing may allocate memory before post-extraction character checks; Docker memory/CPU limits and isolated workers are part of the containment strategy. Native host execution does not provide a PDF security sandbox.

Temporary-directory deletion runs on ordinary errors, worker deadlines, and request cancellation. A host or API process crash can leave directories until OS/container cleanup. Linux worker process-group termination handles Tesseract descendants; Windows native execution kills only the Python process. Production should use the provided Linux container and supervise it.

The initial delivery could not create a GitHub repository because the connector lacked that operation. The user subsequently supplied the repository `Sanan2030/enterprise-cv-parser` and authorized publication there. That initial capability limitation is historical; current publication status is recorded in the repository history.
