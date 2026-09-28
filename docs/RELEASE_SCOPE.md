# Release acceptance criteria

DocAtlas is a single-workspace documentation assistant for a developer or small team.
It must support real Markdown, text, HTML and text-based PDF documents; persistent,
idempotent ingestion; atomic index replacement; deletion; BM25 and optional local
neural retrieval; rank fusion; evidence inspection; and grounded generation through
an OpenAI-compatible provider. Without a model it returns labeled source excerpts,
never simulated AI answers.

The web application must offer search/answers, library management, source inspection,
and retrieval comparison. The API must validate inputs, bound uploads, protect
configured workspaces with an API key, avoid arbitrary URL fetching, and expose health
and operational counters. Tests must cover index lifecycle, filtering, citations,
abstention, provider failures, API authorization, and regression detection.

Evaluation must preserve per-question results, distinguish answerable/unanswerable
cases, and compare BM25/dense/hybrid when neural embeddings are installed. Fixture
tests are not a human-reviewed benchmark. No fabricated quality or production claims.

Deliverables include installation instructions, Docker packaging, CI, an architecture
description, threat model, and operational limitations. Public cloud deployment,
multi-tenant identity, OCR, fine-tuning and multi-agent workflows are outside this
release. No user documents or credentials belong in Git.

## Commit milestones

1. Package and release contract.
2. Persistent corpus, extraction and hybrid retrieval.
3. Grounded answering, protected API and operational controls.
4. Complete browser interface.
5. Evaluation runner and substantive automated tests.
6. Deployment, CI, measured results and operating documentation.

Commits record actual implementation dates. Future changes should remain functional,
reviewable increments rather than empty commits for contribution activity.
