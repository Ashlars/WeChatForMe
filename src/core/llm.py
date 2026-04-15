"""Shared LLM client utilities — supports both Anthropic and OpenAI API formats."""
from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

import httpx
from loguru import logger

if TYPE_CHECKING:
    from src.core.context import ContextManager


class LLMClient:
    """Unified LLM client that auto-detects API format (Anthropic vs OpenAI)."""

    def __init__(self, api_key: str, base_url: str | None = None):
        self.api_key = api_key
        self.base_url = (base_url or "").rstrip("/")
        self._http = httpx.Client(timeout=60)
        # Detect format: if base_url contains /v1 or doesn't have anthropic, use OpenAI format
        self._is_openai = bool(self.base_url and "/v1" in self.base_url and "anthropic" not in self.base_url)

    def create_message(self, *, model: str, max_tokens: int = 2000, system: str, messages: list[dict]) -> str:
        """Send a chat completion request. Returns the text response.
        Note: reasoning models (GLM-5.1, o1) need higher max_tokens since reasoning consumes tokens."""
        if self._is_openai:
            return self._call_openai(model=model, max_tokens=max_tokens, system=system, messages=messages)
        else:
            return self._call_anthropic(model=model, max_tokens=max_tokens, system=system, messages=messages)

    def _call_openai(self, *, model: str, max_tokens: int, system: str, messages: list[dict]) -> str:
        url = f"{self.base_url}/chat/completions"
        all_messages = [{"role": "system", "content": system}] + messages
        resp = self._http.post(
            url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={"model": model, "messages": all_messages, "max_tokens": max_tokens, "stream": False},
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"API error: {data['error']}")
        msg = data.get("choices", [{}])[0].get("message", {})
        content = msg.get("content")
        # Some reasoning models (GLM-5.1, o1) put content in reasoning field
        if not content and msg.get("reasoning"):
            # Extract the last meaningful line from reasoning as the actual response
            reasoning = msg["reasoning"]
            # Look for the final answer after reasoning steps
            lines = [l.strip() for l in reasoning.split("\n") if l.strip()]
            # Take the last non-empty line that looks like a response (not a reasoning step)
            for line in reversed(lines):
                cleaned = line.lstrip("* ").strip()
                if cleaned and not cleaned.startswith(("选项", "Option", "分析", "确定", "起草")):
                    content = cleaned
                    break
        return (content or "").strip()

    def _call_anthropic(self, *, model: str, max_tokens: int, system: str, messages: list[dict]) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=self.api_key, base_url=self.base_url or None)
        response = client.messages.create(
            model=model, max_tokens=max_tokens, system=system, messages=messages,
        )
        return response.content[0].text.strip()


_client_cache: dict[str, tuple[str, LLMClient]] = {}


def get_client_and_model(
    context: ContextManager,
    *,
    prefix: str = "chat",
    default_model: str = "claude-sonnet-4-6",
) -> tuple[LLMClient, str]:
    """Get LLM client and model name. Caches client when config unchanged."""
    api_key = (
        context.get_config(f"{prefix}_api_key", "")
        or context.get_config("chat_api_key", "")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
        or os.environ.get("ANTHROPIC_API_KEY", "")
    )
    base_url = (
        context.get_config(f"{prefix}_api_base_url", "")
        or context.get_config("chat_api_base_url", "")
        or os.environ.get("ANTHROPIC_BASE_URL", None)
    )
    model = (
        context.get_config(f"{prefix}_api_model", "")
        or context.get_config("chat_api_model", "")
        or os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "")
        or default_model
    )

    cache_key = f"{api_key}:{base_url}"
    cached = _client_cache.get(prefix)
    if cached and cached[0] == cache_key:
        return cached[1], model

    client = LLMClient(api_key=api_key, base_url=base_url)
    _client_cache[prefix] = (cache_key, client)
    logger.info("LLM client created: prefix={}, base_url={}, openai_mode={}", prefix, base_url, client._is_openai)
    return client, model


def parse_llm_json(raw: str) -> dict:
    """Parse JSON from LLM response, stripping markdown code fences."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
    return json.loads(text.strip())


def build_user_persona(context: ContextManager, *, persona_context: str | None = None) -> str:
    """Build user persona prompt from DB config with optional per-chat overrides."""
    aliases = context.get_config("user_aliases", "")
    fields = [
        ("user_personality", "性格"),
        ("user_speaking_style", "说话风格"),
        ("user_habits", "口头禅和习惯"),
        ("user_topics", "感兴趣的话题"),
        ("user_tone", "语气特征"),
        ("user_extra", "补充"),
    ]
    lines = []
    if aliases:
        lines.append(f"- 别人可能叫你: {aliases}（这些都是在叫你，要回应）")
    for key, label in fields:
        val = context.get_config(key, "")
        if val:
            lines.append(f"- {label}: {val}")

    if not lines and not persona_context:
        return ""

    result = "【你的人设（必须严格模仿）】\n" + "\n".join(lines) + "\n"
    if persona_context:
        result += f"\n【在当前聊天中的特殊要求（优先级高于上面的通用人设）】\n{persona_context}\n"
    return result
