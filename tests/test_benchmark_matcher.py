"""Run: python -m tests.test_benchmark_matcher; test: pytest tests/test_benchmark_matcher.py."""

from pathlib import Path

import fitz
import pytest

from app.core.config import settings
from app.services.match_benchmark import load_dataset, main, metrics, run_benchmark
from app.utils.pdf_report_generator import generate_pdf_report

DATASET = Path(__file__).parent / "fixtures" / "job_match_benchmark.json"


@pytest.fixture(scope="module")
def benchmark():
    return run_benchmark(DATASET)


@pytest.mark.parametrize("index", range(10))
def test_each_pair_executes_with_granular_scores(benchmark, index):
    row = benchmark["results"][index]
    assert row["execution_status"] == "PASS", row["traceback"]
    assert 0 <= row["app_model_score"] <= 100
    assert row["absolute_delta"] == round(abs(row["app_model_score"] - row["ai_expected_score"]), 2)
    assert row["alignment_status"] == ("PASS" if row["absolute_delta"] <= 10 else "FAIL")
    assert all(
        len(row["response"]["breakdown"][group]) == 3
        for group in ("skills", "context", "experience", "education")
    )


def test_baseline_is_frozen():
    dataset, digest = load_dataset(DATASET)
    assert digest == "d1e51b9bee6b15565c63c58802132bceb2a54d9a6d3f936475e10119571b0d14"
    assert len({r["candidate_role"] for r in dataset["pairs"]}) == 10


def test_mae_and_final_status(benchmark):
    summary = benchmark["summary"]
    expected = round(sum(r["absolute_delta"] for r in benchmark["results"]) / 10, 2)
    assert summary["mae"] == expected
    assert summary["model_alignment_score"] == round(100 - expected, 2)
    assert summary["execution_success_rate"] == 100
    assert summary["final_status"] == (
        "PASS" if all(r["absolute_delta"] <= 10 for r in benchmark["results"]) else "FAIL"
    )


def test_pdf_contains_comparison_and_evidence(benchmark, tmp_path):
    path = generate_pdf_report(benchmark, tmp_path / "benchmark.pdf")
    with fitz.open(path) as document:
        text = "\n".join(page.get_text() for page in document)
        assert len(document) >= 3
        for phrase in (
            "CV-to-Job Matching Benchmark",
            "Granular category comparison",
            "Pair 10",
            "certifications match",
        ):
            assert phrase in text
        for row in benchmark["results"]:
            assert f"{row['app_model_score']:.2f}%" in text


def test_empty_metrics_never_claim_success():
    result = metrics([])
    assert result["mae"] is None and result["final_status"] == "FAIL"


def test_failure_recorded_without_stopping_batch(monkeypatch):
    from app.services.match_benchmark import JobMatcherService

    original = JobMatcherService.analyze_compatibility
    original_settings = (settings.MATCH_SEMANTIC_BACKEND, settings.MATCH_RERANK_ENABLED)

    def fail_one(self, cv, jd):
        if "Restaurant cook" in cv["summary"]:
            raise RuntimeError("Synthetic execution failure")
        return original(self, cv, jd)

    monkeypatch.setattr(JobMatcherService, "analyze_compatibility", fail_one)
    report = run_benchmark(DATASET)
    assert report["summary"]["executed_successfully"] == 9
    assert report["summary"]["final_status"] == "FAIL"
    assert "Synthetic execution failure" in report["results"][-1]["traceback"]
    assert (settings.MATCH_SEMANTIC_BACKEND, settings.MATCH_RERANK_ENABLED) == original_settings


if __name__ == "__main__":
    raise SystemExit(main())
