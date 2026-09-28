import pytest

from docatlas.ingest import chunk_document, extract
from docatlas.store import Store


def test_ingest_is_idempotent_and_replaces_index(store):
    content = b"# Cache\nCache entries expire after thirty seconds."
    first = store.ingest("cache.md", content)
    assert store.ingest("cache.md", content)["status"] == "unchanged"
    assert store.search("expire", "bm25")[0]["document_id"] == first["id"]
    store.ingest("cache.md", b"# Cache\nCaching is disabled.")
    assert not store.search("expire", "bm25")
    assert len(store.list_documents()) == 3


def test_delete_removes_both_indexes_and_persists(store):
    doc = store.search("database", "hybrid")[0]
    assert store.delete(doc["document_id"])
    reopened = Store(store.path.parent, store.encoder)
    assert not reopened.search("database", "bm25")
    assert len(reopened.list_documents()) == 1
    assert not reopened.delete(doc["document_id"])


def test_modes_and_filtered_ranking(store):
    for mode in ("bm25", "dense", "hybrid"):
        assert store.search("database", mode)[0]["filename"] == "database.md"
    auth = next(d for d in store.list_documents() if d["filename"] == "auth.md")
    hits = store.search("database token", "hybrid", document_id=auth["id"])
    assert hits and all(h["filename"] == "auth.md" for h in hits)
    assert store.search("database", "bm25", document_id="missing") == []


def test_stale_model_is_rejected(store):
    store.encoder.name = "changed"
    with pytest.raises(ValueError, match="stale"):
        store.search("database", "hybrid")


def test_failed_embedding_preserves_old_document(store, monkeypatch):
    def fail(_):
        raise RuntimeError("encoder offline")

    monkeypatch.setattr(store.encoder, "documents", fail)
    with pytest.raises(RuntimeError):
        store.ingest("database.md", b"Replacement SQL database text.")
    assert "environment variable" in store.search("database", "bm25")[0]["text"]


def test_fts_syntax_is_data(store):
    assert isinstance(store.search('" OR * NEAR(foo) - " database', "bm25"), list)
    assert store.search("***", "bm25") == []


def test_extraction_and_chunk_provenance():
    pages = extract(
        "page.html", b"<h1>Title</h1><script>evil secret</script><p>Visible content</p>"
    )
    assert "evil" not in pages[0][1]
    chunks = chunk_document("doc", [(3, "# Setup\n" + "word " * 500)])
    assert len(chunks) > 1
    assert all(c.page == 3 and c.section == "Setup" for c in chunks)
    assert len({c.id for c in chunks}) == len(chunks)


@pytest.mark.parametrize(
    "name,data", [("a.exe", b"x"), ("a.txt", b"\xff"), ("a.md", b" "), ("a.pdf", b"garbage")]
)
def test_invalid_inputs(name, data):
    with pytest.raises(ValueError):
        extract(name, data)


def test_source_metadata_update(store):
    data = b"# Metadata\nSource provenance matters for citations."
    first = store.ingest("meta.md", data, "https://example.com/old")
    store.ingest("meta.md", data, "https://example.com/new")
    assert store.document(first["id"])["source"] == "https://example.com/new"
    with pytest.raises(ValueError):
        store.ingest("meta.md", data, "javascript:alert(1)")


def test_lexical_mode_does_not_silently_fake_semantic(tmp_path):
    store = Store(tmp_path)
    with pytest.raises(ValueError, match="disabled"):
        store.search("database", "dense")
