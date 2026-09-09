# Enterprise CV Parser

Python 3.12 / FastAPI service for extracting multilingual PDF resumes into a Pydantic v2 response with source evidence. Derived from the supplied architecture and substantially rewritten to remove fabricated values, broken date/phone handling, unsafe concurrency, and missing modules.

This is a tested implementation, not a certification of production readiness or universal resume accuracy. See [AUDIT.md](AUDIT.md) for measured validation and remaining limitations. No real candidate PDF was supplied in this task; tests generate synthetic documents. The example candidate output in the blueprint was not treated as ground truth.

## Run with Docker

```bash
cd enterprise-cv-parser
docker compose up --build -d
```

Open the [PDF Intelligence Platform](http://localhost:8000/) to upload, preview, edit and export a PDF. [Swagger UI](http://localhost:8000/docs) and [health](http://localhost:8000/api/v1/health) remain available.

```bash
curl -X POST http://localhost:8000/api/v1/resume/parse \
  -H 'Accept: application/json' \
  -F 'file=@resume.pdf;type=application/pdf'
docker compose logs -f cv-parser-api
docker compose down
```

Compose binds only to localhost. It uses a non-root container, a read-only root filesystem, a temporary in-memory directory, and resource limits. Tesseract English, Azerbaijani, Turkish, and Russian packs are installed in the image. No candidate uploads are retained. The Python API uses temporary directories and closes multipart uploads on success and error. Each worker and its Tesseract child use that same per-request temporary directory, so OCR intermediates are also removed after forced worker termination.

## Dashboard and frontend API

`index.html` is a single-file HTML/CSS/Vanilla JavaScript dashboard served at `/` and `/index.html`. It includes Tailwind CSS, FontAwesome and PDF.js via CDNs. No Node build or frontend server is needed. Main styling is embedded so core controls remain usable if the CSS CDN is unavailable. PDF preview requires the PDF.js CDN; its failure does not prevent extraction.

After pulling an update, rebuild your running container:

```bash
git pull origin main
docker compose up --build -d
```

Visit [http://localhost:8000/](http://localhost:8000/). Upload one PDF by button or drag-and-drop. Review the editable fields and tables; export JSON, flattened CSV, or TXT, or copy JSON. Add/remove experience, education, skills, language, certification, project and table entries. Table titles, headers and cells are editable; rows and columns can be added or removed. Dark/light theme is the only value saved to browser storage. Documents, API keys and edits remain in tab memory; export before closing. JSON download initiation clears the unsaved-edit banner, but the browser/user controls whether the file is ultimately saved.

`POST /api/extract-cv` takes the same multipart `file` upload and returns the camelCase dashboard schema.

## Vercel deployment

Vercel now uses the explicit `app.main:app` FastAPI entrypoint configured in `pyproject.toml`. Deploy the current `main` branch again from Vercel; the previous build used commit `7d62cae`, before the Vercel configuration. The runtime dependencies have been reduced so Vercel does not install OCR, spaCy, or Lingua packages by default.

The deployed Vercel app parses **digital/text PDFs** in-process. Tesseract needs a system binary and is unavailable on Vercel Functions, so scanned/image-only PDFs return an extraction warning or no-readable-text error. For scanned PDF OCR, run this same project with Docker or locally and install the optional dependencies:

```bash
pip install -e '.[ocr,nlp]'
```

The Docker image and CI test environment install those extras automatically. Vercel also excludes test files from the function bundle.
 `GET /api/config` exposes only whether LLM fallback/API-key authentication is enabled and the upload limit; it never returns a secret. The original `/api/v1/resume/parse` response remains compatible. Both POST endpoints appear with a file picker in OpenAPI.

```bash
curl -X POST http://localhost:8000/api/extract-cv \
  -F 'file=@resume.pdf;type=application/pdf'
```

The frontend uses the current origin when served by FastAPI. Opening `index.html` directly defaults to `http://localhost:8000`; use Connection settings for a different server or an existing `X-API-Key`. CORS explicitly permits all origins, methods and headers, with credentialed cookies disabled, as requested. API-key enforcement and all existing document limits also apply to the new endpoint.

The dashboard response includes `personalInformation`, `contactInformation`, `professionalInformation`, `experience`, `education`, `skills`, `languages`, `certifications`, `projects`, `summary`, `tables`, and `confidenceScores`. It also includes `metadata` for real page/word/contact counts, extraction method, language, processing time, LLM mode and warnings. Missing string values are empty; unsupported demographic/career details are not inferred. Confidence is converted from existing evidence scores to 0–100 rather than using fixed sample numbers. Manual edits retain the original scores and are marked as manually edited. Unscored fields appear under the Low / unscored filter.

Table extraction runs with pdfplumber inside the same bounded worker as parsing. Native ruled tables are supported, with a 5,000-cell ceiling. The first visible row is retained as data; neutral column labels avoid guessing that it is a header. Scanned tables are not reconstructed into structured cells automatically; they can be reviewed in the PDF preview and entered manually. An optional-table parser failure leaves CV extraction intact with a warning; resource-limit failures still reject the document.

The eight-step indicator shows preparation, dispatch, processing and completion. Backend substeps are marked active together while waiting because the REST API does not emit stage telemetry. Reset/replacement aborts the browser request and ignores stale results; an already-running server process can continue until its own deadline. The privacy badge reports the chosen server and whether external AI is enabled, not a guarantee that CDN scripts or a remote server are offline.

Frontend checks (Node 18+):

```bash
node --test tests/frontend.test.cjs
```

These validate JavaScript syntax and export behavior without browser automation. Browser visual/interaction QA has not been performed in this update.

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
