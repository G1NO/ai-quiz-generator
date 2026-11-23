"""Export the quiz to formats people actually use.

- GIFT: imports straight into Moodle (and other LMSs that read it)
- CSV: for spreadsheets or bulk upload tools
- Markdown: for review with SMEs
- JSON: the full bundle (map, quiz, evaluation) for reloading or other tools
"""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Optional

from .schemas import ConceptMap, Quiz, QuizEvaluation

_GIFT_SPECIAL = re.compile(r"([~=#{}:\\])")


def _gift_escape(text: str) -> str:
    return _GIFT_SPECIAL.sub(r"\\\1", text.replace("\n", " ").strip())


def to_gift(quiz: Quiz) -> str:
    blocks = [f"// {quiz.topic}", "// Generated with ai-quiz-generator", ""]
    for q in quiz.questions:
        lines = [f"::{q.id}::{_gift_escape(q.stem)} {{"]
        for o in q.options:
            mark = "=" if o.id == q.correct_option_id else "~"
            lines.append(f"\t{mark}{_gift_escape(o.text)}#{_gift_escape(o.feedback)}")
        lines.append(f"\t####{_gift_escape(q.explanation)}")
        lines.append("}")
        blocks.append("\n".join(lines))
        blocks.append("")
    return "\n".join(blocks)


def to_csv(quiz: Quiz, cmap: Optional[ConceptMap] = None) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["question_id", "concept", "bloom_level", "stem",
                "option_a", "option_b", "option_c", "option_d",
                "correct", "explanation"])
    for q in quiz.questions:
        concept = q.concept_id
        if cmap and cmap.concept(q.concept_id):
            concept = cmap.concept(q.concept_id).name
        opts = {o.id: o.text for o in q.options}
        w.writerow([q.id, concept, q.bloom_level, q.stem,
                    opts.get("a", ""), opts.get("b", ""), opts.get("c", ""), opts.get("d", ""),
                    q.correct_option_id, q.explanation])
    return buf.getvalue()


def to_markdown(quiz: Quiz, cmap: Optional[ConceptMap] = None,
                evaluation: Optional[QuizEvaluation] = None) -> str:
    evals = {e.question_id: e for e in evaluation.evaluations} if evaluation else {}
    misc = {}
    if cmap:
        misc = {m.id: m.description for c in cmap.concepts for m in c.misconceptions}

    out = [f"# {quiz.topic}", ""]
    for n, q in enumerate(quiz.questions, 1):
        concept = cmap.concept(q.concept_id).name if cmap and cmap.concept(q.concept_id) else q.concept_id
        out.append(f"## {n}. {q.stem}")
        out.append(f"*Concept: {concept} · Bloom: {q.bloom_level}*")
        out.append("")
        for o in q.options:
            key = " ✅" if o.id == q.correct_option_id else ""
            target = f" — targets: {misc.get(o.misconception_id, o.misconception_id)}" if o.misconception_id else ""
            out.append(f"- **{o.id})** {o.text}{key}{target}")
        out.append("")
        out.append(f"**Explanation:** {q.explanation}")
        if q.id in evals:
            e = evals[q.id]
            out.append(f"**Reviewer score:** {e.average}/4")
            for issue in e.issues:
                out.append(f"- ⚠️ {issue}")
        out.append("")
    return "\n".join(out)


def to_bundle(source: str, audience: str, cmap: ConceptMap, quiz: Quiz,
              evaluation: Optional[QuizEvaluation] = None) -> str:
    return json.dumps({
        "source": source,
        "audience": audience,
        "concept_map": cmap.model_dump(),
        "quiz": quiz.model_dump(),
        "evaluation": evaluation.model_dump() if evaluation else None,
    }, indent=2, ensure_ascii=False)
