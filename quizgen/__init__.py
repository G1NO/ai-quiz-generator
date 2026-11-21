"""ai-quiz-generator: draft quiz questions from training content with AI, built with item-writing best practices."""

__version__ = "0.1.0"

from .generator import generate_quiz  # noqa: E402,F401
from .models import Option, Question, Quiz  # noqa: E402,F401

__all__ = ["generate_quiz", "Option", "Question", "Quiz", "__version__"]
