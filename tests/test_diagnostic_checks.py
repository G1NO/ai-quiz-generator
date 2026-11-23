import pytest

pytest.importorskip("pydantic")

import json
from pathlib import Path

from quizgen.diagnostic import checks, export, graph
from quizgen.diagnostic.llm import tool_schema
from quizgen.diagnostic.schemas import ConceptMap, Quiz, QuizEvaluation

DEMO = json.loads((Path(__file__).parent.parent / "quizgen" / "diagnostic" / "demo_project.json").read_text())


@pytest.fixture
def cmap():
    return ConceptMap.model_validate(DEMO["concept_map"])


@pytest.fixture
def quiz():
    return Quiz.model_validate(DEMO["quiz"])


def ids(results, check):
    return {r.question_id for r in results if r.check == check}


def test_demo_bundle_validates():
    QuizEvaluation.model_validate(DEMO["evaluation"])


def test_demo_flaws_are_caught(quiz, cmap):
    results = checks.run_all(quiz, cmap)
    assert "q4" in ids(results, "longest_answer_giveaway")
    assert "q6" in ids(results, "hidden_negative")
    assert "q6" in ids(results, "untargeted_distractor")
    assert any(r.check == "coverage_gap" and "c4" in r.message for r in results)
    assert not [r for r in results if r.severity == "error"]


def test_clean_questions_pass(quiz, cmap):
    results = checks.run_all(quiz, cmap)
    flagged = {r.question_id for r in results if r.question_id}
    assert {"q1", "q2", "q3", "q5"}.isdisjoint(flagged)


def test_cycle_detected(cmap):
    cmap.concepts[0].prerequisites = ["c6"]  # c6 already depends on c1
    results = checks.check_concept_map(cmap)
    assert any(r.check == "prerequisite_cycle" for r in results)


def test_missing_prerequisite(cmap):
    cmap.concepts[0].prerequisites = ["c99"]
    assert any(r.check == "missing_prerequisite" for r in checks.check_concept_map(cmap))


def test_bad_key_and_unknown_misconception(quiz, cmap):
    q = quiz.questions[0]
    q.correct_option_id = "z"
    q.options[1].misconception_id = "m999"
    results = checks.check_question_structure(quiz, cmap)
    assert "q1" in ids(results, "missing_key")
    assert "q1" in ids(results, "unknown_misconception")


def test_off_concept_distractor(quiz, cmap):
    quiz.questions[0].options[1].misconception_id = "m6"  # data-privacy misconception on a c1 question
    assert "q1" in ids(checks.check_question_structure(quiz, cmap), "off_concept_distractor")


def test_capitalized_negative_is_ok(quiz):
    quiz.questions[5].stem = "Which task is an AI assistant NOT well suited to handle on its own?"
    assert "q6" not in ids(checks.check_item_writing(quiz), "hidden_negative")


def test_all_of_the_above(quiz):
    quiz.questions[0].options[3].text = "All of the above"
    assert "q1" in ids(checks.check_item_writing(quiz), "all_none_of_the_above")


def test_answer_key_pattern(quiz, cmap):
    for q in quiz.questions:
        q.correct_option_id = "a"
    assert any(r.check == "answer_key_pattern" for r in checks.check_quiz_level(quiz, cmap))


def test_prerequisite_order(quiz, cmap):
    quiz.questions.reverse()
    assert any(r.check == "prerequisite_order" for r in checks.check_quiz_level(quiz, cmap))


def test_gift_export_escapes(quiz):
    quiz.questions[0].stem = "What does {x} = 2: mean?"
    gift = export.to_gift(quiz)
    assert r"\{x\} \= 2\: mean?" in gift
    assert gift.count("::q") == len(quiz.questions)


def test_csv_and_markdown(quiz, cmap):
    csv_text = export.to_csv(quiz, cmap)
    assert csv_text.splitlines()[0].startswith("question_id")
    assert len(csv_text.strip().splitlines()) == len(quiz.questions) + 1
    md = export.to_markdown(quiz, cmap)
    assert "✅" in md


def test_dot_renders(cmap, quiz):
    dot = graph.to_dot(cmap, highlight={q.concept_id for q in quiz.questions})
    assert dot.startswith("digraph") and '"c1" -> "c2"' in dot and "dashed" in dot


def test_tool_schema_has_no_refs():
    for model in (ConceptMap, Quiz, QuizEvaluation):
        assert "$ref" not in json.dumps(tool_schema(model))
