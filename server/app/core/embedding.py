"""Embedding 客户端接口。当前为本地确定性哈希实现（离线可用、可复现），
接入真实Embedding API时替换实现并更新version，触发索引重建。"""

import hashlib
import re

DIM = 384
VERSION = "hash-v1"

_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z0-9]+")


class EmbeddingClient:
    version = VERSION

    def embed(self, texts: list[str]) -> list[list[float]]:
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
    return EmbeddingClient()
