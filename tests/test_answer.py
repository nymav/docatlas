import json

import httpx
import pytest

from docatlas.answer import ProviderError, answer, validate_claims
from docatlas.config import Settings


def test_no_provider_returns_labeled_evidence(store):
    result = answer("SQL database", store.search("SQL database", "bm25"), Settings())
    assert result["status"] == "evidence_only"
    assert result["claims"] == []


def test_out_of_scope_abstains(store):
    assert (
        answer("Who won the lunar marathon?", store.search("lunar marathon", "bm25"), Settings())[
            "status"
        ]
        == "insufficient_evidence"
    )


def test_citations_reject_invented_ids_and_quotes(store):
    hits = store.search("database", "bm25")
    for claim in [
        {"text": "Use a URL.", "chunk_id": "fake", "quote": hits[0]["text"]},
        {"text": "Use a URL.", "chunk_id": hits[0]["id"], "quote": "This sentence never appeared."},
    ]:
        with pytest.raises(ProviderError):
            validate_claims({"claims": [claim]}, hits)


def test_provider_contract_and_failure_fallback(store):
    hits = store.search("database", "bm25")
    settings = Settings(llm_url="https://provider.test/v1", llm_model="test")

    def handler(request):
        body = json.loads(request.content)
        assert body["messages"][0]["role"] == "system"
        claim = {
            "text": "Set the database URL environment variable.",
            "chunk_id": hits[0]["id"],
            "quote": "Connect to the SQL database using the database URL environment variable.",
        }
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps({"claims": [claim]})}}],
                "usage": {"total_tokens": 42},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = answer("database URL", hits, settings, client)
        assert result["status"] == "answered"
        assert result["usage"]["total_tokens"] == 42
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503))) as client:
        assert answer("database URL", hits, settings, client)["status"] == "generation_unavailable"


def test_model_can_abstain_without_being_reported_as_broken(store):
    hits = store.search("database", "bm25")
    settings = Settings(llm_url="https://provider.test/v1", llm_model="test")
    response = {"choices": [{"message": {"content": '{"claims":[]}'}}]}
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response))
    ) as client:
        assert answer("database URL", hits, settings, client)["status"] == "insufficient_evidence"


def test_blank_quote_cannot_pass_verification(store):
    hits = store.search("database", "bm25")
    with pytest.raises(ProviderError):
        validate_claims(
            {"claims": [{"text": "Invented answer", "chunk_id": hits[0]["id"], "quote": " " * 20}]},
            hits,
        )
