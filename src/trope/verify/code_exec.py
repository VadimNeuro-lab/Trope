"""V_P for code benchmarks: run the candidate against the problem's own tests."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trope.data.base import Problem
from trope.verify.base import Verdict, at_least

DEFAULT_TIMEOUT = 10.0
DEFAULT_MEMORY_MB = 1024

_SENTINEL = "##TROPE##"
_FENCE = re.compile(r"```[ \t]*([A-Za-z0-9_+#-]*)[ \t]*\r?\n(.*?)```", re.DOTALL)
_PY_LANGS = frozenset({"", "python", "py", "python3"})

_HARNESS = '''\
import json, os, sys, traceback

try:
    import resource
    limit = int(sys.argv[1]) * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
except Exception:
    pass

here = os.path.dirname(os.path.abspath(__file__))
sentinel = sys.argv[2]


def emit(index, status, message):
    sys.stdout.write(
        sentinel + json.dumps({"i": index, "status": status, "message": message}) + "\\n"
    )
    sys.stdout.flush()


with open(os.path.join(here, "solution.py"), encoding="utf-8") as fh:
    source = fh.read()
with open(os.path.join(here, "tests.json"), encoding="utf-8") as fh:
    tests = json.load(fh)

namespace = {"__name__": "__trope_candidate__"}
try:
    exec(compile(source, "solution.py", "exec"), namespace)
except BaseException:
    emit(-1, "error", traceback.format_exc(limit=3)[-500:])
    raise SystemExit(0)

for index, test in enumerate(tests):
    try:
        exec(compile(test, "test_%d" % index, "exec"), dict(namespace))
    except AssertionError as exc:
        emit(index, "fail", str(exc)[:200] or "assertion failed")
    except BaseException:
        emit(index, "error", traceback.format_exc(limit=2)[-300:])
    else:
        emit(index, "pass", "")
'''


@dataclass(frozen=True, slots=True)
class TestOutcome:
    index: int
    passed: bool
    status: str
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "passed": self.passed,
            "status": self.status,
            "message": self.message,
        }


def extract_code(text: str) -> str:
    """The Python block a candidate settled on, or the raw text if unfenced."""
    blocks = [(lang.lower(), body) for lang, body in _FENCE.findall(text)]
    for wanted in (_PY_LANGS - {""}, {""}):
        tagged = [body for lang, body in blocks if lang in wanted]
        if tagged:
            return tagged[-1]
    if blocks:
        return blocks[-1][1]
    opened = text.rfind("```")
    if opened != -1:
        tail = text[opened + 3 :]
        return tail.split("\n", 1)[1] if "\n" in tail else ""
    return text


def _parse_records(stdout: str) -> dict[int, tuple[str, str]]:
    records: dict[int, tuple[str, str]] = {}
    for line in stdout.splitlines():
        start = line.find(_SENTINEL)
        if start == -1:
            continue
        try:
            payload = json.loads(line[start + len(_SENTINEL) :])
        except json.JSONDecodeError:
            continue
        records[int(payload["i"])] = (str(payload["status"]), str(payload["message"]))
    return records


def run_tests(
    code: str,
    tests: Sequence[str],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    memory_mb: int = DEFAULT_MEMORY_MB,
    allow_site: bool = False,
) -> tuple[TestOutcome, ...]:
    """Execute `code` then each test in a fresh interpreter, one outcome each."""
    if not tests:
        return ()
    flags = ["-I"] if allow_site else ["-I", "-S"]
    with tempfile.TemporaryDirectory(prefix="trope-exec-") as tmp:
        root = Path(tmp)
        (root / "solution.py").write_text(code, encoding="utf-8")
        (root / "tests.json").write_text(
            json.dumps(list(tests)), encoding="utf-8"
        )
        (root / "harness.py").write_text(_HARNESS, encoding="utf-8")
        cmd = [
            sys.executable,
            *flags,
            str(root / "harness.py"),
            str(int(memory_mb)),
            _SENTINEL,
        ]
        timed_out = False
        try:
            proc = subprocess.run(
                cmd,
                cwd=tmp,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=timeout,
            )
            stdout, stderr = proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout, stderr = exc.stdout or b"", exc.stderr or b""

    records = _parse_records(stdout.decode("utf-8", "replace"))
    if -1 in records:
        _, message = records[-1]
        return tuple(
            TestOutcome(i, False, "error", message) for i in range(len(tests))
        )
    outcomes: list[TestOutcome] = []
    for i in range(len(tests)):
        if i in records:
            status, message = records[i]
            outcomes.append(TestOutcome(i, status == "pass", status, message))
        elif timed_out:
            outcomes.append(
                TestOutcome(i, False, "timeout", f"no result within {timeout:g}s")
            )
        else:
            outcomes.append(
                TestOutcome(
                    i,
                    False,
                    "not_run",
                    stderr.decode("utf-8", "replace")[-200:],
                )
            )
    return tuple(outcomes)


class CodeExecVerifier:
    """V_P for the code family: verdict is the fraction of the problem's tests that pass, and only a clean sweep verifies."""

    name = "code_exec"

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        memory_mb: int = DEFAULT_MEMORY_MB,
        allow_site: bool = False,
    ) -> None:
        self.timeout = float(timeout)
        self.memory_mb = int(memory_mb)
        self.allow_site = bool(allow_site)
        self.verified_predicate = at_least(1.0)

    def __call__(self, problem: Problem, candidate_text: str) -> Verdict:
        if not problem.tests:
            return Verdict(0.0, False, "problem carries no executable tests")
        code = extract_code(candidate_text)
        if not code.strip():
            return Verdict(0.0, False, "candidate contains no code")
        outcomes = run_tests(
            code,
            problem.tests,
            timeout=self.timeout,
            memory_mb=self.memory_mb,
            allow_site=self.allow_site,
        )
        passed = sum(1 for o in outcomes if o.passed)
        value = passed / len(outcomes)
        first_bad = next((o for o in outcomes if not o.passed), None)
        detail = f"{passed}/{len(outcomes)} tests passed"
        if first_bad is not None:
            detail += f"; test {first_bad.index} {first_bad.status}: {first_bad.message.strip()[:160]}"
        return Verdict(
            value,
            passed == len(outcomes),
            detail,
            {"outcomes": [o.to_dict() for o in outcomes], "entry_point": problem.entry_point},
        )
