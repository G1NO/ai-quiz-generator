"""`quizgen diagnose`: the concept-map pipeline from the command line."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DEMO_FILE = Path(__file__).parent / "demo_project.json"
FORMATS = {"md": ".md", "gift": ".gift", "csv": ".csv", "json": ".json"}


def add_parser(sub) -> None:
    d = sub.add_parser(
        "diagnose",
        help="Concept map -> misconception-targeted quiz -> rubric + rule review.",
        description="Needs: pip install 'ai-quiz-generator[diagnostic]'",
    )
    d.add_argument("source", type=Path, help="Training content file (.txt or .md)")
    d.add_argument("-n", "--num", type=int, default=6, help="Number of questions (default 6)")
    d.add_argument("--concepts", type=int, default=6, help="Concepts to extract (default 6)")
    d.add_argument("-a", "--audience", default="Workplace learners", help="Who the training is for")
    d.add_argument("-f", "--format", action="append", dest="formats", choices=sorted(FORMATS),
                   help="Output format(s). Repeat for more. Default: md and json")
    d.add_argument("--out", type=Path, default=Path("diagnostic-quiz"), help="Output path without extension")
    d.add_argument("--model", help="Claude model name")
    d.add_argument("--no-review", action="store_true", help="Skip the AI rubric review (saves one API call)")
    d.add_argument("--demo", action="store_true", help="Use the bundled finished example (no API key)")


def run(args) -> int:
    try:
        from . import checks, export
        from .schemas import ConceptMap, Quiz, QuizEvaluation
    except ImportError:
        print("Error: diagnostic mode needs extra packages. Run: pip install 'ai-quiz-generator[diagnostic]'",
              file=sys.stderr)
        return 1

    if args.demo:
        data = json.loads(DEMO_FILE.read_text(encoding="utf-8"))
        source, audience = data["source"], data["audience"]
        cmap = ConceptMap.model_validate(data["concept_map"])
        quiz = Quiz.model_validate(data["quiz"])
        evaluation = QuizEvaluation.model_validate(data["evaluation"])
        print("Demo mode: using the bundled example project.")
    else:
        if not args.source.exists():
            print(f"Error: can't find {args.source}", file=sys.stderr)
            return 2
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            print("Error: set the ANTHROPIC_API_KEY environment variable (or use --demo).", file=sys.stderr)
            return 1
        from .llm import DEFAULT_MODEL, LLM
        from .pipeline import build_concept_map, evaluate_quiz, generate_quiz

        source, audience = args.source.read_text(encoding="utf-8"), args.audience
        llm = LLM(api_key=key, model=args.model or os.environ.get("QUIZGEN_MODEL") or DEFAULT_MODEL)
        try:
            print("Building concept map...")
            cmap = build_concept_map(llm, source, audience, args.concepts)
            print("Writing quiz...")
            quiz = generate_quiz(llm, source, cmap, audience, args.num)
            evaluation = None
            if not args.no_review:
                print("Reviewing questions...")
                evaluation = evaluate_quiz(llm, source, cmap, quiz, audience)
        except Exception as e:  # surface API/validation problems as plain messages
            print(f"Error: {e}", file=sys.stderr)
            return 1

    print(f"\n{len(cmap.concepts)} concepts, {len(quiz.questions)} questions.")
    results = checks.run_all(quiz, cmap)
    icons = {"error": "✖", "warning": "⚠", "info": "·"}
    if results:
        print("Rule-based checks:")
        for r in results:
            where = f"{r.question_id}: " if r.question_id else ""
            print(f"  {icons[r.severity]} {where}{r.message}")
    else:
        print("Rule-based checks: no issues.")
    if evaluation:
        avg = sum(e.average for e in evaluation.evaluations) / max(len(evaluation.evaluations), 1)
        print(f"AI rubric average: {avg:.2f} / 4")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    writers = {
        "md": lambda: export.to_markdown(quiz, cmap, evaluation),
        "gift": lambda: export.to_gift(quiz),
        "csv": lambda: export.to_csv(quiz, cmap),
        "json": lambda: export.to_bundle(source, audience, cmap, quiz, evaluation),
    }
    for fmt in args.formats or ["md", "json"]:
        path = args.out.with_suffix(FORMATS[fmt])
        path.write_text(writers[fmt](), encoding="utf-8")
        print(f"Wrote {path}")
    return 0
