"""Optional reranking in a killable, offline, memory-bounded worker process."""

import json
import math
import os
import subprocess
import sys
from functools import lru_cache

from app.core.config import settings
from app.core.logging import logger

# Public model identifier uses L6, not L-6.
MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def model_cached() -> bool:
    try:
        from huggingface_hub import try_to_load_from_cache

        return isinstance(try_to_load_from_cache(MODEL, "config.json"), str)
    except (ImportError, OSError):
        return False


def rerank(cv_text: str, job_text: str) -> tuple[float | None, str]:
    if not settings.MATCH_RERANK_ENABLED or settings.IS_VERCEL:
        return None, "resource_policy"
    if not model_cached():
        return None, "model_not_cached"
    try:
        process = subprocess.run(
            [sys.executable, "-m", "app.services.job_reranker"],
            input=json.dumps({"cv": cv_text, "job": job_text}, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=settings.MATCH_RERANK_TIMEOUT,
            env={**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "OMP_NUM_THREADS": "1"},
        )
        if process.returncode:
            return None, "worker_resource_or_model_error"
        result = float(json.loads(process.stdout)["score"])
        if not math.isfinite(result) or not 0 <= result <= 100:
            return None, "invalid_model_score"
        return result, "cross_encoder"
    except (subprocess.TimeoutExpired, OSError, ValueError, KeyError, TypeError, MemoryError):
        logger.info("job_match_reranker_fallback")
        return None, "timeout_or_resource_error"


def worker() -> None:
    if os.name == "posix":
        import resource

        limit = settings.MATCH_RERANK_MEMORY_MB * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    import torch
    from sentence_transformers import CrossEncoder
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    payload = json.loads(sys.stdin.read(125_000))
    # Retrieve a bounded evidence window; never silently take just page one.
    words = payload["cv"].split()
    passages = [" ".join(words[i : i + 160]) for i in range(0, len(words), 160)] or [""]
    query = payload["job"]
    query_words = query.split()
    queries = [" ".join(query_words[i : i + 120]) for i in range(0, len(query_words), 120)] or [""]
    # Cover beginning, middle, and end of long JDs within the inference budget.
    queries = [queries[i] for i in sorted({0, len(queries) // 2, len(queries) - 1})]
    pairs = []
    for query in queries:
        try:
            matrix = TfidfVectorizer(max_features=10000).fit_transform([query, *passages])
            scores = cosine_similarity(matrix[0], matrix[1:])[0]
            selected = sorted(range(len(passages)), key=lambda i: scores[i], reverse=True)[:2]
        except ValueError:
            selected = [0]
        pairs.extend((query, passages[i]) for i in selected)
    model = CrossEncoder(
        MODEL,
        device="cpu",
        local_files_only=True,
        max_length=512,
        activation_fn=torch.nn.Sigmoid(),
        trust_remote_code=False,
    )
    values = model.predict(pairs, batch_size=2, show_progress_bar=False)
    print(json.dumps({"score": float(sum(values) / len(values)) * 100}))


if __name__ == "__main__":
    worker()
