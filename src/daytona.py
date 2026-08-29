"""Execute generated Playwright reproductions in a Daytona sandbox.

The Daytona SDK intentionally remains an optional import so the rest of the
orchestrator (and unit tests) can run without credentials. At runtime install
``requirements.txt`` and provide ``DAYTONA_API_KEY`` either in the environment
or in a project-root ``.env`` file.

The runner targets npm web applications while repository selection is still in
progress.  Its defaults are equivalent to::

    npm ci || npm install
    npm install --no-save @playwright/test
    npx playwright install chromium
    npm run dev -- --host 0.0.0.0
    npx playwright test <generated test> --reporter=line

Set ``DAYTONA_ARTIFACT_DIR`` to control where screenshots, videos, traces, and
application logs downloaded before sandbox deletion are retained.
"""

from __future__ import annotations

import os
import posixpath
import shlex
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

try:  # Person 1's shared models take precedence as soon as they are available.
    from .models import ExecutionResult, ReproductionPlan
except ImportError:  # pragma: no cover - exercised only before shared models land
    @dataclass
    class ReproductionPlan:
        summary: str
        setup_notes: str
        test_file_name: str
        test_code: str
        expected_failure: str

    @dataclass
    class ExecutionResult:
        exit_code: int
        stdout: str
        stderr: str
        reproduced: bool = False
        reason: str = ""
        artifacts: list[str] = field(default_factory=list)


_REPO_DIR = "/home/daytona/repo"
_DEFAULT_SETUP = (
    "(npm ci || npm install) && "
    "npm install --no-save @playwright/test && "
    "npx playwright install chromium"
)
_DEFAULT_START = "npm run dev -- --host 0.0.0.0"
_PLAYWRIGHT_CONFIG = """const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  timeout: 30_000,
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:5173',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  reporter: [['line']],
});
"""
_ASSERTION_MARKERS = (
    "assertionerror",
    "expect(received)",
    "expect(locator)",
    "expected:",
    "received:",
    "to equal",
    "to be",
)
_INFRASTRUCTURE_MARKERS = (
    "syntaxerror",
    "cannot find module",
    "no tests found",
    "browser has been closed",
    "executable doesn't exist",
    "error: page.goto: net::",
    "error: page.goto: timeout",
    "test timeout of",
)


@dataclass
class _StageResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""


def _safe_test_path(file_name: str) -> str:
    """Return a repository-relative POSIX path, rejecting path traversal."""
    path = PurePosixPath(file_name or "reproduce.spec.ts")
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("test_file_name must stay inside the cloned repository")
    return str(path)


def _read_remote(sandbox: Any, path: str) -> str:
    value = sandbox.fs.download_file(path)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _run_stage(
    sandbox: Any,
    name: str,
    command: str,
    *,
    cwd: str = _REPO_DIR,
    timeout: int = 600,
) -> _StageResult:
    """Run a command while preserving stdout and stderr in separate files.

    Daytona's ExecuteResponse combines streams in ``result``.  Redirecting in
    the sandbox and downloading both files gives the orchestrator faithful
    stream capture while still retaining output when a command returns nonzero.
    """
    base = posixpath.join(cwd, ".repro-agent", name)
    stdout_path, stderr_path, code_path = (
        f"{base}.stdout",
        f"{base}.stderr",
        f"{base}.exitcode",
    )
    wrapped = (
        "mkdir -p .repro-agent; set +e; "
        f"( bash -lc {shlex.quote(command)} ) > {shlex.quote(stdout_path)} "
        f"2> {shlex.quote(stderr_path)}; code=$?; "
        f"printf '%s' \"$code\" > {shlex.quote(code_path)}; exit 0"
    )
    response = sandbox.process.exec(wrapped, cwd=cwd, timeout=timeout)
    fallback = str(getattr(response, "result", "") or "")
    try:
        stdout = _read_remote(sandbox, stdout_path)
        stderr = _read_remote(sandbox, stderr_path)
        code_text = _read_remote(sandbox, code_path).strip()
        exit_code = int(code_text)
    except Exception as exc:
        # A transport timeout can prevent the wrapper files from being written.
        response_code = int(getattr(response, "exit_code", 1) or 0)
        return _StageResult(
            response_code if response_code else 1,
            fallback,
            f"Could not collect {name} command streams: {exc}",
        )
    return _StageResult(exit_code, stdout, stderr)


