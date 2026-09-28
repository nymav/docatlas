# Evaluation protocol

`fastapi-development.jsonl` contains 30 AI-authored development cases: 24 answerable
questions linked to literal evidence quotes and 6 out-of-corpus questions. Source
quotes were checked against the pinned source snapshot. **These are not independently
human-reviewed labels, an untouched test set, or evidence of general production accuracy.**

Run the corpus fetcher, ingest the documents, then run `docatlas eval`. The scorer
validates that every gold quote exists before measuring retrieval. Recall measures
the fraction of labeled evidence items found in the top k passages; MRR is the first
relevant rank reciprocal; nDCG uses binary gain for newly covered evidence. Repeated
overlapping passages cannot earn repeated gain for the same evidence item.

Unanswerable cases are excluded from recall/MRR/nDCG. Their abstention rate and the
false-abstention rate on answerable cases are shown separately. The abstention rule
is a configurable heuristic, not a calibrated confidence probability. Generated
answer correctness is not measured by this retrieval benchmark.

Before making a resume accuracy claim: have a human review these labels, add hard
paraphrases and ambiguous questions, create a separate held-out test set, and avoid
tuning on that set. Include alternative valid evidence when more than one passage
answers a question. The current labels can undercount alternate valid passages.

Baseline comparisons require matching dataset, corpus fingerprint, k and abstention
threshold. A regression threshold is not a significance test. CI tests deliberately
corrupt a metric to prove the gate fails; normal CI is offline and uses deterministic
fixtures. The optional workflow downloads the real corpus for a development benchmark.

The corpus comes from the MIT-licensed FastAPI project. Only the pinned manifest and
short evidence labels are committed; downloaded documents and model weights are ignored.
