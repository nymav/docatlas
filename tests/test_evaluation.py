import copy
import json

import pytest

from docatlas.evaluation import evaluate, regressions, score_case


def test_repeated_passages_do_not_inflate_gain():
    case = {"relevant": [{"filename": "a.md", "quote": "a sufficiently long quote"}]}
    hits = [{"filename": "a.md", "text": "a sufficiently long quote"}] * 3
    assert score_case(case, hits) == {"recall": 1, "mrr": 1, "ndcg": 1}


def test_regression_gate_fails_bad_change(store, tmp_path):
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "sql",
                "question": "SQL database URL",
                "relevant": [
                    {
                        "filename": "database.md",
                        "quote": "Connect to the SQL database using the database URL environment variable.",
                    }
                ],
            }
        )
        + "\n"
    )
    baseline = evaluate(store, dataset, ["bm25"])
    assert baseline["modes"]["bm25"]["summary"]["recall"] == 1
    assert regressions(baseline, baseline) == []
    broken = copy.deepcopy(baseline)
    broken["modes"]["bm25"]["summary"]["recall"] = 0
    assert "recall regressed" in regressions(baseline, broken)[0]
    broken["dataset_sha256"] = "changed"
    with pytest.raises(ValueError, match="Incompatible"):
        regressions(baseline, broken)


def test_missing_gold_passage_fails_loudly(store, tmp_path):
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "bad",
                "question": "Hello",
                "relevant": [{"filename": "missing.md", "quote": "This evidence does not exist."}],
            }
        )
        + "\n"
    )
    with pytest.raises(ValueError, match="Missing labeled evidence"):
        evaluate(store, dataset, ["bm25"])
