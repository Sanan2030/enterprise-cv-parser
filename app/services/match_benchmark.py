"""Reproducible offline benchmark runner; baseline labels never use model outputs."""

import argparse
import hashlib
import json
import platform
import traceback
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from app.core.config import settings
from app.schemas.job_match import JobMatchResponse
from app.services.job_matcher import JobMatcherService

GROUPS = {
    "skills": "skill_match_score",
    "context": "semantic_similarity_score",
    "experience": "experience_score",
    "education": "education_score",
}
BANDS = {"high": (80, 100), "medium": (40, 70), "low": (10, 39), "edge": (0, 10)}


def load_dataset(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    data = json.loads(raw)
    pairs = data["pairs"]
    if len(pairs) != 10 or [p["pair_id"] for p in pairs] != list(range(1, 11)):
        raise ValueError("Benchmark requires ten ordered, distinct pairs")
    for pair, band in zip(pairs, ["high"] * 3 + ["medium"] * 3 + ["low"] * 2 + ["edge"] * 2):
        if pair["scenario_band"] != band or not BANDS[band][0] <= pair["ai_expected_score"] <= BANDS[band][1]:
            raise ValueError("Baseline label must match the declared scenario band")
        if set(pair["ai_expected_breakdown"]) != set(GROUPS) or not all(
            isinstance(v, (int, float)) and 0 <= v <= 100 for v in pair["ai_expected_breakdown"].values()
        ):
            raise ValueError("Expected category scores must be percentages")
    return data, hashlib.sha256(raw).hexdigest()


def metrics(results: list[dict]) -> dict:
    successful = [row for row in results if row["execution_status"] == "PASS"]
    mae = round(sum(row["absolute_delta"] for row in successful) / len(successful), 2) if successful else None
    aligned = sum(row["alignment_status"] == "PASS" for row in successful)
    return {
        "total_cases": len(results),
        "executed_successfully": len(successful),
        "execution_success_rate": round(100 * len(successful) / len(results), 2) if results else 0,
        "mae": mae,
        "model_alignment_score": round(100 - mae, 2) if mae is not None else None,
        "aligned_cases": aligned,
        "alignment_pass_rate": round(100 * aligned / len(results), 2) if results else 0,
        "final_status": "PASS" if results and len(successful) == len(results) == aligned else "FAIL",
    }


def insights(row: dict) -> list[str]:
    if row["execution_status"] != "PASS":
        return ["Resolve the recorded execution error before interpreting this pair's alignment."]
    if row["absolute_delta"] <= 10:
        return ["Within the predeclared 10-point tolerance; retain as a regression case."]
    gaps = sorted(
        GROUPS,
        key=lambda g: abs(row["app_model_breakdown"][g] - row["ai_expected_breakdown"][g]),
        reverse=True,
    )
    suggestions = {
        "skills": "Review no-requirement credit and the 50/30/20 skill weights; validate mandatory-stack coverage on held-out labels.",
        "context": "Inspect duties/summary evidence and the actual semantic backend; compare a locally cached cross-encoder on held-out paraphrases.",
        "experience": "Check role-specific years, seniority aliases and the recency decay; total tenure can overstate transferable experience.",
        "education": "Review no-requirement credit, degree/major groups and credential vocabulary against the JD's explicit requirements.",
    }
    direction = "higher" if row["app_model_score"] > row["ai_expected_score"] else "lower"
    return [
        f"Application score is {row['absolute_delta']:.2f} points {direction} than the independent target.",
        *[suggestions[group] for group in gaps[:2]],
        "Confirm the subjective baseline with independent human reviewers before changing weights; do not tune on these same ten cases.",
    ]


def run_benchmark(dataset_path: Path, *, backend: str = "auto", rerank: bool = False) -> dict:
    if backend not in {"tfidf", "auto"}:
        raise ValueError("backend must be tfidf or auto")
    dataset, digest = load_dataset(dataset_path)
    original = settings.MATCH_SEMANTIC_BACKEND, settings.MATCH_RERANK_ENABLED, settings.MATCH_MODEL_LOCAL_ONLY
    results = []
    try:
        settings.MATCH_SEMANTIC_BACKEND = backend
        settings.MATCH_RERANK_ENABLED = rerank
        settings.MATCH_MODEL_LOCAL_ONLY = True
        for pair in dataset["pairs"]:
            row = dict(pair)
            try:
                response = JobMatcherService().analyze_compatibility(pair["cv_data"], pair["job_description"])
                JobMatchResponse.model_validate(response)
                delta = round(abs(pair["ai_expected_score"] - response["match_percentage"]), 2)
                row.update(
                    execution_status="PASS",
                    app_model_score=response["match_percentage"],
                    absolute_delta=delta,
                    alignment_status="PASS" if delta <= 10 else "FAIL",
                    app_model_breakdown={g: response["breakdown"][key] for g, key in GROUPS.items()},
                    response=response,
                    traceback=None,
                )
            except Exception:
                row.update(
                    execution_status="FAIL",
                    app_model_score=None,
                    absolute_delta=None,
                    alignment_status="ERROR",
                    app_model_breakdown={},
                    response=None,
                    traceback=traceback.format_exc(),
                )
            row["insights"] = insights(row)
            results.append(row)
    finally:
        settings.MATCH_SEMANTIC_BACKEND, settings.MATCH_RERANK_ENABLED, settings.MATCH_MODEL_LOCAL_ONLY = (
            original
        )
    versions = {}
    for package in ("scikit-learn", "sentence-transformers", "reportlab"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = "not installed"
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_source": dataset["baseline_source"],
        "dataset_sha256": digest,
        "baseline_version": dataset["baseline_version"],
        "configuration": {
            "backend_requested": backend,
            "rerank_enabled": rerank,
            "local_models_only": True,
            "serverless": settings.IS_VERCEL,
            "python": platform.python_version(),
            "packages": versions,
        },
        "alignment_tolerance_points": 10,
        "summary": metrics(results),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("tests/fixtures/job_match_benchmark.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("reports"))
    parser.add_argument("--backend", choices=("tfidf", "auto"), default="auto")
    parser.add_argument("--rerank", action="store_true")
    parser.add_argument(
        "--require-alignment", action="store_true", help="Exit nonzero for any delta above 10 points"
    )
    args = parser.parse_args()
    report = run_benchmark(args.dataset, backend=args.backend, rerank=args.rerank)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "benchmark_match_results.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False)
    )
    for row in report["results"]:
        if row["traceback"]:
            (args.output_dir / f"pair_{row['pair_id']:02d}_error.log").write_text(row["traceback"])
    from app.utils.pdf_report_generator import generate_pdf_report

    generate_pdf_report(report, args.output_dir / "benchmark_match_results.pdf")
    print(json.dumps(report["summary"], indent=2))
    return int(
        report["summary"]["execution_success_rate"] != 100
        or (args.require_alignment and report["summary"]["final_status"] != "PASS")
    )


if __name__ == "__main__":
    raise SystemExit(main())
