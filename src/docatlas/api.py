import asyncio
import logging
import secrets
import threading
import time
import uuid
from collections import Counter, deque
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .answer import answer
from .config import Settings
from .retrieval import LocalEncoder
from .store import Store

logger = logging.getLogger("docatlas")


class Query(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    mode: Literal["bm25", "dense", "hybrid"] = "bm25"
    k: int = Field(default=6, ge=1, le=15)
    document_id: str | None = Field(default=None, max_length=64)


class Feedback(BaseModel):
    request_id: uuid.UUID
    helpful: bool
    note: str = Field(default="", max_length=2000)


def create_app(settings=None, encoder=None):
    settings = settings or Settings.from_env()
    if settings.embeddings not in {"bm25", "fastembed"}:
        raise ValueError("DOCATLAS_EMBEDDINGS must be bm25 or fastembed.")
    if settings.embeddings == "fastembed" and encoder is None:
        encoder = LocalEncoder(settings.embedding_model, settings.data_dir / "models")
    store = Store(settings.data_dir, encoder)
    app = FastAPI(
        title="DocAtlas", version="1.0.0", docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.store = store
    app.state.settings = settings
    counters = Counter()
    durations = deque(maxlen=1000)
    windows = {}
    state_lock = threading.Lock()
    work_slots = asyncio.Semaphore(4)

    @app.middleware("http")
    async def controls(request: Request, call_next):
        request_id = str(uuid.uuid4())
        start = time.perf_counter()
        if request.url.path.startswith("/api/"):
            if settings.api_key and not secrets.compare_digest(
                request.headers.get("x-api-key", ""), settings.api_key
            ):
                return JSONResponse(
                    {"detail": "A valid workspace API key is required."}, status_code=401
                )
            # Do not trust forwarded headers from arbitrary clients.
            client = request.client.host if request.client else "unknown"
            now = time.monotonic()
            with state_lock:
                for key in list(windows):
                    if not windows[key] or windows[key][-1] <= now - 60:
                        del windows[key]
                window = windows.setdefault(client, deque())
                while window and window[0] <= now - 60:
                    window.popleft()
                if len(window) >= settings.rate_limit:
                    return JSONResponse(
                        {"detail": "Rate limit reached. Try again shortly."},
                        status_code=429,
                        headers={"Retry-After": "60"},
                    )
                window.append(now)
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                # Same-origin web UI; API callers without Origin may use API keys.
                origin = request.headers.get("origin")
                if origin and origin != str(request.base_url).rstrip("/"):
                    return JSONResponse(
                        {"detail": "Cross-origin writes are not accepted."}, status_code=403
                    )
            raw_length = request.headers.get("content-length", "0")
            if (
                request.url.path == "/api/documents"
                and request.method == "POST"
                and "content-length" not in request.headers
            ):
                return JSONResponse({"detail": "Uploads require Content-Length."}, status_code=411)
            try:
                if int(raw_length) > (settings.max_upload_mb + 1) * 1024 * 1024:
                    return JSONResponse({"detail": "Request too large."}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Invalid Content-Length."}, status_code=400)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request_failed id=%s", request_id)
            response = JSONResponse(
                {"detail": "Unexpected server error.", "request_id": request_id}, status_code=500
            )
        elapsed = (time.perf_counter() - start) * 1000
        with state_lock:
            counters[f"http_{response.status_code}"] += 1
            durations.append(elapsed)
        response.headers.update(
            {
                "X-Request-ID": request_id,
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            }
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    def health():
        with store.connect() as db:
            db.execute("SELECT 1")
        return {"status": "ok"}

    @app.get("/api/config")
    def config():
        return {
            "version": "1.0.0",
            "modes": ["bm25", "dense", "hybrid"] if encoder else ["bm25"],
            "default_mode": "hybrid" if encoder else "bm25",
            "generation": bool(settings.llm_url and settings.llm_model),
            "embedding_model": encoder.name if encoder else None,
            "max_upload_mb": settings.max_upload_mb,
        }

    @app.get("/api/documents")
    def documents():
        return {"documents": store.list_documents(), "fingerprint": store.fingerprint()}

    @app.get("/api/documents/{document_id}")
    def document(document_id: str):
        result = store.document(document_id)
        if not result:
            raise HTTPException(404, "Document not found.")
        return result

    @app.post("/api/documents", status_code=201)
    async def upload(file: Annotated[UploadFile, File()], source: Annotated[str, Form()] = ""):
        limit = settings.max_upload_mb * 1024 * 1024
        data = await file.read(limit + 1)
        await file.close()
        if len(data) > limit:
            raise HTTPException(413, "File exceeds the upload limit.")
        if len(source) > 2000:
            raise HTTPException(422, "Source URL is too long.")
        async with work_slots:
            try:
                return await asyncio.to_thread(store.ingest, file.filename or "", data, source)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc

    @app.delete("/api/documents/{document_id}")
    def delete(document_id: str):
        if not store.delete(document_id):
            raise HTTPException(404, "Document not found.")
        return {"status": "deleted"}

    def run_search(query):
        if not query.question.strip():
            raise HTTPException(422, "Question must contain text.")
        try:
            return store.search(query.question, query.mode, query.k, query.document_id)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/search")
    async def search(query: Query, request: Request):
        start = time.perf_counter()
        async with work_slots:
            hits = await asyncio.to_thread(run_search, query)
        return {
            "hits": hits,
            "mode": query.mode,
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            "request_id": request.state.request_id,
        }

    @app.post("/api/ask")
    async def ask(query: Query, request: Request):
        start = time.perf_counter()
        async with work_slots:
            hits = await asyncio.to_thread(run_search, query)
            result = await asyncio.to_thread(answer, query.question, hits, settings)
        with state_lock:
            counters[result["status"]] += 1
        return {
            **result,
            "hits": hits,
            "mode": query.mode,
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            "request_id": request.state.request_id,
        }

    @app.post("/api/feedback", status_code=201)
    def feedback(value: Feedback):
        store.save_feedback(str(value.request_id), value.helpful, value.note)
        return {"status": "saved"}

    @app.get("/api/metrics")
    def metrics():
        with state_lock:
            ordered = sorted(durations)
            return {
                "counts": dict(counters),
                "recent_requests": len(ordered),
                "p95_ms": round(ordered[min(int(len(ordered) * 0.95), len(ordered) - 1)], 2)
                if ordered
                else 0,
            }

    @app.get("/api/openapi.json")
    def schema():
        return app.openapi()

    app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="web")
    return app
