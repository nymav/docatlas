import numpy as np
import pytest

from docatlas.store import Store


class TestEncoder:
    """Deterministic test double; never used as a real semantic benchmark."""

    name = "test-encoder"

    def documents(self, texts):
        return np.stack([self.query(text) for text in texts])

    def query(self, text):
        text = text.lower()
        vector = np.array(
            [
                float("database" in text or "sql" in text),
                float("auth" in text or "token" in text),
                0.1,
            ],
            dtype=np.float32,
        )
        return vector / np.linalg.norm(vector)


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path, TestEncoder())
    value.ingest(
        "database.md",
        b"# Database\nConnect to the SQL database using the database URL environment variable.",
    )
    value.ingest(
        "auth.md",
        b"# Authentication\nAuthentication requires a Bearer token in the authorization header.",
    )
    return value
