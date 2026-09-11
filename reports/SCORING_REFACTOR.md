# Semantic context, relevant tenure and active weights

The original dataset and reference PDF/JSON are unchanged. All ten pairs executed with real cached `sentence-transformers/all-MiniLM-L6-v2` embeddings, offline, with reranking disabled. Results are in `semantic_refactor_results.json`.

MAE decreased from **8.52 to 4.12 percentage points**. Alignment increased from **91.48% to 95.88%**; **8/10** pairs are within the frozen 10-point tolerance, versus 5/10 before. Pairs 4 and 5 still fail alignment. No labels were changed or score floors introduced. This small synthetic set is not proof of general accuracy.

| Pair | AI target | Previous TF-IDF | Refactored semantic | Delta |
|---|---:|---:|---:|---:|
| 1 | 95 | 82.14 | 92.35 | 2.65 |
| 2 | 94 | 81.68 | 94.44 | 0.44 |
| 3 | 91 | 82.47 | 93.84 | 2.84 |
| 4 | 63 | 66.47 | 75.14 | 12.14 |
| 5 | 57 | 67.88 | 68.35 | 11.35 |
| 6 | 48 | 56.07 | 50.13 | 2.13 |
| 7 | 25 | 35.24 | 21.17 | 3.83 |
| 8 | 18 | 34.82 | 13.84 | 4.16 |
| 9 | 2 | 0.00 | 0.45 | 1.55 |
| 10 | 0 | 0.00 | 0.12 | 0.12 |

## Implementation

- `job_matcher.py`: scoped duties/summary semantic comparison, relevant work intervals, dynamic aggregation, exposed `effective_weights`; exclusion and domain guards remain final overrides.
- `match_dimensions.py`: role-family/domain filtering before interval merging; no-requirement coverage is zero; proportional active-weight normalization.
- `job_match.py`: optional additive `effective_weights` field; all prior response keys and types remain intact. Archived responses still deserialize.
- `match_benchmark.py`: automatic local semantic backend by default; deterministic tests explicitly use TF-IDF. The benchmark never downloads models at request time.

The old 12-19% values were lexical similarities, not an explicit cap. The refactor uses actual semantic embeddings rather than artificially raising low scores. Unrelated Chef/Financial Analyst jobs no longer contribute ML/DevOps years or recency. Missing required certifications remain active penalties; absent certification requirements have zero weight. Weights depend on JD requirements, not whether the candidate supplied evidence.

## Deployment and reproduction

```bash
python -m pip install '.[matching,benchmark,test]'
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', device='cpu', trust_remote_code=False)"
python -m tests.test_benchmark_matcher --backend auto --output-dir reports/semantic-rerun
python -m pytest -q
node --test tests/frontend.test.cjs tests/job_matching_frontend.test.cjs
```

Cached local weights are not committed to Git. Vercel's lightweight resource policy still uses the disclosed lexical fallback; deploy on a host with enough memory and the cached model for the semantic path. Role-family rules and administrative-clause detection have limited vocabulary. Review transferability manually where job titles are ambiguous.

## Validation and compatibility

All original 229 test cases remain; assertions that explicitly required automatic 100% credit or the old fixed aggregates were updated to the requested rules. Mixed-language tests still require full technical coverage and now check absence of invented experience/education credit instead of an old overall-score floor. Six new regressions test unrelated tenure, unstated weights, required credential penalties, archived schema compatibility, scoped semantic inputs and title-free technical requirements. Full validation: 235 Python and 12 frontend tests passed.
