"""OpenAI-compatible 教材约束生成适配器。"""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class GroundedGeneration:
    answer: str
    evidence_ids: list[str]
    prompt_tokens: int
    completion_tokens: int


class OpenAICompatibleLLM:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 30,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url or not api_key or not model:
            raise ValueError("外部 LLM 需要 base_url、api_key 和 model")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._client = client

    async def generate_grounded_answer(
        self, *, query: str, evidence: list[dict]
    ) -> GroundedGeneration:
        evidence_payload = [
            {
                "evidence_id": item["evidence_id"],
                "title": item["title"],
                "physical_page": item["physical_page"],
                "text": item["text"],
            }
            for item in evidence
        ]
        messages = [
            {
                "role": "system",
                "content": (
                    "你是教材问答助手。只能使用用户提供的教材证据回答，禁止使用模型参数知识补充事实。"
                    "证据不足时 answer 必须明确拒答。输出严格 JSON："
                    '{"answer":"...","evidence_ids":["..."]}。'
                    "evidence_ids 只能选择提供的证据 ID。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"question": query, "evidence": evidence_payload},
                    ensure_ascii=False,
                ),
            },
        ]
        request = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
        }
        if self._client is None:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await self._post(client, request)
        else:
            response = await self._post(self._client, request)
        return response

    async def _post(
        self, client: httpx.AsyncClient, request: dict
    ) -> GroundedGeneration:
        response = await client.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=request,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.removeprefix("```json").removeprefix("```")
            content = content.removesuffix("```").strip()
        parsed = json.loads(content)
        answer = parsed.get("answer")
        evidence_ids = parsed.get("evidence_ids")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("模型响应缺少 answer")
        if not isinstance(evidence_ids, list) or not all(
            isinstance(item, str) for item in evidence_ids
        ):
            raise ValueError("模型响应的 evidence_ids 无效")
        request_context = json.loads(request["messages"][1]["content"])
        allowed_ids = {item["evidence_id"] for item in request_context["evidence"]}
        selected_ids = [item for item in evidence_ids if item in allowed_ids]
        usage = payload.get("usage") or {}
        return GroundedGeneration(
            answer=answer.strip(),
            evidence_ids=selected_ids,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
        )
