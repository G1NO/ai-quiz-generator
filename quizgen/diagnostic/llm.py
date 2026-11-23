"""Thin wrapper around the Claude API that returns validated pydantic objects.

Uses tool use with tool_choice "auto" plus a clear instruction to call the
submit tool. Newer models (e.g. claude-sonnet-5-5) reject forced tool choice
("tool"/"any"), so we ask instead of force, then verify a tool call was made
and validate its input against the pydantic schema. If the model answers in
plain text or the input doesn't validate, we send it back with a nudge.
"""

from __future__ import annotations

import copy
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

from .prompts import SYSTEM

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "claude-sonnet-5-5"


def _inline_refs(schema: dict) -> dict:
    """Replace $ref pointers with their definitions so the schema is self-contained."""
    schema = copy.deepcopy(schema)
    defs = schema.pop("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                return walk(copy.deepcopy(defs[name]))
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


def tool_schema(model: Type[BaseModel]) -> dict:
    return _inline_refs(model.model_json_schema())


class LLM:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, max_tokens: int = 8000):
        import anthropic  # imported here so demo mode works without the package configured

        self.client = anthropic.Anthropic(api_key=api_key.strip())
        self.model = model
        self.max_tokens = max_tokens

    def structured(self, prompt: str, output: Type[T], retries: int = 2) -> T:
        tool_name = f"submit_{output.__name__.lower()}"
        tools = [{
            "name": tool_name,
            "description": f"Submit the {output.__name__} result.",
            "input_schema": tool_schema(output),
        }]
        instruction = (f"\n\nSubmit your answer by calling the `{tool_name}` tool. "
                       "Don't reply in plain text.")
        messages = [{"role": "user", "content": prompt + instruction}]

        last_error: Exception | None = None
        for _ in range(retries + 1):
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM,
                tools=tools,
                tool_choice={"type": "auto"},
                messages=messages,
            )
            block = next((b for b in resp.content if b.type == "tool_use"), None)
            if block is None:
                last_error = RuntimeError("Model replied in text instead of calling the tool.")
                messages = messages + [
                    {"role": "assistant", "content": resp.content},
                    {"role": "user", "content": f"Please submit that by calling the `{tool_name}` tool now."},
                ]
                continue
            try:
                return output.model_validate(block.input)
            except ValidationError as e:
                last_error = e
                # Feed the validation error back so the model can fix its answer.
                messages = messages + [
                    {"role": "assistant", "content": resp.content},
                    {"role": "user", "content": [{
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "is_error": True,
                        "content": f"That didn't match the schema. Fix these errors and resubmit:\n{e}",
                    }]},
                ]
        raise RuntimeError(f"Couldn't get valid {output.__name__} from the model: {last_error}")
