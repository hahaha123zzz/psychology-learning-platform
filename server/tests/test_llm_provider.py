import json

import httpx
import pytest

from app.core.providers.llm import OpenAICompatibleLLM


@pytest.mark.asyncio
async def test_openai_compatible_provider_returns_grounded_json() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://models.example/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer secret"
        body = json.loads(request.content)
        assert body["model"] == "demo-model"
        assert "只能使用" in body["messages"][0]["content"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "answer": "内部效度依赖实验控制。",
                                    "evidence_ids": ["ev-1", "invented"],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 8},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleLLM(
            base_url="https://models.example/v1/",
            api_key="secret",
            model="demo-model",
            client=client,
        )
        result = await provider.generate_grounded_answer(
            query="什么是内部效度？",
            evidence=[
                {
                    "evidence_id": "ev-1",
                    "title": "实验心理学",
                    "physical_page": 12,
                    "text": "实验控制能够提高内部效度。",
                }
            ],
        )

    assert result.answer == "内部效度依赖实验控制。"
    assert result.evidence_ids == ["ev-1"]
    assert result.prompt_tokens == 20
    assert result.completion_tokens == 8


@pytest.mark.asyncio
async def test_openai_compatible_provider_rejects_unstructured_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not-json"}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleLLM(
            base_url="https://models.example/v1",
            api_key="secret",
            model="demo-model",
            client=client,
        )
        with pytest.raises(json.JSONDecodeError):
            await provider.generate_grounded_answer(
                query="问题",
                evidence=[
                    {
                        "evidence_id": "ev-1",
                        "title": "教材",
                        "physical_page": 1,
                        "text": "证据",
                    }
                ],
            )
