"""Explain a failure to a beginner, hints first."""

from . import llm

SYSTEM = """You are a patient coding mentor for a beginner who got this code from an AI.
Explain the problem shown by the failing test output or flag. Return JSON:
{"bug_type": one of ["invented package or function", "outdated API", "missing edge case",
  "off-by-one", "insecure default", "swallowed error", "wrong input assumption", "other"],
 "predict_question": "<a question asking the learner what the code does for the failing input>",
 "hint": "<a nudge that does not reveal the line or the fix>",
 "line": "<the exact line of code at fault>",
 "fix": "<the corrected code for that part, plus one sentence on why>"}
Use simple words. No jargon without explaining it."""


def explain(code: str, problem: str) -> dict:
    return llm.chat_json(llm.NANO, SYSTEM, f"Code:\n{code}\n\nProblem found:\n{problem}")
