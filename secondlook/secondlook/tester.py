"""Write pytest tests that try to break the AI's code."""

from . import llm

SYSTEM = """You are a strict Python tester helping a beginner check AI-written code.
Write pytest tests for the module `solution` (import from it with `from solution import ...`).
Test the INTENDED behaviour described by the user, not what the code happens to do.
Always cover: a normal case, empty input, zero or None where relevant, negative numbers,
boundary values (first/last element), unusual text (Unicode, whitespace), and wrong input format.
Use tmp_path for any files. Never use the network. Give each test a descriptive name.
Return only the Python test file, no prose, no code fences."""


def write_tests(code: str, intent: str, model: str = llm.SUPER) -> str:
    user = f"What the code is supposed to do:\n{intent or '(not given; infer it from the code)'}\n\nCode (solution.py):\n{code}"
    tests = _strip_fences(llm.chat(model, SYSTEM, user))
    if not tests.strip():
        raise ValueError("Nemotron returned no tests")
    return tests


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip() + "\n"
