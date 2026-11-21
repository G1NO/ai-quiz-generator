"""Data models for quiz questions, with validation."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

BLOOM_LEVELS = ("remember", "understand", "apply", "analyze", "evaluate", "create")


class ValidationError(ValueError):
    """Raised when a question doesn't meet the required structure."""


@dataclass
class Option:
    text: str
    correct: bool
    feedback: str


@dataclass
class Question:
    stem: str
    options: list[Option]
    objective: str
    bloom_level: str
    warnings: list[str] = field(default_factory=list)

    @property
    def correct_index(self) -> int:
        return next(i for i, o in enumerate(self.options) if o.correct)

    @property
    def correct_option(self) -> Option:
        return self.options[self.correct_index]

    def validate(self) -> None:
        """Check structure. Raises ValidationError on hard problems."""
        if not self.stem.strip():
            raise ValidationError("Question stem is empty.")
        if not 3 <= len(self.options) <= 5:
            raise ValidationError(
                f"Expected 3-5 options, got {len(self.options)}: {self.stem[:60]!r}"
            )
        n_correct = sum(o.correct for o in self.options)
        if n_correct != 1:
            raise ValidationError(
                f"Expected exactly 1 correct option, got {n_correct}: {self.stem[:60]!r}"
            )
        for o in self.options:
            if not o.text.strip():
                raise ValidationError(f"Empty option text: {self.stem[:60]!r}")
            if not o.feedback.strip():
                raise ValidationError(f"Missing feedback for option {o.text[:40]!r}")
        if self.bloom_level not in BLOOM_LEVELS:
            raise ValidationError(
                f"Unknown Bloom's level {self.bloom_level!r}. Use one of: {', '.join(BLOOM_LEVELS)}"
            )

    @classmethod
    def from_dict(cls, d: dict) -> "Question":
        try:
            options = [
                Option(
                    text=str(o["text"]).strip(),
                    correct=bool(o.get("correct", False)),
                    feedback=str(o.get("feedback", "")).strip(),
                )
                for o in d["options"]
            ]
            q = cls(
                stem=str(d["stem"]).strip(),
                options=options,
                objective=str(d.get("objective", "")).strip(),
                bloom_level=str(d.get("bloom_level", "")).strip().lower(),
            )
        except (KeyError, TypeError) as e:
            raise ValidationError(f"Malformed question data: {e}") from e
        q.validate()
        return q

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Quiz:
    title: str
    questions: list[Question]

    def to_dict(self) -> dict:
        return {"title": self.title, "questions": [q.to_dict() for q in self.questions]}
