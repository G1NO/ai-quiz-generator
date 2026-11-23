"""The three stages: source -> concept map -> quiz -> evaluation."""

from __future__ import annotations

from .llm import LLM
from .prompts import CONCEPT_MAP, EVALUATE, QUIZ
from .schemas import ConceptMap, Quiz, QuizEvaluation


def build_concept_map(llm: LLM, source: str, audience: str, n_concepts: int = 6) -> ConceptMap:
    prompt = CONCEPT_MAP.format(source=source, audience=audience, n_concepts=n_concepts)
    return llm.structured(prompt, ConceptMap)


def generate_quiz(llm: LLM, source: str, cmap: ConceptMap, audience: str, n_questions: int = 6) -> Quiz:
    prompt = QUIZ.format(
        source=source,
        audience=audience,
        n_questions=n_questions,
        concept_map=cmap.model_dump_json(indent=2),
    )
    return llm.structured(prompt, Quiz)


def evaluate_quiz(llm: LLM, source: str, cmap: ConceptMap, quiz: Quiz, audience: str) -> QuizEvaluation:
    prompt = EVALUATE.format(
        source=source,
        audience=audience,
        concept_map=cmap.model_dump_json(indent=2),
        quiz=quiz.model_dump_json(indent=2),
    )
    return llm.structured(prompt, QuizEvaluation)
