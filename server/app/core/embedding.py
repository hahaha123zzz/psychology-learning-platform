"""Embedding 客户端与部署级供应商选择。"""

import hashlib
import re
from typing import Protocol

from app.core.config import get_settings
from app.core.providers.embedding import OpenAICompatibleEmbedding

DIM = 384
VERSION = "hash-v1"

_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z0-9]+")


class EmbeddingClient(Protocol):
    version: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbeddingClient:
    version = VERSION

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * DIM
        tokens = _TOKEN_RE.findall(text.lower())
        feats = list(tokens)
        for a, b in zip(tokens, tokens[1:], strict=False):
            if len(a) == 1 and len(b) == 1:
                feats.append(a + b)
        for feat in feats:
            digest = hashlib.md5(feat.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "little") % DIM
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[bucket] += sign
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


def get_embedding_client() -> EmbeddingClient:
    settings = get_settings()
    if settings.llm_provider == "internal" or not settings.embedding_model:
        return HashEmbeddingClient()
    return OpenAICompatibleEmbedding(
        provider=settings.llm_provider,
        base_url=settings.embedding_base_url or settings.llm_base_url,
        api_key=settings.embedding_api_key or settings.llm_api_key,
        model=settings.embedding_model,
        dimension=settings.embedding_dimension,
        timeout_seconds=settings.embedding_timeout_seconds,
    )
