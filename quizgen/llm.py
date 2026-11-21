"""Thin wrappers around LLM providers.

Each client exposes one method: complete(system, user) -> str.
That keeps the rest of the code provider-agnostic and easy to test with a fake.
"""

from __future__ import annotations

import os
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class LLMError(RuntimeError):
    pass


class AnthropicClient:
    default_model = "claude-sonnet-5-5"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover - depends on environment
            raise LLMError(
                "The anthropic package isn't installed. Run: pip install 'ai-quiz-generator[anthropic]'"
            ) from e
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise LLMError("Set the ANTHROPIC_API_KEY environment variable.")
        self._client = anthropic.Anthropic(api_key=key)
        self.model = model or os.environ.get("QUIZGEN_MODEL") or self.default_model

    def complete(self, system: str, user: str) -> str:  # pragma: no cover - network
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")


class OpenAIClient:
    default_model = "gpt-4.1-mini"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        try:
            import openai
        except ImportError as e:  # pragma: no cover - depends on environment
            raise LLMError(
                "The openai package isn't installed. Run: pip install 'ai-quiz-generator[openai]'"
            ) from e
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise LLMError("Set the OPENAI_API_KEY environment variable.")
        self._client = openai.OpenAI(api_key=key)
        self.model = model or os.environ.get("QUIZGEN_MODEL") or self.default_model

    def complete(self, system: str, user: str) -> str:  # pragma: no cover - network
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or ""


PROVIDERS = {"anthropic": AnthropicClient, "openai": OpenAIClient}


def get_client(provider: str, model: str | None = None) -> LLMClient:
    try:
        cls = PROVIDERS[provider]
    except KeyError:
        raise LLMError(f"Unknown provider {provider!r}. Choose: {', '.join(PROVIDERS)}") from None
    return cls(model=model)
