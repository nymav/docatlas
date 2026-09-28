# Operating DocAtlas

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| DOCATLAS_DATA_DIR | data | SQLite database and embedding cache |
| DOCATLAS_EMBEDDINGS | bm25 | bm25 or fastembed |
| DOCATLAS_EMBEDDING_MODEL | BAAI/bge-small-en-v1.5 | English neural embedding model |
| DOCATLAS_LLM_URL | empty | Trusted OpenAI-compatible base URL |
| DOCATLAS_LLM_MODEL | empty | Model identifier at that endpoint |
| DOCATLAS_LLM_KEY | empty | Server-side provider credential |
| DOCATLAS_API_KEY | empty | Workspace authentication; required for network binding |
| DOCATLAS_MAX_UPLOAD_MB | 10 | Per-file byte limit |
| DOCATLAS_RATE_LIMIT | 60 | Requests per minute per direct client IP |
| DOCATLAS_MIN_DENSE_SCORE | 0.55 | Heuristic semantic evidence threshold |

## API

All `/api/*` routes require `X-API-Key` when a workspace key is configured. The
public `/health` route returns only readiness of the SQLite connection. The UI shell
is public but cannot read protected documents without the key.

- `GET /api/config`: capabilities without secrets.
- `POST /api/documents`: multipart `file` and optional `source` URL. Does not fetch URL.
- `GET /api/documents`: library metadata.
- `GET /api/documents/{id}`: extracted passages.
- `DELETE /api/documents/{id}`: document and both search indexes.
- `POST /api/search`: `{question, mode, k, document_id?}`.
- `POST /api/ask`: same contract, plus generation if configured.
- `POST /api/feedback`: `{request_id, helpful, note?}`; persisted locally.
- `GET /api/metrics`: process-local counters and last-1000-request p95.
- `GET /api/openapi.json`: full API schema.

Generation is synchronous within a bounded four-operation semaphore, with a 45-second
provider timeout and no automatic retries that could duplicate paid calls. Requests
waiting for a slot remain pending; this is not a durable distributed job queue.
The first neural call includes model load/download latency. Warm evaluation excludes it.

## Persistence and backup

Use the SQLite backup API for a consistent live backup, or stop the application before
copying the data directory. Do not copy only the main database while WAL writes are
active. Verify backups by opening a restored database and querying known documents.
Original uploaded binaries are not retained; keep your source files to re-index.
Changing the chunker or model requires re-ingestion; unchanged-content detection
currently tracks content and embedding model, not a configurable chunker version.

Do not run multiple application replicas against the same mounted SQLite database.
For larger deployments, migrate storage, jobs, rate limiting and identity to external
services. Current metrics and rate limits reset on process restart. Behind a reverse
proxy the limiter sees that proxy's IP; enforce per-user limits at the proxy layer.

## Provider troubleshooting

`evidence_only` means no generation provider is configured. `generation_unavailable`
means the provider failed, returned incompatible JSON, or a claim failed quote/source
validation. `insufficient_evidence` means the retrieval heuristic abstained. None is
silently converted into a successful generated answer.

From Docker Desktop, a model server on the host commonly uses
`http://host.docker.internal:11434/v1`. Ensure the host model server accepts that
connection. Linux host networking may require an explicit host-gateway mapping.

## Known quality limitations

The development corpus contains technical terms that favor BM25. More diverse,
human-reviewed data is needed before choosing a retrieval strategy for another domain.
The abstention heuristic can mistake topical similarity for an answer, especially on
personal or time-sensitive questions. Quote verification does not verify entailment.
Text-based PDF extraction preserves page numbers but not layout; scanned PDFs need
external OCR. This release has no automatic reranker, OCR or graph index.
