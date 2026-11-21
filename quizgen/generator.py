"""Build the prompt, call the model, and turn the response into Question objects."""

from __future__ import annotations

import json
import re

from .llm import LLMClient
from .models import BLOOM_LEVELS, Question, Quiz, ValidationError
from .quality import review

MAX_SOURCE_CHARS = 60_000

SYSTEM_PROMPT = """You are an experienced instructional designer who writes high-quality \
multiple-choice assessment items for workplace training.

Follow these item-writing rules:
- Base every question only on the training content provided. Do not add outside facts.
- Each question tests one clear idea tied to a learning objective.
- Write the stem as a complete question or scenario. Prefer realistic workplace scenarios for apply-level and higher.
- Give exactly 4 options with exactly 1 correct answer.
- Distractors must be plausible: common misconceptions or partial understanding, not jokes.
- Keep options similar in length and grammar so the answer isn't given away.
- Never use "all of the above" or "none of the above".
- Avoid negative stems (NOT, EXCEPT) unless essential.
- Write feedback for EVERY option that explains why it is right or wrong, in 1-2 plain sentences.

Respond with JSON only, no other text, in exactly this shape:
{
  "questions": [
    {
      "objective": "Learners will be able to ...",
      "bloom_level": "remember|understand|apply|analyze|evaluate|create",
      "stem": "...",
      "options": [
        {"text": "...", "correct": true, "feedback": "..."},
        {"text": "...", "correct": false, "feedback": "..."}
      ]
    }
  ]
}"""


def build_user_prompt(
    content: str,
    num_questions: int,
    bloom_level: str | None = None,
    objectives: list[str] | None = None,
    audience: str | None = None,
) -> str:
    parts = [f"Write {num_questions} multiple-choice questions from the training content below."]
    if bloom_level:
        parts.append(f"Target Bloom's level: {bloom_level}.")
    else:
        parts.append("Mix Bloom's levels, favoring understand and apply.")
    if audience:
        parts.append(f"Audience: {audience}.")
    if objectives:
        parts.append("Align each question to one of these learning objectives:")
        parts.extend(f"- {o}" for o in objectives)
    parts.append("\n<training_content>\n" + content.strip() + "\n</training_content>")
    return "\n".join(parts)


def extract_json(text: str) -> dict:
    """Pull the JSON object out of a model response (tolerates code fences or chatter)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValidationError("The model response didn't contain JSON.")
        candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ValidationError(f"Couldn't parse the model's JSON: {e}") from e


def parse_questions(data: dict) -> tuple[list[Question], list[str]]:
    """Return (valid questions, errors for any that were dropped)."""
    raw = data.get("questions")
    if not isinstance(raw, list):
        raise ValidationError('Expected a "questions" list in the response.')
    good, errors = [], []
    for i, item in enumerate(raw, 1):
        try:
            good.append(Question.from_dict(item))
        except ValidationError as e:
            errors.append(f"Question {i} dropped: {e}")
    return good, errors


def generate_quiz(
    client: LLMClient,
    content: str,
    num_questions: int = 5,
    title: str = "Knowledge Check",
    bloom_level: str | None = None,
    objectives: list[str] | None = None,
    audience: str | None = None,
) -> tuple[Quiz, list[str]]:
    """Generate, validate and quality-review a quiz. Returns (quiz, problems)."""
    if not content.strip():
        raise ValueError("The training content is empty.")
    if not 1 <= num_questions <= 25:
        raise ValueError("Number of questions must be between 1 and 25.")
    if bloom_level and bloom_level not in BLOOM_LEVELS:
        raise ValueError(f"Bloom's level must be one of: {', '.join(BLOOM_LEVELS)}")
    if len(content) > MAX_SOURCE_CHARS:
        content = content[:MAX_SOURCE_CHARS]

    response = client.complete(
        SYSTEM_PROMPT,
        build_user_prompt(content, num_questions, bloom_level, objectives, audience),
    )
    questions, errors = parse_questions(extract_json(response))
    if not questions:
        raise ValidationError("No usable questions came back. " + " ".join(errors))
    review(questions)
    return Quiz(title=title, questions=questions), errors
