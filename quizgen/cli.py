"""Command-line interface: quizgen generate <file> [options]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .exporters import EXPORTERS
from .generator import generate_quiz
from .llm import LLMError, get_client
from .models import BLOOM_LEVELS, ValidationError


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="quizgen",
        description="Draft multiple-choice quiz questions from training content using AI.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="Generate a quiz from a text or markdown file.")
    g.add_argument("source", type=Path, help="Training content file (.txt or .md)")
    g.add_argument("-n", "--num", type=int, default=5, help="Number of questions (1-25, default 5)")
    g.add_argument("-t", "--title", default=None, help="Quiz title (default: from file name)")
    g.add_argument("-l", "--level", choices=BLOOM_LEVELS, help="Target Bloom's level (default: mixed)")
    g.add_argument(
        "-o", "--objective", action="append", dest="objectives", metavar="TEXT",
        help="A learning objective to align to (repeat for more)",
    )
    g.add_argument("-a", "--audience", help='Who the training is for, e.g. "new call center hires"')
    g.add_argument(
        "-f", "--format", action="append", dest="formats", choices=sorted(EXPORTERS),
        help="Output format(s). Repeat for more. Default: md and html",
    )
    g.add_argument("--out", type=Path, default=Path("quiz"), help="Output path without extension (default: quiz)")
    g.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic")
    g.add_argument("--model", help="Model name (overrides the provider default)")
    g.add_argument(
        "--demo", action="store_true",
        help="Run offline with a built-in sample response (no API key needed)",
    )
    return p


def main(argv: list[str] | None = None, client=None) -> int:
    args = build_parser().parse_args(argv)

    if not args.source.exists():
        print(f"Error: can't find {args.source}", file=sys.stderr)
        return 2
    content = args.source.read_text(encoding="utf-8")
    title = args.title or args.source.stem.replace("-", " ").replace("_", " ").title() + " Quiz"

    try:
        if client is None and args.demo:
            from .demo import DemoClient

            client = DemoClient()
        llm = client or get_client(args.provider, args.model)
        quiz, problems = generate_quiz(
            llm, content, num_questions=args.num, title=title, bloom_level=args.level,
            objectives=args.objectives, audience=args.audience,
        )
    except (LLMError, ValidationError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    formats = args.formats or ["md", "html"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    written = []
    for fmt in formats:
        path = args.out.with_suffix("." + fmt)
        path.write_text(EXPORTERS[fmt](quiz), encoding="utf-8")
        written.append(path)

    flagged = sum(1 for q in quiz.questions if q.warnings)
    print(f"Generated {len(quiz.questions)} question(s).")
    for p in problems:
        print(f"  - {p}")
    if flagged:
        print(f"{flagged} question(s) flagged for review. See the notes in the Markdown or CSV output.")
    for path in written:
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
