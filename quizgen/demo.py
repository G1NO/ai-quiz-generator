"""Offline demo: runs the full pipeline with a canned model response, no API key needed.

The canned response below is a fixed example written for the bundled sample
training content (examples/sample-training.md). It includes one deliberately
flawed question so you can see the quality checker in action.
"""

from __future__ import annotations

import json

SAMPLE_RESPONSE = {
    "questions": [
        {
            "objective": "Learners will be able to identify tasks that are a good fit for an AI assistant.",
            "bloom_level": "understand",
            "stem": "Which of these tasks is the best fit for an AI assistant?",
            "options": [
                {"text": "Drafting a first version of a team announcement", "correct": True,
                 "feedback": "Drafting is a strength. You review and edit before sending."},
                {"text": "Calculating final payroll totals for the month", "correct": False,
                 "feedback": "AI can make math errors. Use your payroll system or a spreadsheet."},
                {"text": "Deciding which employee gets a promotion", "correct": False,
                 "feedback": "Decisions about people need human judgment and context the AI doesn't have."},
                {"text": "Confirming a vendor's price for today", "correct": False,
                 "feedback": "The AI may give an outdated or invented number. Check the vendor directly."},
            ],
        },
        {
            "objective": "Learners will be able to write a prompt that includes a goal, context and format.",
            "bloom_level": "apply",
            "stem": "Jordan needs to tell a long-time client their order is delayed one week by a supplier. Which prompt will get the most usable first draft?",
            "options": [
                {"text": "\"Write an email to our client about their order being delayed by our supplier.\"", "correct": False,
                 "feedback": "It has a goal and some context, but no format, so the AI has to guess the tone and length."},
                {"text": "\"Write a short apology email to a long-time client about a one-week supplier delay. Warm, under 120 words.\"", "correct": True,
                 "feedback": "It has a clear goal, the context (who, what, why) and the format (tone and length)."},
                {"text": "\"Write a professional email that is warm, friendly and under 120 words, with a helpful tone.\"", "correct": False,
                 "feedback": "Format only. The AI doesn't know what happened or who the email is for."},
                {"text": "\"Our supplier delayed a long-time client's order by one week, and they are a valued customer.\"", "correct": False,
                 "feedback": "Context only. There's no goal, so the AI doesn't know what you want it to write."},
            ],
        },
        {
            "objective": "Learners will be able to decide what information is safe to share with an AI tool.",
            "bloom_level": "apply",
            "stem": "A coworker wants to paste a customer's name, address and account number into a public AI tool to draft a letter. What should they do instead?",
            "options": [
                {"text": "Replace the details with placeholders like [Customer] and fill them in afterward", "correct": True,
                 "feedback": "The AI drafts the letter, and the personal data never leaves your hands."},
                {"text": "Paste it in, since most AI tools delete chat history automatically after a while", "correct": False,
                 "feedback": "Many tools store what you paste. Don't assume it gets deleted."},
                {"text": "Paste it in, as long as the customer has been with the company for years", "correct": False,
                 "feedback": "How long someone has been a customer doesn't change the data risk."},
                {"text": "Share just the account number and leave the customer's name and address out", "correct": False,
                 "feedback": "An account number on its own is still sensitive. Use a placeholder instead."},
            ],
        },
        {
            "objective": "Learners will be able to review AI output for errors before using it.",
            "bloom_level": "apply",
            "stem": "The AI gives you a statistic to put in a report for leadership. What should you do first?",
            "options": [
                {"text": "Confirm it in a reliable source before you use it", "correct": True,
                 "feedback": "AI can invent numbers that sound real. Facts always get checked."},
                {"text": "Ask the AI to double-check whether the number is right", "correct": False,
                 "feedback": "The AI may repeat the same wrong answer confidently. Check a real source."},
                {"text": "Round the number so it looks cleaner in the report", "correct": False,
                 "feedback": "Rounding a made-up number doesn't make it true."},
                {"text": "Use it as-is, since AI tools are usually accurate", "correct": False,
                 "feedback": "\"Usually\" isn't good enough for a report with your name on it."},
            ],
        },
        {
            "objective": "",
            "bloom_level": "remember",
            "stem": "Which of the following is NOT one of the four prompt habits?",
            "options": [
                {"text": "Goal", "correct": False, "feedback": "Incorrect."},
                {"text": "Context", "correct": False, "feedback": "Incorrect."},
                {"text": "Speed, because a fast prompt always gets the best answer from the assistant", "correct": True, "feedback": "Correct."},
                {"text": "All of the above", "correct": False, "feedback": "Incorrect."},
            ],
        },
    ]
}


class DemoClient:
    """Stands in for a real LLM client and returns the canned response."""

    def complete(self, system: str, user: str) -> str:
        return "Here is your quiz:\n```json\n" + json.dumps(SAMPLE_RESPONSE, indent=2) + "\n```"
