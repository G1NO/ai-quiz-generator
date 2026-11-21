"""Item-writing quality checks.

These catch common multiple-choice mistakes that make questions easier to guess
or harder to understand. They don't reject a question. They attach warnings so
a human reviewer knows what to look at.
"""

from __future__ import annotations

import re

from .models import Question

_ALL_NONE = re.compile(r"\b(all|none|both|neither)\s+of\s+the\s+(above|following)\b", re.I)
_NEGATIVE_STEM = re.compile(r"\b(NOT|EXCEPT|LEAST|NEVER)\b")
_ABSOLUTES = re.compile(r"\b(always|never|all|none|every|only|completely)\b", re.I)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def check_question(q: Question) -> list[str]:
    """Return a list of human-readable warnings for one question."""
    warnings: list[str] = []
    texts = [o.text for o in q.options]

    # "All of the above" / "None of the above"
    if any(_ALL_NONE.search(t) for t in texts):
        warnings.append(
            'Uses "all/none of the above". These let learners guess from partial knowledge.'
        )

    # Negative stems are easy to misread
    if _NEGATIVE_STEM.search(q.stem):
        warnings.append(
            "Negative stem (NOT/EXCEPT/LEAST). Learners often misread these; rephrase if you can."
        )

    # Correct answer noticeably longer than the distractors (a classic giveaway)
    lengths = [len(t) for t in texts]
    correct_len = lengths[q.correct_index]
    others = [n for i, n in enumerate(lengths) if i != q.correct_index]
    if others and correct_len > 1.5 * (sum(others) / len(others)) and correct_len - max(others) > 15:
        warnings.append(
            "Correct answer is much longer than the others. Length can give the answer away."
        )

    # Duplicate or near-duplicate options
    normed = [_norm(t) for t in texts]
    if len(set(normed)) < len(normed):
        warnings.append("Two or more options are the same.")

    # Absolute words in distractors only (test-wise learners rule these out)
    distractor_absolutes = [
        o.text for o in q.options if not o.correct and _ABSOLUTES.search(o.text)
    ]
    if len(distractor_absolutes) >= 2 and not _ABSOLUTES.search(q.correct_option.text):
        warnings.append(
            'Several distractors use absolutes ("always", "never") but the answer does not. '
            "Test-wise learners can rule them out."
        )

    # Feedback that just says "correct"/"incorrect" isn't teaching anything
    thin = [o for o in q.options if len(o.feedback.split()) < 4]
    if thin:
        warnings.append(
            f"{len(thin)} option(s) have very short feedback. Explain *why* the choice is right or wrong."
        )

    if not q.objective:
        warnings.append("No learning objective attached.")

    return warnings


def review(questions: list[Question]) -> list[Question]:
    """Attach warnings to each question in place and return the list."""
    seen_stems: set[str] = set()
    for q in questions:
        q.warnings = check_question(q)
        key = _norm(q.stem)
        if key in seen_stems:
            q.warnings.append("Duplicate of an earlier question.")
        seen_stems.add(key)
    return questions
