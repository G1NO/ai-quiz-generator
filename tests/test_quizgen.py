import copy
import csv
import io
import json

import pytest

from quizgen.cli import main
from quizgen.demo import SAMPLE_RESPONSE, DemoClient
from quizgen.exporters import to_csv, to_gift, to_html, to_json, to_markdown
from quizgen.generator import build_user_prompt, extract_json, generate_quiz, parse_questions
from quizgen.models import Question, ValidationError
from quizgen.quality import check_question

CONTENT = "AI assistants are good at drafting. Always check facts before using AI output."


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def complete(self, system, user):
        self.calls.append((system, user))
        return self.payload if isinstance(self.payload, str) else json.dumps(self.payload)


def good_q(**overrides):
    q = copy.deepcopy(SAMPLE_RESPONSE["questions"][0])
    q.update(overrides)
    return q


# ---------- models ----------

def test_valid_question_parses():
    q = Question.from_dict(good_q())
    assert q.correct_index == 0
    assert q.bloom_level == "understand"


def test_rejects_two_correct_answers():
    d = good_q()
    d["options"][1]["correct"] = True
    with pytest.raises(ValidationError, match="exactly 1 correct"):
        Question.from_dict(d)


def test_rejects_missing_feedback():
    d = good_q()
    d["options"][2]["feedback"] = ""
    with pytest.raises(ValidationError, match="feedback"):
        Question.from_dict(d)


def test_rejects_unknown_bloom_level():
    with pytest.raises(ValidationError, match="Bloom"):
        Question.from_dict(good_q(bloom_level="memorize"))


def test_rejects_too_few_options():
    d = good_q()
    d["options"] = d["options"][:2]
    with pytest.raises(ValidationError, match="3-5 options"):
        Question.from_dict(d)


# ---------- quality checks ----------

def test_clean_question_has_no_warnings():
    assert check_question(Question.from_dict(good_q())) == []


def test_flawed_demo_question_is_flagged():
    flawed = Question.from_dict(SAMPLE_RESPONSE["questions"][4])
    warnings = " ".join(check_question(flawed))
    assert "all/none of the above" in warnings
    assert "Negative stem" in warnings
    assert "much longer" in warnings
    assert "short feedback" in warnings
    assert "No learning objective" in warnings


def test_duplicate_options_flagged():
    d = good_q()
    d["options"][3]["text"] = d["options"][2]["text"]
    assert any("same" in w for w in check_question(Question.from_dict(d)))


# ---------- generator ----------

def test_extract_json_handles_code_fence_and_chatter():
    text = 'Sure!\n```json\n{"questions": []}\n```\nHope that helps.'
    assert extract_json(text) == {"questions": []}


def test_extract_json_without_fence():
    assert extract_json('Here you go: {"a": 1} done') == {"a": 1}


def test_extract_json_errors_cleanly():
    with pytest.raises(ValidationError):
        extract_json("no json here")


def test_bad_questions_are_dropped_not_fatal():
    data = {"questions": [good_q(), {"stem": "broken"}]}
    good, errors = parse_questions(data)
    assert len(good) == 1
    assert len(errors) == 1 and "Question 2" in errors[0]


def test_prompt_includes_options():
    p = build_user_prompt("text", 3, bloom_level="apply", objectives=["Do X"], audience="new hires")
    assert "3 multiple-choice" in p and "apply" in p and "- Do X" in p and "new hires" in p
    assert "<training_content>" in p


def test_generate_quiz_end_to_end_with_demo_client():
    quiz, errors = generate_quiz(DemoClient(), CONTENT, num_questions=5, title="T")
    assert len(quiz.questions) == 5 and errors == []
    flagged = [q for q in quiz.questions if q.warnings]
    assert len(flagged) == 1  # only the deliberately flawed one


def test_generate_quiz_validates_inputs():
    with pytest.raises(ValueError):
        generate_quiz(FakeClient({}), "   ")
    with pytest.raises(ValueError):
        generate_quiz(FakeClient({}), CONTENT, num_questions=0)
    with pytest.raises(ValueError):
        generate_quiz(FakeClient({}), CONTENT, bloom_level="memorize")


def test_generate_quiz_errors_when_nothing_usable():
    with pytest.raises(ValidationError, match="No usable questions"):
        generate_quiz(FakeClient({"questions": [{"stem": "x"}]}), CONTENT)


# ---------- exporters ----------

@pytest.fixture
def quiz():
    q, _ = generate_quiz(DemoClient(), CONTENT)
    return q


def test_markdown_has_answers_and_review_notes(quiz):
    md = to_markdown(quiz)
    assert md.startswith("# Knowledge Check")
    assert md.count("✅") == len(quiz.questions)
    assert "⚠️" in md


def test_markdown_without_answer_key(quiz):
    assert "✅" not in to_markdown(quiz, answer_key=False)


def test_csv_round_trips(quiz):
    rows = list(csv.DictReader(io.StringIO(to_csv(quiz))))
    assert len(rows) == len(quiz.questions)
    assert rows[0]["correct"] == "A"
    assert rows[1]["correct"] == "B"


def test_gift_format(quiz):
    gift = to_gift(quiz)
    assert gift.count("::Q") == len(quiz.questions)
    assert gift.count("\n  =") == len(quiz.questions)  # one correct answer each
    assert "\\:" not in gift.split("::Q1::")[0]


def test_gift_escapes_special_characters():
    d = good_q(stem="What does {x} = 1: mean?")
    q, _ = generate_quiz(FakeClient({"questions": [d]}), CONTENT, num_questions=1)
    assert "\\{x\\} \\= 1\\: mean?" in to_gift(q)


def test_json_export(quiz):
    assert len(json.loads(to_json(quiz))["questions"]) == len(quiz.questions)


def test_html_is_self_contained_and_safe(quiz):
    page = to_html(quiz)
    assert page.startswith("<!DOCTYPE html>")
    assert "<script>" in page and "http" not in page.split("<script>")[0].split("<style>")[0][200:]
    evil = good_q(stem="</script><script>alert(1)</script>")
    q, _ = generate_quiz(FakeClient({"questions": [evil]}), CONTENT, num_questions=1)
    assert "</script><script>alert" not in to_html(q)


# ---------- CLI ----------

def test_cli_demo_writes_files(tmp_path, capsys):
    src = tmp_path / "safety-basics.md"
    src.write_text(CONTENT)
    out = tmp_path / "out" / "quiz"
    code = main(["generate", str(src), "--demo", "--out", str(out), "-f", "md", "-f", "gift", "-f", "csv"])
    assert code == 0
    for ext in ("md", "gift", "csv"):
        assert (out.with_suffix("." + ext)).exists()
    printed = capsys.readouterr().out
    assert "Generated 5 question(s)" in printed and "1 question(s) flagged" in printed
    assert "# Safety Basics Quiz" in out.with_suffix(".md").read_text()


def test_cli_missing_file(tmp_path, capsys):
    assert main(["generate", str(tmp_path / "nope.md"), "--demo"]) == 2
    assert "can't find" in capsys.readouterr().err


def test_cli_reports_model_errors(tmp_path, capsys):
    src = tmp_path / "t.md"
    src.write_text(CONTENT)
    code = main(["generate", str(src), "--out", str(tmp_path / "q")], client=FakeClient("not json"))
    assert code == 1
    assert "Error" in capsys.readouterr().err