def _result(
    stage: str,
    result: _StageResult,
    logs: list[tuple[str, _StageResult]],
    artifacts: list[str] | None = None,
) -> ExecutionResult:
    stdout = "\n".join(
        f"===== {name} stdout =====\n{item.stdout}" for name, item in logs if item.stdout
    )
    stderr = "\n".join(
        f"===== {name} stderr =====\n{item.stderr}" for name, item in logs if item.stderr
    )
    return ExecutionResult(
        exit_code=result.exit_code,
        stdout=stdout,
        stderr=stderr,
        reproduced=False,
        reason=f"{stage} failed with exit code {result.exit_code}",
        artifacts=artifacts or [],
    )


def _classify_test(result: _StageResult) -> tuple[bool, str]:
    if result.exit_code == 0:
        return False, "Playwright passed; the reported bug was not reproduced"
    output = f"{result.stdout}\n{result.stderr}".lower()
    if any(marker in output for marker in _INFRASTRUCTURE_MARKERS):
        return False, "Playwright could not complete due to a test or browser failure"
    if any(marker in output for marker in _ASSERTION_MARKERS):
        return True, "Playwright assertion failed as expected; bug reproduced"
    return False, "Playwright failed, but no assertion failure proved the reported bug"


def _download_artifacts(sandbox: Any, local_dir: Path) -> list[str]:
    """Download Playwright evidence and app logs before deleting the sandbox."""
    find_command = (
        "find test-results playwright-report .repro-agent "
        "-type f \\( -name '*.png' -o -name '*.webm' -o -name '*.zip' "
        "-o -name 'app.stdout' -o -name 'app.stderr' \\) 2>/dev/null || true"
    )
    response = sandbox.process.exec(find_command, cwd=_REPO_DIR, timeout=30)
    remote_paths = [line.strip() for line in str(getattr(response, "result", "")).splitlines()]
    saved: list[str] = []
    for remote in remote_paths:
        if not remote or remote.startswith("/") or ".." in PurePosixPath(remote).parts:
            continue
        destination = local_dir.joinpath(*PurePosixPath(remote).parts)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            content = sandbox.fs.download_file(posixpath.join(_REPO_DIR, remote))
            destination.write_bytes(content if isinstance(content, bytes) else str(content).encode())
            saved.append(str(destination))
        except Exception:
            # Artifact collection is best-effort and must not hide test results.
            continue
    return saved


