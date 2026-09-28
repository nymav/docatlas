"""Passage-level metrics with explicit abstention and compatible regression gates."""

import hashlib
import json
import math
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from .answer import normalize_quote, sufficient_evidence


def score_case(case, hits):
    relevant = case.get("relevant", [])
    found = set()
    gains = []
    first = None
    for rank, hit in enumerate(hits, start=1):
        matched = {
            i
            for i, item in enumerate(relevant)
            if hit["filename"] == item["filename"]
            and normalize_quote(item["quote"]) in normalize_quote(hit["text"])
        }
        new = matched - found
        if matched and first is None:
            first = rank
        gains.append(1 if new else 0)
        found |= matched
    if not relevant:
        return {"recall": None, "mrr": None, "ndcg": None}
    dcg = sum(gain / math.log2(i + 2) for i, gain in enumerate(gains))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(len(relevant), len(hits))))
    return {
        "recall": len(found) / len(relevant),
        "mrr": 1 / first if first else 0,
        "ndcg": dcg / ideal if ideal else 0,
    }


def load_cases(path: Path):
    cases = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    ids = set()
    for case in cases:
        if not isinstance(case.get("id"), str) or case["id"] in ids:
            raise ValueError("Evaluation case ids must be unique strings.")
        ids.add(case["id"])
        if not isinstance(case.get("question"), str) or not case["question"].strip():
            raise ValueError("Each case needs a question.")
        if not isinstance(case.get("relevant"), list):
            raise ValueError("Each case needs a relevant array; use [] for unanswerable.")
        for item in case["relevant"]:
            if (
                not isinstance(item, dict)
                or not item.get("filename")
                or len(item.get("quote", "")) < 12
            ):
                raise ValueError(
                    "Relevant evidence needs a filename and a quote of at least 12 characters."
                )
    if not cases:
        raise ValueError("Evaluation dataset is empty.")
    return cases


def evaluate(store, dataset: Path, modes, k=5, minimum_dense=0.55):
    cases = load_cases(dataset)
    # Labels must exist in the corpus; otherwise recall numbers would be misleading.
    docs = {d["filename"]: store.document(d["id"]) for d in store.list_documents()}
    for case in cases:
        for item in case["relevant"]:
            doc = docs.get(item["filename"])
            if not doc or not any(
                normalize_quote(item["quote"]) in normalize_quote(p["text"])
                for p in doc["passages"]
            ):
                raise ValueError(f"Missing labeled evidence for {case['id']}: {item['filename']}")
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "corpus_fingerprint": store.fingerprint(),
        "embedding_model": store.encoder.name if store.encoder else None,
        "k": k,
        "min_dense_score": minimum_dense,
        "case_count": len(cases),
        "modes": {},
        "scope": "Retrieval and abstention only. Does not measure generated-answer accuracy.",
    }
    for mode in modes:
        results = []
        # Warm model once. Timings exclude startup/download cost, explicitly reported.
        store.search(cases[0]["question"], mode, k)
        for case in cases:
            start = time.perf_counter()
            hits = store.search(case["question"], mode, k)
            latency = (time.perf_counter() - start) * 1000
            abstained = not sufficient_evidence(case["question"], hits, minimum_dense)
            results.append(
                {
                    "id": case["id"],
                    "category": case.get("category", "general"),
                    "question": case["question"],
                    **score_case(case, hits),
                    "expected_abstention": not case["relevant"],
                    "abstained": abstained,
                    "latency_ms": round(latency, 3),
                    "retrieved_ids": [h["id"] for h in hits],
                }
            )

        def summary(rows):
            output = {}
            for metric in ("recall", "mrr", "ndcg"):
                values = [r[metric] for r in rows if r[metric] is not None]
                output[metric] = round(statistics.mean(values), 4) if values else None
            negatives = [r for r in rows if r["expected_abstention"]]
            positives = [r for r in rows if not r["expected_abstention"]]
            output["unanswerable_abstention_rate"] = (
                round(statistics.mean(r["abstained"] for r in negatives), 4) if negatives else None
            )
            output["answerable_false_abstention_rate"] = (
                round(statistics.mean(r["abstained"] for r in positives), 4) if positives else None
            )
            latencies = sorted(r["latency_ms"] for r in rows)
            output["warm_p95_ms"] = latencies[math.ceil(len(latencies) * 0.95) - 1]
            output["count"] = len(rows)
            return output

        report["modes"][mode] = {
            "summary": summary(results),
            "categories": {
                category: summary([r for r in results if r["category"] == category])
                for category in sorted({r["category"] for r in results})
            },
            "cases": results,
        }
    return report


def regressions(baseline, current, tolerance=0.01):
    if not 0 <= tolerance <= 1:
        raise ValueError("Tolerance must be between zero and one.")
    for key in ("dataset_sha256", "corpus_fingerprint", "k", "min_dense_score"):
        if baseline[key] != current[key]:
            raise ValueError(f"Incompatible evaluation reports: {key} differs.")
    failures = []
    for mode, old in baseline["modes"].items():
        if mode not in current["modes"]:
            failures.append(f"Missing mode: {mode}")
            continue
        new = current["modes"][mode]["summary"]
        for metric in ("recall", "mrr", "ndcg", "unanswerable_abstention_rate"):
            value = old["summary"].get(metric)
            if value is not None and (
                new.get(metric) is None or value - new[metric] > tolerance + 1e-9
            ):
                failures.append(f"{mode}: {metric} regressed from {value} to {new.get(metric)}")
        value = old["summary"].get("answerable_false_abstention_rate")
        if value is not None and (
            new.get("answerable_false_abstention_rate") is None
            or new["answerable_false_abstention_rate"] - value > tolerance + 1e-9
        ):
            failures.append(f"{mode}: answerable false abstention increased")
    return failures


def markdown_report(report):
    lines = [
        "# Retrieval evaluation",
        "",
        report["scope"],
        "",
        f"Cases: {report['case_count']} · k={report['k']} · corpus `{report['corpus_fingerprint']}`",
        "",
        "| Mode | Recall@k | MRR@k | nDCG@k | Unanswerable abstention | False abstention | Warm p95 ms |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for mode, result in report["modes"].items():
        s = result["summary"]
        lines.append(
            "| "
            + " | ".join(
                str(v)
                for v in [
                    mode,
                    s["recall"],
                    s["mrr"],
                    s["ndcg"],
                    s["unanswerable_abstention_rate"],
                    s["answerable_false_abstention_rate"],
                    s["warm_p95_ms"],
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "Latency is a single sequential local run after warmup, not a production load test.",
            "Thresholds are engineering gates, not statistical significance tests.",
            "",
            "## Cases requiring investigation",
            "",
        ]
    )
    for mode, result in report["modes"].items():
        for row in result["cases"]:
            if (row["recall"] is not None and row["recall"] < 1) or row["abstained"] != row[
                "expected_abstention"
            ]:
                lines.append(
                    f"- **{mode} / {row['id']}**: {row['question']} — recall={row['recall']}, abstained={row['abstained']}"
                )
    return "\n".join(lines) + "\n"
