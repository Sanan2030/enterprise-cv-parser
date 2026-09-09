# Validation record

Executed in the creation workspace with Python 3.12.13 on Linux.

| Check | Observed result |
| --- | --- |
| Pytest | 87 passed in 5.44 seconds |
| Statement coverage | 92% (944 statements, 76 missed) |
| Ruff lint | Passed |
| Ruff formatting | 47 Python files formatted |
| Dependency consistency (`pip check`) | No broken requirements |
| Editable package build/install | Passed |
| Real PDF extraction | Passed with synthetic digital PDF |
| Real English Tesseract OCR | Passed with generated raster page |
| Real API subprocess parse | Passed |
| Temporary-directory cleanup | Passed for success, invalid PDF, and forced worker timeout |
| OCR failure integrations | Mocked missing language and timeout cases passed |
| LLM integrations | Mocked disabled, malformed schema, network failure, ungrounded and grounded suggestions passed |
| Source AST check | No `pass` statements; all function return annotations present |
| Docker build/run | Not executed: Docker unavailable |
| Real AZ/TR/RU OCR | Not executed: only English and orientation packs installed on host |
| Live LLM | Not executed: no credentialed request made |
| Real candidate PDF | Not supplied for this task |
| GitHub publication | Initial creation blocked; user subsequently supplied the destination repository. See commit history for publication. |

Coverage is statement coverage measured in the parent pytest process. The worker module is executed by real API tests but is not instrumented for subprocess coverage, so it appears as 0% in `validation-output.txt`. This is not 100% branch or scenario coverage and says nothing by itself about extraction accuracy on arbitrary CVs.

One dependency deprecation warning was emitted by Starlette TestClient about the AnyIO BlockingPortal alias. It did not fail the tests and has not been suppressed.

The full pytest coverage table is in `validation-output.txt`. `constraints.txt` captures the resolved package versions before installing this project; it contains no credentials or local editable project paths. The app sends no candidate data over the network unless its optional LLM fallback is explicitly enabled.


## Dashboard integration validation (2026-09-09)

- Python regression suite: **95 passed**, including the original parser tests, real `/api/extract-cv` subprocess requests, multipart CORS preflight, CORS on size-limit errors, native PDF table extraction, missing-field behavior and dashboard/config routes.
- Frontend JavaScript: syntax checked with Node; **4 Node tests passed** for edited nested JSON/table export, CSV formula neutralization, Unicode/newline/empty-array handling, and comprehensive TXT output.
- Ruff lint and formatting passed for updated Python sources.
- Browser rendering, click-through interaction testing and Docker execution were not performed; no claim of visual or container verification is made.
- Earlier 92% coverage is historical; coverage was not remeasured for this integration.
