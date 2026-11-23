"""Rule-based item checks.

These are the "test cases for recurring failures": cheap, deterministic
checks for the mistakes LLM-written quizzes make over and over. They run
on every quiz, no API call needed, and they back up the AI reviewer
instead of trusting it blindly.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Optional

from .schemas import CheckResult, ConceptMap, Quiz

NEGATIVE_WORDS = re.compile(r"\b(not|except|least|never)\b")
ABOVE_PHRASES = re.compile(r"\b(all|none|both) of the above\b", re.IGNORECASE)


def _r(check: str, qid: Optional[str], severity: str, message: str) -> CheckResult:
    return CheckResult(check=check, question_id=qid, severity=severity, message=message)


# ---------- Concept map ----------

def find_cycle(cmap: ConceptMap) -> Optional[list[str]]:
    graph = {c.id: [p for p in c.prerequisites if cmap.concept(p)] for c in cmap.concepts}
    state: dict[str, int] = {}  # 1 = visiting, 2 = done
    stack: list[str] = []

    def dfs(node: str) -> Optional[list[str]]:
        state[node] = 1
        stack.append(node)
        for nxt in graph.get(node, []):
            if state.get(nxt) == 1:
                return stack[stack.index(nxt):] + [nxt]
            if state.get(nxt) is None:
                found = dfs(nxt)
                if found:
                    return found
        stack.pop()
        state[node] = 2
        return None

    for cid in graph:
        if state.get(cid) is None:
            found = dfs(cid)
            if found:
                return found
    return None


def check_concept_map(cmap: ConceptMap) -> list[CheckResult]:
    out: list[CheckResult] = []
    ids = [c.id for c in cmap.concepts]

    for cid, n in Counter(ids).items():
        if n > 1:
            out.append(_r("duplicate_concept_id", None, "error", f"Concept id {cid} is used {n} times."))

    for c in cmap.concepts:
        for p in c.prerequisites:
            if p == c.id:
                out.append(_r("self_prerequisite", None, "error", f"{c.id} lists itself as a prerequisite."))
            elif not cmap.concept(p):
                out.append(_r("missing_prerequisite", None, "error",
                              f"{c.id} ({c.name}) points to prerequisite {p}, which isn't in the map."))
        if not c.misconceptions:
            out.append(_r("no_misconceptions", None, "warning",
                          f"{c.id} ({c.name}) has no misconceptions, so its distractors can't be diagnostic."))

    m_ids = [m.id for c in cmap.concepts for m in c.misconceptions]
    for mid, n in Counter(m_ids).items():
        if n > 1:
            out.append(_r("duplicate_misconception_id", None, "error", f"Misconception id {mid} is used {n} times."))

    cycle = find_cycle(cmap)
    if cycle:
        out.append(_r("prerequisite_cycle", None, "error", "Prerequisite loop: " + " -> ".join(cycle)))

    return out


# ---------- Quiz ----------

def _allowed_misconceptions(cmap: ConceptMap, concept_id: str) -> set[str]:
    """Misconceptions from the concept itself plus its direct prerequisites."""
    c = cmap.concept(concept_id)
    if not c:
        return set()
    allowed = {m.id for m in c.misconceptions}
    for p in c.prerequisites:
        pc = cmap.concept(p)
        if pc:
            allowed |= {m.id for m in pc.misconceptions}
    return allowed


def check_question_structure(quiz: Quiz, cmap: ConceptMap) -> list[CheckResult]:
    out: list[CheckResult] = []
    all_misconceptions = cmap.misconception_ids()

    for q in quiz.questions:
        opt_ids = [o.id for o in q.options]

        if len(q.options) != 4:
            out.append(_r("option_count", q.id, "error", f"Has {len(q.options)} options; expected 4."))
        if len(set(opt_ids)) != len(opt_ids):
            out.append(_r("duplicate_option_id", q.id, "error", "Two options share the same id."))
        if q.correct_option_id not in opt_ids:
            out.append(_r("missing_key", q.id, "error",
                          f"Answer key '{q.correct_option_id}' doesn't match any option."))
        if not cmap.concept(q.concept_id):
            out.append(_r("unknown_concept", q.id, "error", f"Tests concept {q.concept_id}, which isn't in the map."))

        texts = [o.text.strip().lower() for o in q.options]
        if len(set(texts)) != len(texts):
            out.append(_r("duplicate_option_text", q.id, "error", "Two options have the same text."))

        allowed = _allowed_misconceptions(cmap, q.concept_id)
        for o in q.options:
            if o.id == q.correct_option_id:
                if o.misconception_id:
                    out.append(_r("key_tagged_as_misconception", q.id, "error",
                                  f"The correct option ({o.id}) is tagged with misconception {o.misconception_id}."))
                continue
            if not o.misconception_id:
                out.append(_r("untargeted_distractor", q.id, "warning",
                              f"Option {o.id} isn't tied to a misconception, so a wrong pick tells you nothing."))
            elif o.misconception_id not in all_misconceptions:
                out.append(_r("unknown_misconception", q.id, "error",
                              f"Option {o.id} targets {o.misconception_id}, which isn't in the map."))
            elif allowed and o.misconception_id not in allowed:
                out.append(_r("off_concept_distractor", q.id, "warning",
                              f"Option {o.id} targets {o.misconception_id}, which belongs to a different concept."))

    return out


def check_item_writing(quiz: Quiz) -> list[CheckResult]:
    """Classic item-writing flaws that give answers away or trip learners up."""
    out: list[CheckResult] = []

    for q in quiz.questions:
        for o in q.options:
            if ABOVE_PHRASES.search(o.text):
                out.append(_r("all_none_of_the_above", q.id, "warning",
                              f"Option {o.id} uses an 'of the above' option."))

        lowered = NEGATIVE_WORDS.findall(q.stem)
        if lowered:
            caps = re.findall(r"\b(NOT|EXCEPT|LEAST|NEVER)\b", q.stem)
            if not caps:
                out.append(_r("hidden_negative", q.id, "warning",
                              f"Stem uses '{lowered[0]}' without emphasis; learners skim past it. Rephrase or capitalize."))

        key = next((o for o in q.options if o.id == q.correct_option_id), None)
        others = [o for o in q.options if o.id != q.correct_option_id]
        if key and others:
            avg_other = sum(len(o.text) for o in others) / len(others)
            if avg_other and len(key.text) > 1.5 * avg_other and len(key.text) == max(len(o.text) for o in q.options):
                out.append(_r("longest_answer_giveaway", q.id, "warning",
                              f"Correct answer is {len(key.text)} chars vs. {avg_other:.0f} avg for the others. Test-wise learners pick the longest."))

    return out


def check_quiz_level(quiz: Quiz, cmap: ConceptMap) -> list[CheckResult]:
    out: list[CheckResult] = []
    qs = quiz.questions
    if not qs:
        return [_r("empty_quiz", None, "error", "Quiz has no questions.")]

    # Answer key spread: learners notice when it's always 'b'.
    positions = Counter(q.correct_option_id for q in qs)
    letter, count = positions.most_common(1)[0]
    if len(qs) >= 4 and count / len(qs) > 0.5:
        out.append(_r("answer_key_pattern", None, "warning",
                      f"{count} of {len(qs)} answers are '{letter}'. Shuffle the key."))

    # Coverage
    tested = {q.concept_id for q in qs}
    untested = [c for c in cmap.concepts if c.id not in tested]
    if untested:
        names = ", ".join(f"{c.id} ({c.name})" for c in untested)
        out.append(_r("coverage_gap", None, "info", f"No question covers: {names}."))

    # Cognitive level
    levels = Counter(q.bloom_level for q in qs)
    if levels.get("remember", 0) / len(qs) > 0.5:
        out.append(_r("too_much_recall", None, "warning",
                      "More than half the questions are pure recall. Add apply/analyze items."))

    # Prerequisite ordering: a concept should be tested after its prerequisites.
    first_seen: dict[str, int] = {}
    for i, q in enumerate(qs):
        first_seen.setdefault(q.concept_id, i)
    for q in qs:
        c = cmap.concept(q.concept_id)
        if not c:
            continue
        for p in c.prerequisites:
            if p in first_seen and first_seen[p] > first_seen[q.concept_id]:
                out.append(_r("prerequisite_order", q.id, "info",
                              f"Tests {c.id} before its prerequisite {p}. Consider reordering."))

    return out


def run_all(quiz: Quiz, cmap: ConceptMap) -> list[CheckResult]:
    order = {"error": 0, "warning": 1, "info": 2}
    results = (
        check_concept_map(cmap)
        + check_question_structure(quiz, cmap)
        + check_item_writing(quiz)
        + check_quiz_level(quiz, cmap)
    )
    return sorted(results, key=lambda r: order[r.severity])
