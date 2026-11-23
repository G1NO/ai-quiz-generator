"""Data models for the concept map, the quiz, and the evaluation.

Everything the LLM returns gets validated against these, so a malformed
response fails loudly instead of quietly producing a broken quiz.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

BloomLevel = Literal["remember", "understand", "apply", "analyze", "evaluate", "create"]


# ---------- Concept map ----------

class Misconception(BaseModel):
    id: str = Field(description="Short id, e.g. 'm1'")
    description: str = Field(description="The wrong belief a learner might hold")
    why_it_happens: str = Field(description="Why learners tend to fall into it")


class Concept(BaseModel):
    id: str = Field(description="Short id, e.g. 'c1'")
    name: str
    description: str
    prerequisites: list[str] = Field(
        default_factory=list,
        description="Ids of concepts a learner must understand first",
    )
    misconceptions: list[Misconception] = Field(default_factory=list)


class ConceptMap(BaseModel):
    topic: str
    learning_objectives: list[str]
    concepts: list[Concept]

    def concept(self, concept_id: str) -> Optional[Concept]:
        return next((c for c in self.concepts if c.id == concept_id), None)

    def misconception_ids(self) -> set[str]:
        return {m.id for c in self.concepts for m in c.misconceptions}


# ---------- Quiz ----------

class Option(BaseModel):
    id: str = Field(description="'a', 'b', 'c', or 'd'")
    text: str
    misconception_id: Optional[str] = Field(
        default=None,
        description="For a wrong answer: the id of the misconception it targets",
    )
    feedback: str = Field(description="What the learner sees if they pick this option")


class Question(BaseModel):
    id: str = Field(description="Short id, e.g. 'q1'")
    concept_id: str
    bloom_level: BloomLevel
    stem: str
    options: list[Option]
    correct_option_id: str
    explanation: str


class Quiz(BaseModel):
    topic: str
    questions: list[Question]


# ---------- Evaluation ----------

class RubricScores(BaseModel):
    alignment: int = Field(ge=1, le=4, description="Does it test the concept and objective it claims to?")
    accuracy: int = Field(ge=1, le=4, description="Is the keyed answer correct and the rest clearly wrong?")
    distractor_quality: int = Field(ge=1, le=4, description="Are wrong answers plausible and tied to real misconceptions?")
    clarity: int = Field(ge=1, le=4, description="Is the stem clear and free of tricks or giveaways?")
    accessibility: int = Field(ge=1, le=4, description="Plain language, reading level, no reliance on visuals or idioms")
    bias: int = Field(ge=1, le=4, description="4 = no cultural, gender, or background assumptions")


class QuestionEvaluation(BaseModel):
    question_id: str
    scores: RubricScores
    issues: list[str] = Field(default_factory=list)
    suggested_fix: Optional[str] = None

    @property
    def average(self) -> float:
        s = self.scores
        vals = [s.alignment, s.accuracy, s.distractor_quality, s.clarity, s.accessibility, s.bias]
        return round(sum(vals) / len(vals), 2)


class QuizEvaluation(BaseModel):
    evaluations: list[QuestionEvaluation]
    overall_notes: str


# ---------- Rule-based checks ----------

class CheckResult(BaseModel):
    check: str
    question_id: Optional[str]  # None = quiz-level finding
    severity: Literal["error", "warning", "info"]
    message: str
