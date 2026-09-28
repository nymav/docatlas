from fastapi.testclient import TestClient

from docatlas.api import create_app
from docatlas.config import Settings


def test_full_document_lifecycle(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        assert client.get("/").status_code == 200
        assert client.get("/health").json() == {"status": "ok"}
        uploaded = client.post(
            "/api/documents",
            files={
                "file": ("guide.md", b"# Setup\nInstall the package with pip install docatlas.")
            },
        )
        assert uploaded.status_code == 201
        doc_id = uploaded.json()["id"]
        result = client.post("/api/ask", json={"question": "Install package pip", "mode": "bm25"})
        assert result.json()["status"] == "evidence_only"
        assert result.json()["hits"][0]["document_id"] == doc_id
        assert client.get(f"/api/documents/{doc_id}").json()["passages"]
        assert (
            client.post(
                "/api/feedback", json={"request_id": result.json()["request_id"], "helpful": True}
            ).status_code
            == 201
        )
        assert client.delete(f"/api/documents/{doc_id}").status_code == 200
        assert client.get(f"/api/documents/{doc_id}").status_code == 404
        assert client.post("/api/search", json={"question": "Install package"}).json()["hits"] == []


def test_auth_covers_reads_writes_and_schema(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path, api_key="test-secret"))) as client:
        for path in ["/api/documents", "/api/config", "/api/metrics", "/api/openapi.json"]:
            assert client.get(path).status_code == 401
            assert client.get(path, headers={"X-API-Key": "test-secret"}).status_code == 200
        assert client.post("/api/ask", json={"question": "test"}).status_code == 401
        assert client.get("/health").status_code == 200


def test_limits_and_input_validation(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path, max_upload_mb=1))) as client:
        assert client.post("/api/ask", json={"question": "  "}).status_code == 422
        assert client.post("/api/search", json={"question": "hello", "k": 100}).status_code == 422
        assert client.post("/api/documents", files={"file": ("bad.exe", b"bad")}).status_code == 422
        assert (
            client.post(
                "/api/documents", files={"file": ("big.txt", b"a" * (1024 * 1024 + 1))}
            ).status_code
            == 413
        )
        assert (
            client.post(
                "/api/ask", json={"question": "hello"}, headers={"Origin": "https://evil.test"}
            ).status_code
            == 403
        )


def test_rate_limit(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path, rate_limit=2))) as client:
        assert client.get("/api/config").status_code == 200
        assert client.get("/api/config").status_code == 200
        result = client.get("/api/config")
        assert result.status_code == 429
        assert result.headers["retry-after"] == "60"
