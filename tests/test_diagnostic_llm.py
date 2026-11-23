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
        payload = self.payloads.pop(0)
        if payload is None:  # model answered in plain text instead of calling the tool
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="Here's the map...")])
        block = SimpleNamespace(type="tool_use", id=f"tu_{len(self.calls)}", input=payload)
        return SimpleNamespace(content=[block])


def fake_llm(payloads):
    llm = LLM.__new__(LLM)
    llm.client = SimpleNamespace(messages=FakeMessages(payloads))
    llm.model = "test-model"
    llm.max_tokens = 1000
    return llm


def test_returns_validated_model_and_uses_auto_tool_choice():
    llm = fake_llm([DEMO["concept_map"]])
    cmap = build_concept_map(llm, "some source " * 30, "staff")
    assert isinstance(cmap, ConceptMap)
    call = llm.client.messages.calls[0]
    # Forced tool choice is rejected by newer models, so we must send "auto".
    assert call["tool_choice"] == {"type": "auto"}
    assert "submit_conceptmap" in call["messages"][0]["content"]


def test_nudges_when_model_replies_in_text():
    llm = fake_llm([None, DEMO["concept_map"]])
    cmap = llm.structured("prompt", ConceptMap)
    assert cmap.topic == DEMO["concept_map"]["topic"]
    nudge = llm.client.messages.calls[1]["messages"][-1]["content"]
    assert "submit_conceptmap" in nudge


def test_key_whitespace_is_stripped(monkeypatch):
    import anthropic
    seen = {}
    monkeypatch.setattr(anthropic, "Anthropic", lambda api_key: seen.setdefault("key", api_key))
    LLM(api_key="  sk-ant-test\n")
    assert seen["key"] == "sk-ant-test"


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
