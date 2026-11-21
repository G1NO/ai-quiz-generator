"""Export a quiz to Markdown, CSV, Moodle GIFT, JSON or a self-contained HTML page."""

from __future__ import annotations

import csv
import html
import io
import json
import string

from .models import Quiz

LETTERS = string.ascii_uppercase


def to_markdown(quiz: Quiz, answer_key: bool = True) -> str:
    out = [f"# {quiz.title}", ""]
    for n, q in enumerate(quiz.questions, 1):
        out.append(f"### {n}. {q.stem}")
        out.append(f"*Objective: {q.objective or 'not set'} · Bloom's level: {q.bloom_level}*")
        out.append("")
        for i, o in enumerate(q.options):
            mark = " ✅" if (answer_key and o.correct) else ""
            out.append(f"- **{LETTERS[i]}.** {o.text}{mark}")
        if answer_key:
            out.append("")
            out.append("<details><summary>Feedback</summary>")
            out.append("")
            for i, o in enumerate(q.options):
                out.append(f"- **{LETTERS[i]}:** {o.feedback}")
            out.append("")
            out.append("</details>")
        if q.warnings:
            out.append("")
            out.append("> ⚠️ **Review:** " + " ".join(q.warnings))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def to_csv(quiz: Quiz) -> str:
    """One row per question. Works for spreadsheets and most LMS bulk importers."""
    max_opts = max(len(q.options) for q in quiz.questions)
    header = ["question", "objective", "bloom_level"]
    for i in range(max_opts):
        header += [f"option_{LETTERS[i]}", f"feedback_{LETTERS[i]}"]
    header += ["correct", "review_notes"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for q in quiz.questions:
        row = [q.stem, q.objective, q.bloom_level]
        for i in range(max_opts):
            if i < len(q.options):
                row += [q.options[i].text, q.options[i].feedback]
            else:
                row += ["", ""]
        row += [LETTERS[q.correct_index], " | ".join(q.warnings)]
        w.writerow(row)
    return buf.getvalue()


def _gift_escape(s: str) -> str:
    for ch in "\\~=#{}:":
        s = s.replace(ch, "\\" + ch)
    return s.replace("\n", " ")


def to_gift(quiz: Quiz) -> str:
    """Moodle GIFT format, with per-option feedback."""
    out = [f"// {quiz.title}", ""]
    for n, q in enumerate(quiz.questions, 1):
        out.append(f"// Objective: {q.objective} | Bloom's: {q.bloom_level}")
        out.append(f"::Q{n}:: {_gift_escape(q.stem)} {{")
        for o in q.options:
            prefix = "=" if o.correct else "~"
            out.append(f"  {prefix}{_gift_escape(o.text)} #{_gift_escape(o.feedback)}")
        out.append("}")
        out.append("")
    return "\n".join(out)


def to_json(quiz: Quiz) -> str:
    return json.dumps(quiz.to_dict(), indent=2, ensure_ascii=False)


_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body{{margin:0;background:#f6f3ee;color:#1d1b18;font:17px/1.6 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:720px;margin:0 auto;padding:40px 20px 60px}}
h1{{font-size:30px;margin:0 0 6px}} .sub{{color:#6b645a;margin:0 0 28px}}
.q{{background:#fff;border:1px solid #e2dbcf;border-radius:12px;padding:20px 22px;margin-bottom:18px}}
.q h2{{font-size:18px;margin:0 0 4px}} .meta{{font-size:13px;color:#6b645a;margin-bottom:12px}}
button.opt{{display:block;width:100%;text-align:left;font:inherit;background:#faf8f4;border:1px solid #d9d1c3;border-radius:8px;padding:10px 14px;margin:8px 0;cursor:pointer}}
button.opt:hover:not(:disabled){{border-color:#b4532a}} button.opt:focus-visible{{outline:2px solid #b4532a;outline-offset:2px}}
button.opt:disabled{{color:#1d1b18;cursor:default}}
button.opt.right{{background:#e6f2e7;border-color:#5a9a66}} button.opt.wrong{{background:#f8e3df;border-color:#c0614f}}
.fb{{margin-top:10px;padding:10px 14px;border-radius:8px;background:#f3eee5;display:none}} .fb.show{{display:block}}
#score{{font-weight:600;margin-top:24px}}
</style></head><body><main>
<h1>{title}</h1><p class="sub">{count} questions · choose an answer to see feedback</p>
<div id="quiz"></div><p id="score" aria-live="polite"></p>
</main>
<script>
const Q={data};
const root=document.getElementById('quiz');let answered=0,right=0;
Q.questions.forEach((q,n)=>{{
  const d=document.createElement('section');d.className='q';
  d.innerHTML=`<h2>${{n+1}}. ${{esc(q.stem)}}</h2><div class="meta">${{esc(q.bloom_level)}}</div>`;
  const fb=document.createElement('div');fb.className='fb';fb.setAttribute('aria-live','polite');
  q.options.forEach(o=>{{
    const b=document.createElement('button');b.className='opt';b.textContent=o.text;
    b.onclick=()=>{{
      d.querySelectorAll('button').forEach((x,i)=>{{x.disabled=true;if(q.options[i].correct)x.classList.add('right');}});
      if(!o.correct)b.classList.add('wrong');
      fb.innerHTML='<strong>'+(o.correct?'Correct. ':'Not quite. ')+'</strong>'+esc(o.feedback);fb.classList.add('show');
      answered++;if(o.correct)right++;
      if(answered===Q.questions.length)document.getElementById('score').textContent=`Score: ${{right}} of ${{answered}}`;
    }};
    d.appendChild(b);
  }});
  d.appendChild(fb);root.appendChild(d);
}});
function esc(s){{return String(s).replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]))}}
</script></body></html>
"""


def to_html(quiz: Quiz) -> str:
    """A self-contained, clickable quiz page with feedback (no answer key visible)."""
    data = {
        "questions": [
            {
                "stem": q.stem,
                "bloom_level": q.bloom_level.capitalize(),
                "options": [{"text": o.text, "correct": o.correct, "feedback": o.feedback} for o in q.options],
            }
            for q in quiz.questions
        ]
    }
    safe = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return _HTML.format(title=html.escape(quiz.title), count=len(quiz.questions), data=safe)


EXPORTERS = {
    "md": to_markdown,
    "csv": to_csv,
    "gift": to_gift,
    "json": to_json,
    "html": to_html,
}
