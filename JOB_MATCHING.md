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

The existing four numeric fields remain under `breakdown`. Four nested objects now provide their inputs:

| Parent field | Nested object and sub-scores | Fixed weights |
|---|---|---|
| `skill_match_score` | `skills`: `hard_skills_match`, `tools_and_frameworks_match`, `soft_skills_match` | 50%, 30%, 20% |
| `semantic_similarity_score` | `context`: `domain_relevance`, `responsibilities_match`, `summary_alignment` | 30%, 50%, 20% |
| `experience_score` | `experience`: `years_of_experience_fit`, `title_seniority_match`, `recency_factor` | 60%, 25%, 15% |
| `education_score` | `education`: `degree_level_fit`, `field_of_study_relevance`, `certifications_match` | 60%, 25%, 15% |

Each leaf is rounded to two decimals, then the parent is the rounded weighted sum of the returned leaves. The raw overall score aggregates the four returned parent scores using 40/30/20/10. Parent scores therefore intentionally differ from older releases. Existing scalar keys remain API-compatible; clients can additionally render the nested objects. The dashboard displays all 12 sub-scores.

- **Hard skills and tools:** mandatory recognized skill coverage, with tools/frameworks partitioned from other technical skills. Docker, Git, databases, and known frameworks enter the tools category. Aliases and explicit custom skill lists remain supported. Unknown explicit skills default to the hard category.
- **Soft skills:** recognized communication, leadership, teamwork, problem solving, critical thinking, Agile, Scrum, and Kanban coverage. Both native `soft_skills` and dashboard `skills.soft` are accepted. These do not inflate technical coverage.
- **Domain:** coverage of recognized software, finance, healthcare, creative, hospitality, and engineering contexts. This is a curated contextual rule, not unrestricted industry understanding.
- **Responsibilities and summary:** separately sanitized professional duties and summary are compared with positive job requirements using the configured semantic backend. Missing evidence scores zero. Optional cross-encoder refinement updates duties when present, otherwise summary; `model_routing.reranked_field` identifies the affected leaf. The context parent is always recomputed afterward.
- **Years:** elapsed, merged work intervals divided by required years, capped at 100. Overlapping roles are not double counted; ongoing roles end at today's UTC date. Partial dates assume the first day. Missing, ambiguous, or reversed intervals contribute no years.
- **Title/seniority:** recognized role overlap multiplied by documented seniority fit, taking the strongest past title. Levels are intern=1, junior=2, mid=3, senior=4, lead/principal/staff/director=5. Missing seniority scores zero when the JD explicitly requires it; no recognized role/seniority constraint scores 100. This coarse vocabulary does not establish equivalence between all engineering specialties.
- **Recency:** the latest valid employment end date scores 100 for the first year, then decays with a five-year half-life: `100 * 2 ** (-max(0, years_since_end - 1) / 5)`. No valid work interval scores zero. This uses work dates, never candidate age.
- **Degree:** documented level meeting the recognized minimum scores 100, otherwise zero. Hierarchy: high school, associate, bachelor, master, doctorate.
- **Field:** coverage of recognized academic subjects found in degree/major fields against the JD. The initial vocabulary includes computing, software engineering, business, finance, medicine and engineering; grouped subjects are approximate.
- **Certifications:** recognized required names matched only against the certification section, including aliases for PMP, CKA, AWS Solutions Architect, CISSP, CPA, Scrum Master, and CPR. Dashboard `certificateName`, native `certification_name`, `name`, and string entries are supported. This checks documented presence, not validity, expiry or verification of licenses. Unknown credentials are not automatically interpreted.

No recognized requirement in a category means 100 (no constraint), not verified qualification. If no technical or soft requirements are recognized at all, all three skill leaves are zero. Missing summary, duties, or valid employment dates score zero. Optional requirements are excluded where recognized; requirement and negation detection remain rule-based. Weights are fixed and never redistributed. Scores are compatibility indicators, not calibrated probabilities of job performance.

Final `match_percentage` applies explicit evidence guards after the weighted sum: documented hard exclusions yield 0; contradictory supported acronym domains cap the score at 9; zero recognized required-skill overlap caps it at the lower of 9 and 9% of the semantic component. `scoring_adjustments` explains every applied guard. These conservative caps can underestimate candidates whose skills fall outside the vocabulary.

Verdicts: **Highly Suitable ≥80**, **Suitable ≥60**, **Partially Suitable ≥40**, otherwise **Low Compatibility**.

## Response

The response includes `match_percentage`, `verdict`, `breakdown`, `skills_analysis` (`matched_skills`, `missing_skills`), and `recommendations`. Additional diagnostic fields expose `semantic_method`, `experience_analysis`, `education_analysis`, `warnings`, `raw_match_percentage`, `scoring_adjustments`, and `model_routing` so missing evidence, policy caps, and fallback scoring are visible.

Only professional summary, skills, work titles/responsibilities/dates, education degree/subject, certifications, and project descriptions/technologies enter matching. Personal information, contact data, filenames, parser confidence, and raw extraction metadata are excluded. No CV text is sent to an external inference API.

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

A stage-one score between 40 and 70 inclusive, recognized exclusions, negation, or short uppercase acronyms routes the request to an optional cross-encoder. It refines only the duties or summary sub-score; hard exclusions and evidence caps still apply afterward. Pre-cache the actual public model identifier:

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

## Granular scoring validation

`tests/test_job_matcher.py` verifies every nested leaf, exact fixed-weight aggregation, API serialization, category separation, missing evidence, certification aliases, degree/major mismatch, seniority, recency, and bounded inputs. `tests/job_matching_frontend.test.cjs` verifies nested score rendering. The prior hard-mode report describes the earlier release; numeric parent scores have intentionally changed in this release.

Validation result for this release: **214 Python tests passed; 12 frontend tests passed**, including all 22 hard-mode adversarial/routing cases.
