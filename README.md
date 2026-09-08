# Enterprise CV Parser

Python 3.12 / FastAPI service for extracting multilingual PDF resumes into a Pydantic v2 response with source evidence. Derived from the supplied architecture and substantially rewritten to remove fabricated values, broken date/phone handling, unsafe concurrency, and missing modules.

This is a tested implementation, not a certification of production readiness or universal resume accuracy. See [AUDIT.md](AUDIT.md) for measured validation and remaining limitations. No real candidate PDF was supplied in this task; tests generate synthetic documents. The example candidate output in the blueprint was not treated as ground truth.

## Run with Docker

```bash
cd enterprise-cv-parser
docker compose up --build -d
```

Open [Swagger UI](http://localhost:8000/docs) or [health](http://localhost:8000/api/v1/health).

```bash
curl -X POST http://localhost:8000/api/v1/resume/parse \
  -H 'Accept: application/json' \
  -F 'file=@resume.pdf;type=application/pdf'
docker compose logs -f cv-parser-api
docker compose down
```

Compose binds only to localhost. It uses a non-root container, a read-only root filesystem, a temporary in-memory directory, and resource limits. Tesseract English, Azerbaijani, Turkish, and Russian packs are installed in the image. No candidate uploads are retained. The Python API uses temporary directories and closes multipart uploads on success and error. Each worker and its Tesseract child use that same per-request temporary directory, so OCR intermediates are also removed after forced worker termination.

## Run tests

Without installing Python dependencies on your host:

```bash
docker build --target test -t enterprise-cv-parser-tests .
docker run --rm enterprise-cv-parser-tests
```

Local Linux / macOS (Python 3.12 and Tesseract required):

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -c constraints.txt '.[test]'
pytest -q --cov=app --cov-report=term-missing
ruff check .
ruff format --check .
uvicorn app.main:app --host 127.0.0.1 --port 8000 --limit-concurrency 16
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -c constraints.txt '.[test]'
pytest -q
uvicorn app.main:app --host 127.0.0.1 --port 8000 --limit-concurrency 16
```

For native Windows, install Tesseract and put its executable on PATH or set `TESSERACT_CMD`. Docker is preferred: process-group termination also kills an in-flight Tesseract child on Linux; Windows native execution cannot provide that same process-tree guarantee. Tests include a real English OCR smoke test, so English traineddata is required. Missing requested OCR packs produce warnings, not a false claim of multilingual OCR support.

## Pipeline and response

1. Reject files above 15 MiB, invalid PDF signatures/trailers, damaged/repaired files, encryption, and excessive page counts.
2. Extract line geometry and hyperlinks using PyMuPDF; use pdfplumber for native-text recovery when PyMuPDF returns no text and there are no raster images.
3. Detect raster-heavy pages with insufficient text. OCR only those pages using word geometry, explicit language availability, pixel limits, and timeouts.
4. Find a vertical gutter and preserve spanning title/footer bands. Read each column vertically before switching columns.
5. Detect document language with Lingua and classify section headings using exact/fuzzy multilingual dictionaries.
6. Extract contacts, summary, work experience, education, explicit skills, language lines, certificate lines, and project lines. Retain all section content in `raw_sections` with page evidence.
7. Optionally recover missing name/email/summary through schema-validated, exact-quote-gated LLM suggestions.
8. Validate nested Pydantic output and compute an uncalibrated heuristic evidence score.

The result retains the blueprint's nested `document`, `personal_information`, `professional_profile`, `work_experience`, `education`, `skills`, `certifications`, `languages`, `projects`, and `quality` structure. `raw_sections` is added to preserve text that cannot be confidently structured. Unknown fields are null, not invented. A year-only date stays `YYYY`; month and full-day precision are retained as `YYYY-MM` and `YYYY-MM-DD`. Ambiguous numeric dates remain null; their original text is retained.

Name extraction without a configured spaCy model is heuristic. First/last names, nationality, duration, inferred technologies, employment type, and other unsupported fine-grained fields are deliberately not guessed. Certificates and projects are preserved as section lines rather than fully resolving their multi-line relationships. `quality.overall_confidence` is not a probability of correctness, and missing sections are reported separately.

## Configuration

Copy `.env.example` to `.env` for local development. The Compose environment is explicit: add desired settings to its `environment` mapping; it does not automatically forward every `.env` variable into the container.

| Variable | Default | Meaning |
| --- | --- | --- |
| `MAX_UPLOAD_SIZE_MB` | `15` | Maximum file size, capped at 15 MiB |
| `MAX_PAGES` | `30` | Maximum PDF pages |
| `MAX_TEXT_CHARS` | `300000` | Maximum extracted text size |
| `MAX_PAGE_PIXELS` | `20000000` | OCR rendering ceiling |
| `OCR_DPI` | `220` | OCR resolution |
| `OCR_TIMEOUT` | `30` | Seconds per Tesseract call |
| `OCR_LANGUAGES` | `eng+aze+tur+rus` | Requested installed language packs |
| `PARSE_TIMEOUT` | `120` | Total API worker deadline in seconds |
| `MAX_CONCURRENT_PARSES` | `2` | Active worker ceiling per API process |
| `DEFAULT_PHONE_REGION` | `AZ` | Region for local phone numbers |
| `SPACY_MODEL` | unset | Installed spaCy pipeline package or path |
| `API_KEY` | unset | Optional `X-API-Key` authentication |
| `USE_LLM_FALLBACK` | `false` | Explicit opt-in to send CV text to OpenAI |
| `OPENAI_API_KEY` | unset | Secret required for enabled fallback |
| `OPENAI_MODEL` | `gpt-4o-mini` | Configurable structured-output model |
| `LLM_MAX_CHARS` | `30000` | Oversized evidence payloads are skipped, not truncated |

Enable spaCy NER only after installing and evaluating a model for the intended language. No models are downloaded implicitly at startup. Lingua candidates are EN/AZ/TR/RU/DE/FR/ES; OCR availability is separate. Adding OCR languages requires their traineddata packages.

LLM fallback uses OpenAI's chat completions endpoint through HTTPX with a schema. It is intentionally limited to evidence-checkable name/email/summary fields, never overwrites native values, ignores unsupported fields and ungrounded quotes, and skips oversized payloads. Ollama and vision parsing are not exposed as implemented features. No API key or CV contents are logged. Configuring fallback is an explicit data-transfer decision; it can incur provider charges.

## API behavior

| Status | Meaning |
| --- | --- |
| `200` | Parsed response, possibly with warnings or null fields |
| `401` | Invalid/missing configured API key |
| `413` | Request/file/page/text/pixel limit exceeded |
| `415` | Unsupported filename extension or MIME |
| `422` | Missing upload, malformed/encrypted PDF, or no readable text |
| `503` | Parser capacity exhausted or OCR unavailable |
| `504` | Worker exceeded processing deadline |
| `500` | Sanitized internal processing error |

Multipart field name is `file`. Uppercase `.PDF` is accepted. MIME declarations are checked but not trusted in place of PDF validation. Invalid multipart structure may produce framework `400` errors. Health is a liveness endpoint, not an OCR/model/dependency readiness check.

A separate subprocess handles each parse to avoid sharing MuPDF across threads, and is terminated on timeout. A process-count limit and bounded upload body prevent unbounded per-request buffering. The body is buffered up to the upload limit before multipart parsing; the configured server concurrency limit is therefore part of the memory budget. Front production deployments with TLS, authentication, request-body/read deadlines, rate limits, and workload-specific resource controls. The app itself does not implement distributed rate limiting, a durable queue, or tenant isolation.

## Dependencies and evidence

`constraints.txt` records the environment versions used for validation. It is a version constraint snapshot, not a hash-locked supply-chain artifact; OS packages and the Docker base image are not digest pinned. CI runs lint, pytest, and a Docker build. The Docker build was not run in the creation environment because no Docker executable/daemon was available.

References consulted for implementation:

- [PyMuPDF multiprocessing guidance](https://pymupdf.readthedocs.io/en/latest/recipes-multiprocessing.html): MuPDF is not safe for multithreaded use.
- [Starlette request parsing](https://starlette.dev/requests/): `max_part_size` limits non-file fields, so an independent total-body limit is necessary.
- [Pydantic model concepts](https://docs.pydantic.dev/latest/concepts/models/): nested schema validation.

Dependency licenses remain those of their upstream projects. Review them for your distribution model before deployment, including PyMuPDF's licensing terms. The blueprint's star counts and maintenance claims are not repeated as verified research.

## GitHub repository

Source: [Sanan2030/enterprise-cv-parser](https://github.com/Sanan2030/enterprise-cv-parser).

```bash
git clone https://github.com/Sanan2030/enterprise-cv-parser.git
cd enterprise-cv-parser
docker compose up --build -d
```

The initial delivery archive includes `history.bundle` for the original local semantic commits. The repository's `main` branch contains the published implementation and publication documentation updates.
