"""Tests the structured-output loop with a fake client (no network)."""

import pytest

pytest.importorskip("pydantic")

import json
from pathlib import Path
from types import SimpleNamespace

from quizgen.diagnostic.llm import LLM
from quizgen.diagnostic.pipeline import build_concept_map
from quizgen.diagnostic.schemas import ConceptMap

DEMO = json.loads((Path(__file__).parent.parent / "quizgen" / "diagnostic" / "demo_project.json").read_text())


class FakeMessages:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        block = SimpleNamespace(type="tool_use", id=f"tu_{len(self.calls)}", input=self.payloads.pop(0))
        return SimpleNamespace(content=[block])


def fake_llm(payloads):
    llm = LLM.__new__(LLM)
    llm.client = SimpleNamespace(messages=FakeMessages(payloads))
    llm.model = "test-model"
    llm.max_tokens = 1000
    return llm


def test_returns_validated_model_and_forces_tool():
    llm = fake_llm([DEMO["concept_map"]])
    cmap = build_concept_map(llm, "some source " * 30, "staff")
    assert isinstance(cmap, ConceptMap)
    call = llm.client.messages.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": "submit_conceptmap"}


def test_retries_with_validation_error():
    llm = fake_llm([{"topic": "x"}, DEMO["concept_map"]])  # first answer is missing fields
    cmap = llm.structured("prompt", ConceptMap)
    assert cmap.topic == DEMO["concept_map"]["topic"]
    second = llm.client.messages.calls[1]["messages"]
    assert second[-1]["content"][0]["is_error"] is True


def test_cli_diagnose_demo(tmp_path, capsys):
    from quizgen.cli import main

    out = tmp_path / "diag"
    code = main(["diagnose", "examples/diagnostic/ai-at-work.txt", "--demo",
                 "-f", "md", "-f", "gift", "-f", "csv", "-f", "json", "--out", str(out)])
    assert code == 0
    for ext in (".md", ".gift", ".csv", ".json"):
        assert out.with_suffix(ext).exists()
    printed = capsys.readouterr().out
    assert "longest" in printed.lower() and "rubric average" in printed.lower()