def run_in_daytona(
    repo_url: str,
    plan: ReproductionPlan,
    setup_command: str | None = None,
    start_command: str | None = None,
    *,
    _daytona: Any | None = None,
) -> ExecutionResult:
    """Clone and execute a Playwright reproduction in a fresh Daytona sandbox.

    ``_daytona`` is a private dependency-injection seam used by focused tests.
    Production callers should omit it.  Every normal return is an
    :class:`ExecutionResult`; SDK, clone, setup, start, and test failures are
    converted into structured results rather than escaping the orchestrator.
    """
    if not repo_url or not repo_url.strip():
        return ExecutionResult(-1, "", "Repository URL is required", False, "Sandbox setup failed", [])

    try:
        test_path = _safe_test_path(plan.test_file_name)
    except (AttributeError, ValueError) as exc:
        return ExecutionResult(-1, "", str(exc), False, "Invalid reproduction plan", [])

    if _daytona is None:
        try:
            from dotenv import load_dotenv

            # Existing process variables win over values in the project file.
            # An explicit path also works under Python 3.14 and stdin-based CLIs.
            load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
            from daytona import Daytona

            _daytona = Daytona()
        except ImportError as exc:
            return ExecutionResult(
                -1,
                "",
                f"Missing runtime dependency ({exc.name}); run `pip install -r requirements.txt`",
                False,
                "Sandbox setup failed",
                [],
            )
        except Exception as exc:
            return ExecutionResult(
                -1,
                "",
                f"Could not configure Daytona client: {exc}",
                False,
                "Sandbox setup failed",
                [],
            )

    sandbox = None
    logs: list[tuple[str, _StageResult]] = []
    try:
        try:
            sandbox = _daytona.create()
            sandbox.git.clone(repo_url.strip(), _REPO_DIR, depth=1)
        except Exception as exc:
            return ExecutionResult(-1, "", f"Could not create sandbox or clone repository: {exc}", False, "Repository setup failed", [])

        try:
            remote_test_path = posixpath.join(_REPO_DIR, test_path)
            remote_parent = posixpath.dirname(remote_test_path)
            sandbox.process.exec(
                f"mkdir -p {shlex.quote(remote_parent)}", cwd=_REPO_DIR, timeout=30
            )
            sandbox.fs.upload_file(plan.test_code.encode("utf-8"), remote_test_path)
            sandbox.fs.upload_file(
                _PLAYWRIGHT_CONFIG.encode("utf-8"),
                posixpath.join(_REPO_DIR, ".repro-agent.playwright.config.cjs"),
            )
        except Exception as exc:
            return ExecutionResult(-1, "", f"Could not write generated test: {exc}", False, "Repository setup failed", [])

        setup = _run_stage(sandbox, "setup", setup_command or _DEFAULT_SETUP, timeout=1200)
        logs.append(("setup", setup))
        if setup.exit_code:
            return _result("Dependency setup", setup, logs)

        if start_command != "":
            app_command = start_command or _DEFAULT_START
            launch = (
                f"nohup bash -lc {shlex.quote(app_command)} "
                "> .repro-agent/app.stdout 2> .repro-agent/app.stderr & "
                "pid=$!; echo $pid > .repro-agent/app.pid; sleep 3; "
                "kill -0 $pid"
            )
            start = _run_stage(sandbox, "start", launch, timeout=30)
            logs.append(("start", start))
            if start.exit_code:
                try:
                    start.stderr += "\n" + _read_remote(sandbox, posixpath.join(_REPO_DIR, ".repro-agent/app.stderr"))
                except Exception:
                    pass
                return _result("Application start", start, logs)

        test_command = (
            f"npx playwright test {shlex.quote(test_path)} "
            "--config=.repro-agent.playwright.config.cjs --output=test-results"
        )
        test = _run_stage(sandbox, "test", test_command, timeout=600)
        logs.append(("test", test))

        # Include server output in the evidence returned to Nosana.
        if start_command != "":
            for stream in ("stdout", "stderr"):
                try:
                    value = _read_remote(sandbox, posixpath.join(_REPO_DIR, f".repro-agent/app.{stream}"))
                    logs.append(("application", _StageResult(0, value, "") if stream == "stdout" else _StageResult(0, "", value)))
                except Exception:
                    pass

        artifact_root = os.environ.get("DAYTONA_ARTIFACT_DIR")
        local_dir = Path(artifact_root) if artifact_root else Path(tempfile.mkdtemp(prefix="repro-agent-"))
        artifacts = _download_artifacts(sandbox, local_dir)
        reproduced, reason = _classify_test(test)
        completed = _result("Playwright test", test, logs, artifacts)
        completed.reproduced = reproduced
        completed.reason = reason
        return completed
    except Exception as exc:
        return ExecutionResult(-1, "", f"Daytona execution failed: {exc}", False, "Sandbox execution failed", [])
    finally:
        if sandbox is not None:
            try:
                if hasattr(sandbox, "delete"):
                    sandbox.delete()
                else:
                    _daytona.delete(sandbox, timeout=60, wait=True)
            except Exception:
                # Cleanup failure should not replace the actionable execution result.
                pass
