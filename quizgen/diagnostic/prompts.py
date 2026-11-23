"""Prompts for each stage. Kept in one place so they're easy to tune."""

SYSTEM = (
    "You are an experienced instructional designer and learning scientist. "
    "You build assessments grounded in the source material only. "
    "If the source doesn't support something, leave it out rather than inventing it."
)

CONCEPT_MAP = """Read the source material below and build a concept map for it.

Audience: {audience}

Do this:
1. Write 2-4 measurable learning objectives (start each with an action verb).
2. Pull out the {n_concepts} most important concepts. Keep each one small enough to test with a single question.
3. For each concept, list prerequisite concepts by id. Prerequisites must point to other concepts in this map, and there must be no cycles.
4. For each concept, list 1-3 misconceptions: specific wrong beliefs a real learner in this audience would plausibly hold, and why they fall into them. Avoid strawmen nobody believes.

Use ids like c1, c2... for concepts and m1, m2... for misconceptions (misconception ids unique across the whole map).

<source>
{source}
</source>"""

QUIZ = """Write a multiple-choice quiz from this concept map and source.

Audience: {audience}
Number of questions: {n_questions}

Rules:
- Every question tests exactly one concept (concept_id) and states its Bloom level. Lean toward apply/analyze over remember.
- Order questions so prerequisites come before the concepts that depend on them.
- 4 options (a-d), exactly one correct.
- Every wrong option must target a misconception from the map (misconception_id) belonging to that question's concept or one of its prerequisites. That's what makes the distractors diagnostic.
- Feedback for each option says why it is right or wrong, in one or two plain sentences. For wrong options, address the misconception directly without shaming.
- No "all of the above" / "none of the above". No negatively worded stems unless the word NOT is in caps. Keep options similar in length so the longest one isn't a giveaway.
- Plain language, no idioms, names and scenarios that don't assume a particular culture or gender.

<concept_map>
{concept_map}
</concept_map>

<source>
{source}
</source>"""

EVALUATE = """You are reviewing a quiz someone else wrote. Be a tough, fair reviewer.

Score each question 1-4 on each rubric dimension (1 = serious problem, 4 = solid):
- alignment: tests the concept and objective it claims to
- accuracy: keyed answer is correct per the source; the other options are clearly wrong
- distractor_quality: wrong answers are plausible and tied to real misconceptions
- clarity: stem is clear, no tricks, no grammatical or length cues that give the answer away
- accessibility: plain language, sensible reading level for the audience, no idioms, nothing that depends on seeing an image
- bias: 4 means no cultural, gender, or background assumptions

List concrete issues and give a suggested fix for anything scoring below 3. Don't pad with praise. Then write 2-3 sentences of overall notes, including any gaps in concept coverage.

Audience: {audience}

<concept_map>
{concept_map}
</concept_map>

<quiz>
{quiz}
</quiz>

<source>
{source}
</source>"""
