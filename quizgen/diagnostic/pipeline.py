"""The three stages: source -> concept map -> quiz -> evaluation."""

from __future__ import annotations

from .llm import LLM
from .prompts import CONCEPT_MAP, EVALUATE, QUIZ
import random

from .schemas import ConceptMap, Quiz, QuizEvaluation


def build_concept_map(llm: LLM, source: str, audience: str, n_concepts: int = 6) -> ConceptMap:
    prompt = CONCEPT_MAP.format(source=source, audience=audience, n_concepts=n_concepts)
    return llm.structured(prompt, ConceptMap)


def shuffle_answers(quiz: Quiz, seed: int | None = None) -> Quiz:
    """Spread correct answers across a-d.

    LLMs tend to put the right answer in the same slot (often "a") every time,
    which test-wise learners pick up on. Options keep their text, feedback and
    misconception tags; only their letters change. Each correct answer lands in
    a balanced, shuffled set of positions.
    """
    rng = random.Random(seed)
    quiz = quiz.model_copy(deep=True)
    n_opts = 4
    # Balanced targets: e.g. 6 questions -> a,b,c,d,a,b then shuffled.
    targets = [i % n_opts for i in range(len(quiz.questions))]
    rng.shuffle(targets)
    letters = "abcdefgh"
    for q, target in zip(quiz.questions, targets):
        key = next((o for o in q.options if o.id == q.correct_option_id), None)
        if key is None or len(q.options) != n_opts:
            continue  # leave malformed questions alone; the checks will flag them
        others = [o for o in q.options if o is not key]
        rng.shuffle(others)
        ordered = others[:target] + [key] + others[target:]
        for i, o in enumerate(ordered):
            o.id = letters[i]
        q.options = ordered
        q.correct_option_id = key.id
    return quiz


def generate_quiz(llm: LLM, source: str, cmap: ConceptMap, audience: str, n_questions: int = 6) -> Quiz:
    prompt = QUIZ.format(
        source=source,
        audience=audience,
        n_questions=n_questions,
        concept_map=cmap.model_dump_json(indent=2),
    )
    return shuffle_answers(llm.structured(prompt, Quiz))


def evaluate_quiz(llm: LLM, source: str, cmap: ConceptMap, quiz: Quiz, audience: str) -> QuizEvaluation:
    prompt = EVALUATE.format(
        source=source,
        audience=audience,
        concept_map=cmap.model_dump_json(indent=2),
        quiz=quiz.model_dump_json(indent=2),
    )
    return llm.structured(prompt, QuizEvaluation)
