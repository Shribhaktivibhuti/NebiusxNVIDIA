"""Run the full second look: registry check, docs check, break-it tests, explanations.

Every outside call (PyPI, Tavily, Nemotron) may fail on its own. A failed step is skipped
and noted in report.warnings, so the app never crashes halfway through a check.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import docs_check, explainer, registry, sandbox, tester

MAX_DOC_CALLS = 5


@dataclass
class Report:
    packages: list = field(default_factory=list)
    calls: list = field(default_factory=list)
    tests: str = ""
    run: sandbox.TestRun | None = None
    explanations: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    syntax_error: str = ""


def second_look(code: str, intent: str, check_docs: bool = True) -> Report:
    report = Report()
    try:
        compile(code, "solution.py", "exec")
    except SyntaxError as e:
        report.syntax_error = f"line {e.lineno}: {e.msg}"
        _explain(report, code, [f"The code does not run at all: SyntaxError on {report.syntax_error}"])
        return report

    report.packages = _attempt(report, "the package check", registry.check_packages, code) or []

    if check_docs:
        calls = docs_check.library_calls(code)[:MAX_DOC_CALLS]
        with ThreadPoolExecutor(MAX_DOC_CALLS) as pool:
            checked = pool.map(
                lambda c: _attempt(report, f"the docs check for `{c['call']}`", docs_check.check_call, c["call"], c["library"]),
                calls,
            )
        report.calls = [c for c in checked if c]

    report.tests = _attempt(report, "writing tests", tester.write_tests, code, intent) or ""
    if report.tests:
        report.run = sandbox.run_tests(code, report.tests)

    problems = [f"Package `{p.package}`: {p.detail}" for p in report.packages if not p.exists]
    problems += [f"`{c['call']}`: {c.get('explanation', '')}" for c in report.calls if c.get("status") not in ("ok", "unsure")]
    if report.run and (report.run.failed or report.run.timed_out or report.run.crashed):
        problems.append("Failing tests:\n" + report.run.output[-3000:])
    _explain(report, code, problems)
    return report


def _explain(report: Report, code: str, problems: list[str]) -> None:
    with ThreadPoolExecutor(4) as pool:
        explained = pool.map(lambda p: _attempt(report, "an explanation", explainer.explain, code, p), problems)
    report.explanations = [e for e in explained if e]


def _attempt(report: Report, step: str, fn, *args):
    try:
        return fn(*args)
    except Exception as e:
        report.warnings.append(f"Skipped {step}: {_short(e)}")
        return None


def _short(e: Exception) -> str:
    lines = str(e).strip().splitlines()
    return f"{type(e).__name__}: {lines[0][:160]}" if lines else type(e).__name__
