"""Run untrusted code and its tests somewhere it can't do harm.

With E2B_API_KEY set, each run happens in a fresh E2B cloud sandbox that holds none of
our API keys. Use this for any hosted demo: pasted code must never run on the server
that holds NEBIUS_API_KEY.

Without it, runs happen locally in a throwaway folder with CPU, memory and time limits.
That is fine on your own laptop, but it does NOT block network access or file reads.
"""

import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass

TIMEOUT_S = 20
MEMORY_BYTES = 512 * 1024 * 1024
E2B_WORKDIR = "/home/user/work"
E2B_SETUP = (
    f"mkdir -p {E2B_WORKDIR} && (python3 -m pytest --version"
    " || python3 -m pip install -q pytest"
    " || python3 -m pip install -q --user --break-system-packages pytest) >/dev/null 2>&1"
)
PYTEST_ARGS = ["-q", "-p", "no:cacheprovider"]


@dataclass
class TestRun:
    passed: int
    failed: int
    output: str
    timed_out: bool = False
    crashed: bool = False


def run_tests(code: str, tests: str) -> TestRun:
    """Run tests (test_solution.py) against code (solution.py) with pytest."""
    if os.environ.get("E2B_API_KEY"):
        return _run_in_e2b(code, tests)
    if os.environ.get("SECONDLOOK_HOSTED"):
        # Running pasted code next to the API keys would let anyone read them.
        return TestRun(0, 0, "Tests are switched off on this server until E2B_API_KEY is set.", crashed=True)
    return _run_locally(code, tests)


def _run_in_e2b(code: str, tests: str) -> TestRun:
    from e2b import CommandExitException, Sandbox, TimeoutException

    try:
        sbx = Sandbox.create(timeout=TIMEOUT_S + 120)
    except Exception as e:
        return TestRun(0, 0, f"Couldn't start the E2B sandbox: {type(e).__name__}: {e}", crashed=True)
    try:
        sbx.commands.run(E2B_SETUP, timeout=90)
        sbx.files.write(f"{E2B_WORKDIR}/solution.py", code)
        sbx.files.write(f"{E2B_WORKDIR}/test_solution.py", tests)
        try:
            result = sbx.commands.run("python3 -m pytest " + " ".join(PYTEST_ARGS), cwd=E2B_WORKDIR, timeout=TIMEOUT_S)
        except CommandExitException as e:
            result = e  # pytest exits with 1 when a test fails; that's a normal result here
        except TimeoutException as e:
            return TestRun(0, 0, f"Timed out after {TIMEOUT_S}s ({e})", timed_out=True)
        return _result(result.stdout + result.stderr, result.exit_code)
    except Exception as e:
        return TestRun(0, 0, f"The E2B sandbox failed: {type(e).__name__}: {e}", crashed=True)
    finally:
        try:
            sbx.kill()
        except Exception:
            pass


def _limit_resources():
    import resource

    # macOS refuses RLIMIT_AS, so each limit is best effort; the timeout still applies.
    for limit, value in ((resource.RLIMIT_CPU, TIMEOUT_S), (resource.RLIMIT_AS, MEMORY_BYTES)):
        try:
            resource.setrlimit(limit, (value, value))
        except (ValueError, OSError):
            pass


def _run_locally(code: str, tests: str) -> TestRun:
    """Write code as solution.py and tests as test_solution.py, then run pytest."""
    workdir = tempfile.mkdtemp(prefix="secondlook-")
    try:
        with open(os.path.join(workdir, "solution.py"), "w") as f:
            f.write(code)
        with open(os.path.join(workdir, "test_solution.py"), "w") as f:
            f.write(tests)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", *PYTEST_ARGS, "--rootdir", workdir, workdir],
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_S + 5,
                preexec_fn=_limit_resources if os.name == "posix" else None,  # Windows has no rlimits
                env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
            )
        except subprocess.TimeoutExpired as e:
            return TestRun(0, 0, (e.stdout or "") + "\nTimed out", timed_out=True)
        return _result(proc.stdout + proc.stderr, proc.returncode)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _result(out: str, returncode: int) -> TestRun:
    passed = _count(out, "passed")
    failed = _count(out, "failed") + _count(out, "error")
    killed = {-getattr(signal, name) for name in ("SIGXCPU", "SIGKILL") if hasattr(signal, name)} | {137}
    if returncode in killed:
        return TestRun(passed, failed, out + "\nKilled: hit the CPU or memory limit (infinite loop?)", timed_out=True)
    crashed = returncode != 0 and passed + failed == 0
    return TestRun(passed, failed, out, crashed=crashed)


def failing_tests(output: str) -> list[str]:
    """Names of failed or erroring tests, from pytest's short summary."""
    return re.findall(r"^(?:FAILED|ERROR) \S*?::(\w+)", output, re.M)


def _count(output: str, word: str) -> int:
    m = re.search(rf"(\d+) {word}", output)
    return int(m.group(1)) if m else 0
