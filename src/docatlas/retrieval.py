import threading
from typing import Protocol

import numpy as np


class Encoder(Protocol):
    name: str

    def documents(self, texts: list[str]) -> np.ndarray: ...

    def query(self, text: str) -> np.ndarray: ...


class LocalEncoder:
    """Lazy ONNX model; no inference API or GPU required."""

    def __init__(self, model: str, cache_dir):
        self.name = model
        self.cache_dir = str(cache_dir)
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                from fastembed import TextEmbedding

                self._model = TextEmbedding(self.name, cache_dir=self.cache_dir, threads=2)
        return self._model

    def documents(self, texts):
        return normalize(np.array(list(self._load().passage_embed(texts)), dtype=np.float32))

    def query(self, text):
        return normalize(np.array(list(self._load().query_embed(text)), dtype=np.float32))[0]


def normalize(values):
    return values / np.maximum(np.linalg.norm(values, axis=-1, keepdims=True), 1e-12)


def reciprocal_rank_fusion(rankings: list[list[str]], constant: int = 60):
    scores = {}
    for ranking in rankings:
        for position, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (constant + position)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
