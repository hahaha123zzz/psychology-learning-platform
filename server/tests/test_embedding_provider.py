import json

import httpx
import pytest

from app.core.embedding import HashEmbeddingClient
from app.core.providers.embedding import OpenAICompatibleEmbedding


@pytest.mark.asyncio
async def test_hash_embedding_is_deterministic_and_384_dimensions() -> None:
    provider = HashEmbeddingClient()
    first = await provider.embed(["实验控制"])
    second = await provider.embed(["实验控制"])

    assert first == second
    assert len(first[0]) == 384
    assert provider.version == "hash-v1"


@pytest.mark.asyncio
async def test_openai_compatible_embedding_orders_and_validates_vectors() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://models.example/v1/embeddings"
        assert request.headers["authorization"] == "Bearer secret"
        body = json.loads(request.content)
        assert body == {
            "model": "embedding-model",
            "input": ["第一段", "第二段"],
            "dimensions": 384,
        }
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.2] * 384},
                    {"index": 0, "embedding": [0.1] * 384},
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleEmbedding(
            provider="demo",
            base_url="https://models.example/v1/",
            api_key="secret",
            model="embedding-model",
            client=client,
        )
        vectors = await provider.embed(["第一段", "第二段"])

    assert vectors[0][0] == 0.1
    assert vectors[1][0] == 0.2
    assert provider.version == "demo:embedding-model:384"


@pytest.mark.asyncio
async def test_openai_compatible_embedding_rejects_wrong_dimension() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": [0.1] * 3}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleEmbedding(
            provider="demo",
            base_url="https://models.example/v1",
            api_key="secret",
            model="embedding-model",
            client=client,
        )
        with pytest.raises(ValueError, match="维度无效"):
            await provider.embed(["文本"])
