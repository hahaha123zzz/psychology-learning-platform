"""OpenAI-compatible Embeddings API 适配器。"""

from __future__ import annotations

import httpx


class OpenAICompatibleEmbedding:
    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        api_key: str,
        model: str,
        dimension: int = 384,
        timeout_seconds: float = 30,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not provider or provider == "internal":
            raise ValueError("外部 Embedding 需要非 internal 的 provider")
        if not base_url or not api_key or not model:
            raise ValueError("外部 Embedding 需要 base_url、api_key 和 model")
        if dimension != 384:
            raise ValueError("当前知识索引只支持 384 维 Embedding")
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.dimension = dimension
        self.timeout_seconds = timeout_seconds
        self._client = client
        self.version = f"{provider}:{model}:{dimension}"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        request = {
            "model": self.model,
            "input": texts,
            "dimensions": self.dimension,
        }
        if self._client is None:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                return await self._post(client, request)
        return await self._post(self._client, request)

    async def _post(
        self, client: httpx.AsyncClient, request: dict
    ) -> list[list[float]]:
        response = await client.post(
            f"{self.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=request,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data")
        if not isinstance(data, list) or len(data) != len(request["input"]):
            raise ValueError("Embedding 响应数量与请求不一致")
        ordered = sorted(data, key=lambda item: item.get("index", -1))
        vectors: list[list[float]] = []
        for item in ordered:
            vector = item.get("embedding")
            if not isinstance(vector, list) or len(vector) != self.dimension:
                raise ValueError(
                    f"Embedding 维度无效，期望 {self.dimension}，"
                    f"实际 {len(vector) if isinstance(vector, list) else 'unknown'}"
                )
            vectors.append([float(value) for value in vector])
        return vectors
