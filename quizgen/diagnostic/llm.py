"""Thin wrapper around the Claude API that returns validated pydantic objects.

Uses tool use with a forced tool choice, so the model has to answer in the
exact JSON shape of the target schema.
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

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def structured(self, prompt: str, output: Type[T], retries: int = 1) -> T:
        tool_name = f"submit_{output.__name__.lower()}"
        tools = [{
            "name": tool_name,
            "description": f"Submit the {output.__name__} result.",
            "input_schema": tool_schema(output),
        }]
        messages = [{"role": "user", "content": prompt}]

        last_error: Exception | None = None
        for _ in range(retries + 1):
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM,
                tools=tools,
                tool_choice={"type": "tool", "name": tool_name},
                messages=messages,
            )
            block = next((b for b in resp.content if b.type == "tool_use"), None)
            if block is None:
                last_error = RuntimeError("Model did not return structured output.")
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
