"""MiniLM sentence embeddings (L2): 384 dimensions, CPU, ~90 MB, downloaded once from Hugging Face."""
from __future__ import annotations

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DIM = 384


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str = MODEL_NAME) -> None:
        self._name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover - environment dependent
                raise RuntimeError(
                    "sentence-transformers is not installed: pip install torch "
                    "--index-url https://download.pytorch.org/whl/cpu && pip install -r requirements.txt"
                ) from exc
            self._model = SentenceTransformer(self._name, device="cpu")
        return self._model

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._load().encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        out = [[float(x) for x in v] for v in vectors]
        if any(len(v) != DIM for v in out):
            raise ValueError(f"{self._name} returned vectors that are not {DIM}-dimensional")
        return out
