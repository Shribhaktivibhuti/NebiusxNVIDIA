"""Generate verified drill exercises with Nemotron 3 Ultra.

Each candidate is a fresher task with one planted AI-typical bug, the fixed code and a
hidden pytest test. A candidate is kept only if the test passes on the fixed code and
fails on the buggy code, so every drill has a proven answer.

    python -m secondlook.drill_generator --count 50

Results are appended to drills/generated.json, saved after every batch.
"""

import argparse
import hashlib
import json
import random
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import drill, llm, registry
from .tester import _strip_fences

TASKS = [
    "Count how many times each word appears in a text file.",
    "Return the second largest number in a list.",
    "Check whether a password is strong: at least 8 characters, one digit and one uppercase letter.",
    "Convert a list of temperatures from Celsius to Fahrenheit.",
    "Read a CSV of students (name, marks) and return the name of the top scorer.",
    "Return the grade letter for a mark from 0 to 100 (A for 90 and above, B for 80 and above, C for 70 and above, D for 60 and above, otherwise F).",
    "Remove duplicate emails from a list, ignoring upper and lower case, keeping the first one seen.",
    "Split a restaurant bill equally between friends, rounded to 2 decimal places.",
    "Check whether a string is a palindrome, ignoring spaces, punctuation and case.",
    "Merge two sorted lists into one sorted list.",
    "Return the last n lines of a log file that contain the word ERROR.",
    "Calculate simple interest from a principal, a yearly rate in percent and a number of years.",
    "Turn a time like '14:05' into the number of minutes since midnight.",
    "Save a user's score in a SQLite table and look it up by username.",
    "Check whether a Singapore postal code is valid: exactly 6 digits.",
    "List the .txt files in a folder, sorted by name.",
    "Work out a GPA from a list of (grade_points, credits) pairs.",
    "Return the running total of a list of daily sales.",
    "Group (name, department) pairs into a dictionary of department to list of names.",
    "Turn a list of 'key=value' strings into a dictionary.",
    "Hide all but the last four digits of a card number with asterisks.",
    "Count the working days (Monday to Friday) between two dates, counting both ends.",
    "Work out someone's age in whole years from their birth date and today's date.",
    "Get a nested value from a dictionary using a path like 'a.b.c', returning None if any part is missing.",
    "Return the initials of a full name, like 'Ada Lovelace' -> 'AL'.",
    "Find the index of a target number in a sorted list using binary search, or -1 if it isn't there.",
]

SYSTEM = """You create practice exercises that train beginner programmers to spot bugs that AI chatbots
typically put in Python code.

Given a task and a bug type, write:
- "task": the task as a beginner would ask a chatbot, stating the exact expected behaviour, including the
  case the bug gets wrong (for example "return 0.0 for an empty list").
- "fixed": a correct, complete Python module that solves the task. Standard library only, under 25 lines,
  with a short docstring.
- "code": the same module with exactly ONE planted bug of the given type, changing as few lines as possible.
  It must look like confident chatbot output. No comment, name or docstring may hint at the bug.
- "test": a pytest file that imports from the module `solution` (for example `from solution import func`).
  It must pass on "fixed" and fail on "code". Use tmp_path for files and sqlite3 ":memory:" for databases.
  Never use the network.
- "explanation": two short sentences for a beginner: what goes wrong, and how to fix it.

Bug types:
- invented package or function: imports a package that does not exist on PyPI, or calls a function that
  does not exist in a real standard-library module.
- outdated API: uses something removed from Python or its standard library, such as time.clock,
  collections.Mapping, cgi.escape, base64.encodestring or inspect.getargspec.
- missing edge case: crashes or gives a wrong answer for empty input, zero, None or a single item.
- off-by-one: a range, index, slice or count is one too many or one too few.
- insecure default: SQL built by pasting strings, or eval/exec on user input, where the test shows the harm.
- swallowed error: a bare or broad except hides an error that the task says must be raised.
- wrong input assumption: assumes the wrong format, such as no header row, US month/day order, single
  spaces between words, or names that always have two parts.

Return JSON with the keys task, code, fixed, test and explanation."""

