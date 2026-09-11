# CV-to-job compatibility API

`POST /api/v1/match-job` accepts JSON containing `job_description` and `cv_data`. Pass either the dashboard response from `/api/extract-cv` or the native response from `/api/v1/resume/parse`. Partial CV objects with professional evidence are also supported.

```bash
curl -X POST http://localhost:8000/api/v1/match-job \
  -H 'Content-Type: application/json' \
  -d '{
    "job_description": "Python, FastAPI, Docker, Kubernetes, Redis. Minimum 3 years of experience. Bachelor degree required.",
    "cv_data": {
      "skills": {"technical": ["Python", "FastAPI", "Docker"]},
      "experience": [{"position": "Backend Developer", "startDate": "2020-01", "endDate": "2025-01"}],
      "education": [{"degree": "Bachelor of Science"}]
    }
  }'
```

If `API_KEY` is configured, include `X-API-Key`. The endpoint is also available through FastAPI `/docs`.

## Dashboard workflow

1. Upload a PDF and wait for extraction to finish. The **Job Requirements** panel appears in the sidebar.
2. Paste the vacancy requirements and select **Analyze compatibility**.
3. Review the overall percentage, four component scores, matched/missing skills, and recommendations.

The panel uses the parser URL and API key from Connection settings and submits the current edited CV. Changing the CV, requirements, or connection clears the previous score and cancels pending display updates. Uploading a new document or resetting clears the panel. Timeout and server errors appear inline with a retry button.

Frontend regression checks: `node --test tests/frontend.test.cjs tests/job_matching_frontend.test.cjs`.

## Scores

All component scores are 0–100. The `raw_match_percentage` is the following fixed weighted sum, rounded to two decimals:

`0.40 × skill_match_score + 0.30 × semantic_similarity_score + 0.20 × experience_score + 0.10 × education_score`

- **Skills:** percentage of recognized job skills documented in the candidate's professional evidence. Matches are case-insensitive with aliases such as JS/JavaScript, postgres/PostgreSQL, and k8s/Kubernetes. Known soft skills are excluded. Explicit `Required skills:` comma-separated lists support tools outside the curated vocabulary. An unrecognized hard-skill requirement may be missed; this is rule-based extraction, not unrestricted language understanding.
- **Semantics:** cosine similarity using `sentence-transformers/all-MiniLM-L6-v2`. Token-based chunking and weighted pooling cover documents beyond a single model context window. If loading or encoding fails, scikit-learn TF-IDF cosine similarity is used. The response's `semantic_method` identifies the actual method. Negative cosine values are clamped to zero.
- **Experience:** `min(candidate years / required years, 1) × 100`. Employment intervals are merged to avoid counting overlapping roles twice. Current positions end at today's UTC date. Invalid, future, and ambiguous intervals are excluded; month/year-only dates assume the first day and produce a warning. Years are elapsed days divided by 365.2425. Explicit requirements such as “3–5 years of experience” use the lower bound; multiple requirements use the largest lower bound. This compares total experience, not years in each specific skill or role.
- **Education:** 100 when the documented level meets or exceeds the minimum recognized level, otherwise 0. Hierarchy: high school, associate, bachelor, master, doctorate. Recognized alternatives use the lowest acceptable level. Optional/preferred education clauses do not impose a penalty. Qualifications and completion status are not independently verified.

If no numeric experience or mandatory education requirement is recognized, that component is 100 (no constraint). If no hard skills are recognized, skill coverage is 0 with an explicit warning. Weights are never silently redistributed. Scores are compatibility indicators, not calibrated probabilities of job performance.

Final `match_percentage` applies explicit evidence guards after the weighted sum: documented hard exclusions yield 0; contradictory supported acronym domains cap the score at 9; zero recognized required-skill overlap caps it at the lower of 9 and 9% of the semantic component. `scoring_adjustments` explains every applied guard. These conservative caps can underestimate candidates whose skills fall outside the vocabulary.

Verdicts: **Highly Suitable ≥80**, **Suitable ≥60**, **Partially Suitable ≥40**, otherwise **Low Compatibility**.

## Response

The response includes `match_percentage`, `verdict`, `breakdown`, `skills_analysis` (`matched_skills`, `missing_skills`), and `recommendations`. Additional diagnostic fields expose `semantic_method`, `experience_analysis`, `education_analysis`, `warnings`, `raw_match_percentage`, `scoring_adjustments`, and `model_routing` so missing evidence, policy caps, and fallback scoring are visible.

