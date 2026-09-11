# CV-to-job matching benchmark

The checked-in PDF and JSON evaluate ten synthetic CV-JD pairs against independently AI-authored target labels. Labels were frozen before execution in `tests/fixtures/job_match_benchmark.json`; a SHA-256 assertion detects changes. This is a judgment baseline, not a live second-model API, human consensus, or verified ground truth.

## Run

From the repository root with Python 3.12:

```bash
python -m pip install '.[benchmark,test]'
python -m tests.test_benchmark_matcher
python -m pytest tests/test_benchmark_matcher.py -q
```

Output: `reports/benchmark_match_results.pdf` and `reports/benchmark_match_results.json`.

The default run uses real TF-IDF with reranking disabled for reproducibility. To test installed, locally cached embedding/reranking models:

```bash
python -m pip install '.[benchmark,matching]'
python -m tests.test_benchmark_matcher --backend auto --rerank --output-dir reports/auto
```

No model is downloaded during this benchmark. Actual methods, routing, dependency versions, UTC run time, full responses, and input data are retained in JSON. The script temporarily changes process settings and restores them afterward; run it as a standalone CLI, not concurrently inside the API server. Current employment duration uses the execution date, so later runs may change experience scores.

## Interpreting the results

- Execution success: valid model responses / ten cases. Exceptions are recorded per pair and do not stop remaining cases.
- Absolute delta: `abs(ai_expected_score - app_model_score)`, in percentage points.
- MAE: arithmetic mean of deltas across successful cases; partial execution is explicitly reported. With zero successful cases it is null, not zero.
- Model Alignment Score: `100 - MAE`; this is a descriptive agreement measure, not statistical precision or accuracy.
- Pair alignment: PASS when delta is at most 10 points.
- Final alignment: PASS only when all ten cases execute and every delta is at most 10 points.
- Default CLI exit status verifies execution and artifact generation. Add `--require-alignment` for a CI gate that also fails on alignment discrepancies.

The reference run achieved **10/10 execution success**, **MAE 8.52 points**, **alignment score 91.48%**, and **5/10 pairs within tolerance**. Final alignment is **FAIL**. This is an honest benchmark result, not a pipeline error. No matcher weights were changed to improve these scores. The PDF includes comparison tables, category judgments, all 12 application sub-scores, and discrepancy suggestions.

Baseline overall and category scores are separate holistic judgments, not aggregates calculated using the application formula. High/medium/low/edge bands describe intended baseline scenarios; application outputs may fall outside those bands. Compare proposed tuning on separately reviewed, held-out examples to avoid overfitting this small synthetic set.

The PDF generator escapes text before rendering, repeats table headers and numbers pages. Tests validate PDF text, per-pair execution, ranges, arithmetic, frozen labels, failure continuation, and restored settings. Intentional alignment failures do not make execution tests fail.

Validation: 15 benchmark tests passed; the full suite passed 229 Python tests and 12 frontend tests. The generated 14-page PDF was rendered and visually reviewed.
