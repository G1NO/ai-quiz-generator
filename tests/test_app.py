"""Click-through tests for the Streamlit app, with the API faked out."""

import json
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
pytest.importorskip("pydantic")

from streamlit.testing.v1 import AppTest  # noqa: E402

from quizgen.diagnostic import pipeline  # noqa: E402
from quizgen.diagnostic.schemas import ConceptMap, Quiz, QuizEvaluation  # noqa: E402

ROOT = Path(__file__).parent.parent
DEMO = json.loads((ROOT / "quizgen" / "diagnostic" / "demo_project.json").read_text())


@pytest.fixture
def fake_api(monkeypatch):
    """Live mode returns a map with a different topic than the demo, so we can tell them apart."""
    live_map = dict(DEMO["concept_map"], topic="LIVE TOPIC")
    live_quiz = dict(DEMO["quiz"], topic="LIVE TOPIC")
    monkeypatch.setattr(pipeline, "build_concept_map", lambda *a, **k: ConceptMap.model_validate(live_map))
    monkeypatch.setattr(pipeline, "generate_quiz", lambda *a, **k: Quiz.model_validate(live_quiz))
    monkeypatch.setattr(pipeline, "evaluate_quiz", lambda *a, **k: QuizEvaluation.model_validate(DEMO["evaluation"]))
    import quizgen.diagnostic.llm as llm
    monkeypatch.setattr(llm.LLM, "__init__", lambda self, **k: None)


def app():
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)


def test_demo_mode_loads():
    at = app().run()
    assert not at.exception
    assert any("Using AI Assistants at Work" in m.value for m in at.subheader)


def test_live_steps_refresh_every_tab(fake_api):
    at = app().run()
    at.sidebar.radio[0].set_value("Live (Claude API)").run()
    at.sidebar.text_input[0].set_value("sk-ant-test").run()

    build = next(b for b in at.button if "Build concept map" in b.label)
    build.click().run()
    assert not at.exception
    # The rerun must happen: new map is on screen right away, not the old demo map.
    assert any("LIVE TOPIC" in m.value for m in at.subheader)
    assert any("Concept map ready" in s.value for s in at.success)

    write = next(b for b in at.button if "Write quiz" in b.label)
    write.click().run()
    assert not at.exception
    assert any("Quiz ready" in s.value for s in at.success)
    # Quiz tab (drawn after the button) shows questions, not "write a quiz first".
    assert not any("Write a quiz from the Concept map tab first" in i.value for i in at.info)

    review = next(b for b in at.button if "Run quality review" in b.label)
    review.click().run()
    assert not at.exception
    assert any("Review ready" in s.value for s in at.success)
