"""AI Quiz Generator — Streamlit app.

Source text -> concept map (prerequisites + misconceptions)
            -> diagnostic multiple-choice quiz
            -> rubric review by AI + rule-based item checks
            -> export (GIFT for Moodle, CSV, Markdown, JSON)

Run:  streamlit run app.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from quizgen.diagnostic import checks, export, graph
from quizgen.diagnostic.llm import DEFAULT_MODEL, LLM
from quizgen.diagnostic.pipeline import build_concept_map, evaluate_quiz, generate_quiz
from quizgen.diagnostic.schemas import ConceptMap, Quiz, QuizEvaluation

ROOT = Path(__file__).parent
DEMO_FILE = ROOT / "quizgen" / "diagnostic" / "demo_project.json"

st.set_page_config(page_title="AI Quiz Generator", page_icon="🧠", layout="wide")


# ---------- State ----------

def init_state():
    defaults = {"flash": None, "source": "", "audience": "Non-technical office employees",
                "cmap": None, "quiz": None, "evaluation": None, "loaded_demo": False}
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


def load_bundle(data: dict):
    st.session_state.source = data.get("source", "")
    st.session_state.audience = data.get("audience", st.session_state.audience)
    st.session_state.cmap = ConceptMap.model_validate(data["concept_map"]) if data.get("concept_map") else None
    st.session_state.quiz = Quiz.model_validate(data["quiz"]) if data.get("quiz") else None
    st.session_state.evaluation = QuizEvaluation.model_validate(data["evaluation"]) if data.get("evaluation") else None


def reset_downstream(from_stage: str):
    order = ["cmap", "quiz", "evaluation"]
    for key in order[order.index(from_stage):]:
        st.session_state[key] = None


init_state()


# ---------- Sidebar ----------

with st.sidebar:
    st.header("Settings")
    mode = st.radio("Mode", ["Demo (no API key)", "Live (Claude API)"],
                    help="Demo mode loads a finished example so you can click through every step.")
    live = mode.startswith("Live")

    api_key = ""
    model = DEFAULT_MODEL
    if live:
        default_key = os.environ.get("ANTHROPIC_API_KEY", "")
        try:
            default_key = default_key or st.secrets.get("ANTHROPIC_API_KEY", "")
        except Exception:
            pass
        api_key = st.text_input("Anthropic API key", value=default_key, type="password",
                                help="Used only for this session. Not stored.")
        model = st.text_input("Model", value=DEFAULT_MODEL)
        n_concepts = st.slider("Concepts to extract", 3, 10, 6)
        n_questions = st.slider("Questions to write", 3, 12, 6)
    else:
        if not st.session_state.loaded_demo:
            load_bundle(json.loads(DEMO_FILE.read_text()))
            st.session_state.loaded_demo = True
        if st.button("Reload demo"):
            load_bundle(json.loads(DEMO_FILE.read_text()))

    st.divider()
    uploaded = st.file_uploader("Load a saved project (.json)", type="json")
    if uploaded is not None and st.button("Load project"):
        try:
            load_bundle(json.load(uploaded))
            st.success("Loaded.")
        except (ValidationError, KeyError, json.JSONDecodeError) as e:
            st.error(f"That file doesn't look like a saved project: {e}")


def friendly_error(e: Exception) -> str:
    """Turn API errors into something a non-developer can act on."""
    status = getattr(e, "status_code", None)
    if status == 401:
        return ("That API key didn't work. Copy it again from console.anthropic.com "
                "(use the copy button; the key is only shown once) and paste it in the sidebar.")
    if status == 402 or "credit balance" in str(e).lower():
        return "Your Anthropic account is out of credits. Add some under Settings → Billing in the Console."
    if status == 404:
        return "That model name wasn't found. Check the Model field in the sidebar."
    if status == 429:
        return "Hit a rate limit. Wait a minute and try again."
    if status and status >= 500:
        return "Claude's API had a temporary problem. Try again in a moment."
    return f"Something went wrong: {e}"


def finish_step(message: str):
    """Save a success message and rerun, so every tab redraws from the new results.

    Without the rerun, tabs drawn earlier in this run still show the old data.
    """
    st.session_state.flash = message
    st.rerun()


def get_llm() -> LLM | None:
    if not live:
        st.info("Switch to **Live** mode in the sidebar and add an API key to generate from your own content.")
        return None
    if not api_key:
        st.warning("Add your Anthropic API key in the sidebar.")
        return None
    return LLM(api_key=api_key, model=model)


# ---------- Header ----------

st.title("🧠 AI Quiz Generator")
st.caption(
    "Turns source material into a concept map, writes a quiz whose wrong answers each target a "
    "specific misconception, then reviews every question with an AI rubric plus rule-based checks."
)

if st.session_state.flash:
    st.success(st.session_state.flash)
    st.session_state.flash = None

tab_src, tab_map, tab_quiz, tab_qa, tab_export = st.tabs(
    ["1 · Source", "2 · Concept map", "3 · Quiz", "4 · Quality review", "5 · Export"]
)

cmap: ConceptMap | None = st.session_state.cmap
quiz: Quiz | None = st.session_state.quiz
evaluation: QuizEvaluation | None = st.session_state.evaluation


# ---------- 1. Source ----------

with tab_src:
    st.subheader("Source material")
    st.session_state.audience = st.text_input("Who is this for?", value=st.session_state.audience)
    st.session_state.source = st.text_area(
        "Paste the content learners should master (a lesson, SOP, policy, article...)",
        value=st.session_state.source, height=360,
    )
    words = len(st.session_state.source.split())
    st.caption(f"{words} words")

    if st.button("Build concept map →", type="primary", disabled=words < 50):
        llm = get_llm()
        if llm:
            with st.spinner("Mapping concepts, prerequisites, and misconceptions... (usually 20–60 seconds, don't click away)"):
                try:
                    reset_downstream("cmap")
                    st.session_state.cmap = build_concept_map(
                        llm, st.session_state.source, st.session_state.audience, n_concepts)
                    finish_step("Concept map ready. Open the **2 · Concept map** tab.")
                except Exception as e:
                    st.error(friendly_error(e))
    if words < 50:
        st.caption("Paste at least 50 words to get started.")


# ---------- 2. Concept map ----------

with tab_map:
    if not cmap:
        st.info("Build a concept map from the Source tab first.")
    else:
        st.subheader(cmap.topic)
        st.markdown("**Learning objectives**")
        for obj in cmap.learning_objectives:
            st.markdown(f"- {obj}")

        show_m = st.toggle("Show misconceptions", value=False)
        tested = {q.concept_id for q in quiz.questions} if quiz else None
        st.graphviz_chart(graph.to_dot(cmap, show_misconceptions=show_m, highlight=tested),
                          use_container_width=True)
        st.caption("Arrows go from prerequisite → the concept that builds on it. Orange notes are misconceptions."
                   + (" Dashed boxes have no quiz question yet." if tested is not None else ""))

        map_issues = checks.check_concept_map(cmap)
        for r in map_issues:
            (st.error if r.severity == "error" else st.warning)(r.message)

        with st.expander("Concept details"):
            for c in cmap.concepts:
                pre = ", ".join(cmap.concept(p).name for p in c.prerequisites if cmap.concept(p)) or "none"
                st.markdown(f"**{c.id} · {c.name}** — {c.description}  \n*Prerequisites:* {pre}")
                for m in c.misconceptions:
                    st.markdown(f"  - `{m.id}` {m.description} — *{m.why_it_happens}*")

        with st.expander("Edit the map (JSON) before writing questions"):
            st.caption("Review with an SME here: fix misconceptions, add prerequisites, drop concepts. "
                       "Saving clears the quiz so it gets rewritten from the new map.")
            edited = st.text_area("Concept map JSON", value=cmap.model_dump_json(indent=2), height=300)
            if st.button("Save map"):
                try:
                    st.session_state.cmap = ConceptMap.model_validate_json(edited)
                    reset_downstream("quiz")
                    st.rerun()
                except ValidationError as e:
                    st.error(f"Invalid map: {e}")

        if st.button("Write quiz →", type="primary"):
            llm = get_llm()
            if llm:
                with st.spinner("Writing questions with diagnostic distractors... (can take 1–2 minutes, don't click away)"):
                    try:
                        reset_downstream("quiz")
                        st.session_state.quiz = generate_quiz(
                            llm, st.session_state.source, cmap, st.session_state.audience, n_questions)
                        finish_step("Quiz ready. Open the **3 · Quiz** tab.")
                    except Exception as e:
                        st.error(friendly_error(e))


# ---------- 3. Quiz ----------

with tab_quiz:
    if not quiz or not cmap:
        st.info("Write a quiz from the Concept map tab first.")
    else:
        view = st.radio("View", ["Learner preview", "Designer view"], horizontal=True)
        misc = {m.id: m.description for c in cmap.concepts for m in c.misconceptions}

        for n, q in enumerate(quiz.questions, 1):
            concept = cmap.concept(q.concept_id)
            with st.container(border=True):
                st.markdown(f"**{n}. {q.stem}**")
                if view == "Learner preview":
                    labels = {o.id: f"{o.id}) {o.text}" for o in q.options}
                    pick = st.radio("Your answer", list(labels), format_func=labels.get,
                                    key=f"pick_{q.id}", index=None, label_visibility="collapsed")
                    if pick:
                        chosen = next(o for o in q.options if o.id == pick)
                        (st.success if pick == q.correct_option_id else st.error)(chosen.feedback)
                else:
                    st.caption(f"Concept: {concept.name if concept else q.concept_id} · Bloom: {q.bloom_level}")
                    for o in q.options:
                        if o.id == q.correct_option_id:
                            st.markdown(f"✅ **{o.id})** {o.text}")
                        else:
                            target = misc.get(o.misconception_id, "⚠️ no misconception tagged")
                            st.markdown(f"❌ **{o.id})** {o.text}  \n  &nbsp;&nbsp;&nbsp;↳ *targets:* {target}")
                    st.markdown(f"*Explanation:* {q.explanation}")

        if st.button("Run quality review →", type="primary"):
            llm = get_llm()
            if llm:
                with st.spinner("Reviewing every question against the rubric... (can take about a minute, don't click away)"):
                    try:
                        st.session_state.evaluation = evaluate_quiz(
                            llm, st.session_state.source, cmap, quiz, st.session_state.audience)
                        finish_step("Review ready. Open the **4 · Quality review** tab.")
                    except Exception as e:
                        st.error(friendly_error(e))


# ---------- 4. Quality review ----------

with tab_qa:
    if not quiz or not cmap:
        st.info("Generate a quiz first.")
    else:
        rule_results = checks.run_all(quiz, cmap)
        distractors = [o for q in quiz.questions for o in q.options if o.id != q.correct_option_id]
        targeted = sum(1 for o in distractors if o.misconception_id)
        covered = len({q.concept_id for q in quiz.questions})

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Questions", len(quiz.questions))
        c2.metric("Concept coverage", f"{covered}/{len(cmap.concepts)}")
        c3.metric("Diagnostic distractors", f"{targeted}/{len(distractors)}",
                  help="Wrong answers tied to a specific misconception")
        if evaluation:
            avg = sum(e.average for e in evaluation.evaluations) / max(len(evaluation.evaluations), 1)
            c4.metric("AI rubric avg", f"{avg:.2f} / 4")
        else:
            c4.metric("AI rubric avg", "—")

        st.subheader("Rule-based checks")
        st.caption("Deterministic tests for the flaws AI-written items make most often. No API call; these run every time.")
        if not rule_results:
            st.success("No issues found.")
        for r in rule_results:
            where = f"**{r.question_id}** · " if r.question_id else ""
            msg = f"{where}`{r.check}` — {r.message}"
            {"error": st.error, "warning": st.warning, "info": st.info}[r.severity](msg)

        st.subheader("AI rubric review")
        if not evaluation:
            st.info("Run the quality review from the Quiz tab (Live mode).")
        else:
            rows = []
            for e in evaluation.evaluations:
                s = e.scores
                rows.append({"Q": e.question_id, "Alignment": s.alignment, "Accuracy": s.accuracy,
                             "Distractors": s.distractor_quality, "Clarity": s.clarity,
                             "Accessibility": s.accessibility, "Bias": s.bias, "Avg": e.average})
            df = pd.DataFrame(rows).set_index("Q")
            st.dataframe(df.style.background_gradient(cmap="RdYlGn", vmin=1, vmax=4, axis=None)
                         .format(precision=2), use_container_width=True)

            for e in evaluation.evaluations:
                if e.issues or e.suggested_fix:
                    with st.expander(f"{e.question_id} — {e.average}/4"):
                        for i in e.issues:
                            st.markdown(f"- {i}")
                        if e.suggested_fix:
                            st.markdown(f"**Suggested fix:** {e.suggested_fix}")
            st.markdown(f"**Overall:** {evaluation.overall_notes}")

            # Where the two reviewers agree is where you should look first.
            rule_flagged = {r.question_id for r in rule_results if r.question_id and r.severity != "info"}
            ai_flagged = {e.question_id for e in evaluation.evaluations if e.average < 3.5}
            both = sorted(rule_flagged & ai_flagged)
            if both:
                st.warning(f"Flagged by both the rules and the AI reviewer: {', '.join(both)}. Fix these first.")


# ---------- 5. Export ----------

with tab_export:
    if not quiz or not cmap:
        st.info("Generate a quiz first.")
    else:
        slug = "".join(ch if ch.isalnum() else "_" for ch in quiz.topic.lower()).strip("_")[:40] or "quiz"
        c1, c2 = st.columns(2)
        with c1:
            st.download_button("GIFT (Moodle import)", export.to_gift(quiz),
                               file_name=f"{slug}.gift.txt", use_container_width=True)
            st.download_button("CSV", export.to_csv(quiz, cmap),
                               file_name=f"{slug}.csv", use_container_width=True)
        with c2:
            st.download_button("Markdown (SME review)", export.to_markdown(quiz, cmap, evaluation),
                               file_name=f"{slug}.md", use_container_width=True)
            st.download_button("Full project (JSON)",
                               export.to_bundle(st.session_state.source, st.session_state.audience,
                                                cmap, quiz, evaluation),
                               file_name=f"{slug}.json", use_container_width=True)
        with st.expander("Preview GIFT"):
            st.code(export.to_gift(quiz), language="text")