Only professional summary, hard skills, work titles/responsibilities, education degree/subject, and project descriptions/technologies enter matching. Personal information, contact data, filenames, parser confidence, and raw extraction metadata are excluded. No CV text is sent to an external inference API.

## Dependencies and model setup

The default `pip install .` installs scikit-learn and supports TF-IDF without PyTorch. This keeps the existing minimal deployment viable. `requirements.txt` includes both requested NLP packages for a full installation:

```bash
pip install -r requirements.txt
```

Alternatively install `pip install '.[matching]'`. For CPU-only deployments, install the CPU build of PyTorch for your platform first, following the official PyTorch installation instructions.

By default, `MATCH_SEMANTIC_BACKEND=auto` tries a locally cached MiniLM model and falls back to TF-IDF. `MATCH_MODEL_LOCAL_ONLY=true` prevents model downloads during requests. Pre-cache the public model in the deployment environment:

```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
```

Set `MATCH_SEMANTIC_BACKEND=tfidf` to force lexical scoring. Set `MATCH_MODEL_LOCAL_ONLY=false` only if initial model downloads are desired; first-use latency and disk requirements will increase. Restart after installing or caching a previously unavailable model because the availability result is cached per process. MiniLM is primarily English-oriented; cross-language matching is not guaranteed. TF-IDF is lexical, not contextual.

Inputs are capped at 20,000 job-description characters and 100,000 serialized CV characters, with bounded nested collections. Invalid input returns 422, invalid configured API keys return 401, and exhausted shared analysis capacity returns 503. CPU work runs off the async event loop. Logs contain timings and backend names, not document text.

## Dynamic reranking and resource policy

A stage-one score between 40 and 70 inclusive, recognized exclusions, negation, or short uppercase acronyms routes the request to an optional cross-encoder. It replaces only the semantic component; hard exclusions and evidence caps still apply afterward. Pre-cache the actual public model identifier:

```bash
python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L6-v2', device='cpu', trust_remote_code=False)"
```

The reranker runs offline in a separate CPU worker. TF-IDF retrieves up to two CV passages for each of the beginning, middle, and end JD chunks. This bounds inference but does not exhaustively evaluate every clause of a long JD. MS-MARCO relevance logits are sigmoid-transformed; the result is not a calibrated hiring probability.

- `MATCH_RERANK_ENABLED=true`: enable optional routing.
- `MATCH_RERANK_TIMEOUT=8`: worker deadline in seconds (1–30).
- `MATCH_RERANK_MEMORY_MB=4096`: POSIX address-space limit in MiB (512–16384), not measured resident memory. Windows uses the deadline without this memory limit.
- Serverless/Vercel requests use TF-IDF and skip the heavy reranker. Combined semantic input above 32,000 characters also skips stage-one embeddings.
- Missing local models, worker failure, memory errors, invalid predictions, and timeouts preserve baseline scoring plus deterministic guards. Responses and structured logs expose the routing reason without logging CV contents.

Instruction-like lines, invisible format characters, exact duplicate clauses, duplicate explicit skills, and highly repetitive unpunctuated keyword lines are normalized or removed. Recognized negated experience is excluded from positive evidence. These are bounded rules, not a guarantee against every adversarial rewrite. Explicit CPR and BA domain conflicts are recognized; arbitrary acronym disambiguation is not guaranteed. English/Azerbaijani/Turkish tests verify shared technical skill retention, not unrestricted translation.

## Validation

```bash
python -m pytest tests/test_job_matcher.py tests/test_job_matcher_hard.py -q
python -m pytest -q
```

The tests cover weighted scoring, real TF-IDF, skill aliases, explicit custom skills, overlapping/current employment, multilingual year expressions, education levels, demographic-field invariance, both parser response formats, embedding chunking/failure handling, request validation, API authentication, and capacity handling. Embedding contract tests use controlled encoders; model-download/inference smoke tests are run separately when the real model is available.

See [MATCH_HARD_REPORT.md](MATCH_HARD_REPORT.md) for adversarial results, full regression counts, real-model smoke evidence, and preserved baseline failures.

Implementation references: [Sentence Transformers](https://sbert.net/docs/package_reference/sentence_transformer/model.html), [scikit-learn TF-IDF](https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html).