GIVEAWAY = re.compile(r"#.*\b(bug|wrong|incorrect|fixme|todo|oops|vulnerab|insecure|unsafe|deprecated)", re.I)
KEYS = ("id", "bug_type", "task", "code", "bug_lines", "fixed", "test", "explanation")


def attempt(task: str, bug_type: str, model: str) -> tuple[dict | None, str | None]:
    """One model call. Returns (exercise, None) if it passes every check, else (None, reason)."""
    try:
        raw = llm.chat_json(model, SYSTEM, f"Task: {task}\nBug type: {bug_type}", temperature=0.8, timeout=300)
    except Exception as e:
        return None, f"unusable model reply ({type(e).__name__})"
    ex = {k: raw.get(k) for k in ("task", "code", "fixed", "test", "explanation")}
    if not all(isinstance(v, str) and v.strip() for v in ex.values()):
        return None, "missing fields"
    for k in ("code", "fixed", "test"):
        ex[k] = _strip_fences(ex[k])
    ex["task"], ex["explanation"] = ex["task"].strip(), ex["explanation"].strip()
    ex["bug_type"] = bug_type
    ex["bug_lines"] = drill.changed_lines(ex["code"], ex["fixed"])

    if not ex["bug_lines"]:
        return None, "buggy and fixed code are the same"
    if len(ex["bug_lines"]) > 5:
        return None, "the fix changes too many lines"
    if len(ex["code"].splitlines()) > 30:
        return None, "too long"
    if GIVEAWAY.search(ex["code"]):
        return None, "a comment gives the bug away"
    try:
        imports = registry.check_packages(ex["code"]) + registry.check_packages(ex["fixed"])
    except SyntaxError:
        return None, "code doesn't parse"
    if any(p.exists for p in imports):
        return None, "needs a package outside the standard library"
    if imports and bug_type != "invented package or function":
        return None, "imports a made-up package for the wrong bug type"
    reason = drill.verify(ex)
    return (None, reason) if reason else (ex, None)


def _fingerprint(code: str) -> str:
    return hashlib.sha1(re.sub(r"\s+", "", code).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Generate verified drill exercises with Nemotron.")
    parser.add_argument("--count", type=int, default=50, help="verified exercises to add (default 50)")
    parser.add_argument("--max-attempts", type=int, help="stop after this many model calls (default 3 x count)")
    parser.add_argument("--model", default=llm.ULTRA)
    parser.add_argument("--out", type=Path, default=drill.DRILL_DIR / "generated.json")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    existing = json.loads(args.out.read_text()) if args.out.exists() else []
    seen = {_fingerprint(e["code"]) for e in existing + drill.load_exercises()}
    max_attempts = args.max_attempts or 3 * args.count
    added, rejected, attempts = [], Counter(), 0
    rng = random.Random()

    with ThreadPoolExecutor(args.workers) as pool:
        while len(added) < args.count and attempts < max_attempts:
            batch = min(args.workers, max_attempts - attempts)
            jobs = [(rng.choice(TASKS), drill.BUG_TYPES[(attempts + i) % len(drill.BUG_TYPES)]) for i in range(batch)]
            attempts += batch
            for ex, reason in pool.map(lambda job: attempt(*job, args.model), jobs):
                if reason:
                    rejected[reason] += 1
                    continue
                if len(added) >= args.count:
                    continue
                fingerprint = _fingerprint(ex["code"])
                if fingerprint in seen:
                    rejected["duplicate"] += 1
                    continue
                seen.add(fingerprint)
                ex["id"] = f"gen-{fingerprint[:10]}"
                added.append({k: ex[k] for k in KEYS})
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(existing + added, indent=2) + "\n")
            print(f"{len(added)}/{args.count} kept after {attempts} attempts", flush=True)

    print(f"\nKept {len(added)} new exercises in {args.out} ({len(existing) + len(added)} total).")
    for reason, n in rejected.most_common():
        print(f"  rejected {n}: {reason}")
    print("By bug type:", dict(Counter(e["bug_type"] for e in added)))


if __name__ == "__main__":
    main()
