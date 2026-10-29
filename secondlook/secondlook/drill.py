"""Practice drill: spot the planted AI-typical bug, get scored, see your weak spots.

Every exercise carries a hidden test that passes on the fixed code and fails on the
buggy code, so each drill has a proven answer. Check them all with:
    python -m secondlook.drill
"""

import difflib
import json
import random
import sys
from pathlib import Path

from . import sandbox

BUG_TYPES = [
    "invented package or function",
    "outdated API",
    "missing edge case",
    "off-by-one",
    "insecure default",
    "swallowed error",
    "wrong input assumption",
]

DRILL_DIR = Path(__file__).resolve().parent.parent / "drills"

FEEDBACK_SYSTEM = """You are a friendly coding tutor. A beginner was shown AI-written code with one planted bug
and tried to explain the bug in their own words. Compare their explanation with the real bug. Return JSON:
{"verdict": "right" | "partly right" | "not yet",
 "feedback": "<one or two encouraging sentences that confirm or correct them, in simple words>"}"""


def load_exercises(drill_dir: Path = DRILL_DIR) -> list[dict]:
    """Hand-checked seed exercises plus any verified ones from the generator."""
    exercises = []
    for name in ("seed.json", "generated.json"):
        path = Path(drill_dir) / name
        if path.exists():
            exercises += json.loads(path.read_text())
    return exercises


def verify(ex: dict) -> str | None:
    """Return None if the exercise is sound, otherwise the reason it isn't."""
    if ex.get("bug_type") not in BUG_TYPES:
        return f"unknown bug type {ex.get('bug_type')!r}"
    n = len(ex["code"].splitlines())
    if not ex.get("bug_lines") or not all(1 <= line <= n for line in ex["bug_lines"]):
        return "bug_lines are missing or out of range"
    good = sandbox.run_tests(ex["fixed"], ex["test"])
    if good.failed or good.timed_out or good.crashed or not good.passed:
        return "the fixed code fails its own test"
    bad = sandbox.run_tests(ex["code"], ex["test"])
    if not (bad.failed or bad.timed_out or bad.crashed):
        return "the test doesn't catch the planted bug"
    return None


def changed_lines(code: str, fixed: str) -> list[int]:
    """1-based lines of `code` that the fix touches.

    A pure insertion (say, a missing `if not items: return 0`) has no buggy line of its own,
    so the line before it and the two after it all count as the bug's location.
    """
    a, b = code.splitlines(), fixed.splitlines()
    lines = set()
    for tag, i1, i2, _, _ in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag in ("replace", "delete"):
            lines.update(range(i1 + 1, i2 + 1))
        elif tag == "insert":
            lines.update(n for n in (i1, i1 + 1, i1 + 2) if 1 <= n <= len(a))
    return sorted(n for n in lines if a[n - 1].strip() and not a[n - 1].strip().startswith("#"))


def grade(ex: dict, line: int, bug_type: str) -> dict:
    return {"line_ok": line in ex["bug_lines"], "type_ok": bug_type == ex["bug_type"]}


def skill_profile(history: list[dict]) -> dict[str, tuple[int, int]]:
    """{bug_type: (caught, seen)} from attempts like {"bug_type": ..., "line_ok": ...}."""
    profile = {}
    for attempt in history:
        caught, seen = profile.get(attempt["bug_type"], (0, 0))
        profile[attempt["bug_type"]] = (caught + attempt["line_ok"], seen + 1)
    return profile


def profile_summary(profile: dict[str, tuple[int, int]]) -> str:
    strong = [t for t, (c, s) in profile.items() if c / s >= 0.67]
    weak = sorted((t for t, (c, s) in profile.items() if c / s < 0.5), key=lambda t: profile[t][0] / profile[t][1])
    if not weak and not strong:
        return "Keep going: a few more drills will show your strengths and weak spots."
    parts = []
    if strong:
        parts.append(f"You catch {_join(strong)} bugs")
    if weak:
        parts.append(f"{'but you' if strong else 'You'} miss {_join(weak)} bugs. Next up: more {weak[0]} drills")
    return ", ".join(parts) + "."


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def next_exercise(exercises: list[dict], seen_ids: set[str], profile: dict, rng=random) -> dict:
    """Pick an unseen exercise of the learner's weakest bug type; unseen types count as half caught."""
    unseen = [e for e in exercises if e["id"] not in seen_ids] or exercises

    def catch_rate(bug_type):
        caught, seen = profile.get(bug_type, (0, 0))
        return caught / seen if seen else 0.5

    types = sorted({e["bug_type"] for e in unseen}, key=lambda t: (catch_rate(t), rng.random()))
    return rng.choice([e for e in unseen if e["bug_type"] == types[0]])


def feedback(ex: dict, learner_text: str) -> dict:
    """Nemotron 3 Super judges the learner's own explanation of the bug."""
    from . import llm

    user = (
        f"Code:\n{ex['code']}\n\nThe real bug ({ex['bug_type']}, line {ex['bug_lines']}): {ex['explanation']}\n\n"
        f"The learner's explanation:\n{learner_text}"
    )
    return llm.chat_json(llm.SUPER, FEEDBACK_SYSTEM, user)


if __name__ == "__main__":
    exercises = load_exercises()
    bad = 0
    for ex in exercises:
        reason = verify(ex)
        bad += reason is not None
        print(f"{'FAIL' if reason else 'ok  '} {ex['id']:<24} {reason or ''}")
    print(f"{len(exercises) - bad} of {len(exercises)} exercises verified")
    sys.exit(1 if bad else 0)
