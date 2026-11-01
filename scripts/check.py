"""Run every automatic check and say clearly WHICH ONE failed.

    uv run python scripts/check.py          # lint + types + fast tests (seconds)
    uv run python scripts/check.py --all    # ...plus the slow real-OCR tests (minutes)

Each check answers a different question, so a failure tells you where to look:

    lint   (ruff)    Is the code written safely and tidily? (unused names, bug-prone patterns)
    types  (mypy)    Do the type hints agree with how values are really used?
    tests  (pytest)  Does the program still BEHAVE the way we decided it should?
"""
from __future__ import annotations

import subprocess
import sys
import time

PY = sys.executable  # the interpreter running this script = the project's virtual environment


def run_check(name: str, cmd: list[str]) -> tuple[bool, float, str]:
    start = time.perf_counter()
    proc = subprocess.run([PY, "-m", *cmd], capture_output=True, text=True)
    seconds = time.perf_counter() - start
    output = (proc.stdout + proc.stderr).strip()
    return proc.returncode == 0, seconds, output


def last_line(text: str) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def main() -> int:
    run_slow = "--all" in sys.argv
    pytest_cmd = ["pytest", "-q", "--cov", "--cov-report=term"]
    if run_slow:
        pytest_cmd += ["-m", "slow or not slow"]

    checks = [
        ("lint", ["ruff", "check", "."], "ruff"),
        ("types", ["mypy"], "mypy"),
        ("tests", pytest_cmd, "pytest"),
    ]

    failed: list[str] = []
    print()
    for name, cmd, tool in checks:
        ok, seconds, output = run_check(name, cmd)
        status = "PASS" if ok else "FAIL"
        print(f"  {status}  {name:<6} ({tool}, {seconds:4.1f}s)  {last_line(output)}")
        if not ok:
            failed.append(name)
            print("\n" + "\n".join("      " + ln for ln in output.splitlines()[-40:]) + "\n")
        elif name == "tests":
            total = next((ln for ln in output.splitlines() if ln.startswith("TOTAL")), "")
            if total:
                print(f"        coverage: {total.split()[-1]}")

    print()
    if failed:
        print(f"  {len(failed)} of {len(checks)} checks FAILED: {', '.join(failed)}")
        return 1
    print("  All checks passed. The project is in a known-good state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
