"""Classify a sandbox run as reproduction, or as a failure to get that far.

Task 6. The execution layer reports which pipeline stage a run reached and the
raw Playwright streams; this module decides what that evidence means:

* runs that never reached Playwright (sandbox, repository, setup, start) are
  never reproductions and keep the stage-specific reason they arrived with;
* a passing Playwright run did not reproduce the bug;
* recognised test-infrastructure failures (syntax, missing browser, navigation
  or timeout errors) are not reproductions;
* an assertion failure counts as a reproduction only when it is the plan's
  own bug assertion, so an incidental assertion (a login precondition, an
  unrelated status code) cannot stop the retry loop.

Two signals tie a failed assertion to the plan. Playwright reports where the
failure happened (a ``> 34 |`` code frame and ``file.js:33:5`` stack frames),
and the generated test's final ``expect(...)`` is by construction the one that
encodes the bug, so a failure located inside it is a reproduction and one
located before it is not. When no location can be read, distinctive words from
the plan's ``expected_failure`` are looked for in the output instead.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import replace

from .models import ExecutionResult, ReproductionPlan

_ASSERTION_MARKERS = (
    "assertionerror",
    "expect(received)",
    "expect(locator)",
    "expect(page)",
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

# Words that appear in nearly every expected-failure description or Playwright
# report and therefore say nothing about *which* assertion failed.
_STOPWORDS = frozenset(
    """
    the and but not nor for from into with that this then than when there
    these those been being are was were will would should could does did
    has have had its itself instead still also only just very
    expect expected expects receive received actual actually assertion
    assert asserts fail fails failed failure error errors test tests page
    element elements value values shown show shows display displays
    displayed render renders rendered appear appears text
    """.split()
)
_SECTION = re.compile(r"^===== (\S+) (stdout|stderr) =====$", re.MULTILINE)


def _test_stage_output(result: ExecutionResult) -> str:
    """Return the Playwright streams, excluding earlier stages' output.

    The Daytona runner concatenates every stage's streams under
    ``===== <stage> <stream> =====`` headers so the model sees all evidence.
    Setup logs can legitimately contain words like ``SyntaxError`` or
    ``expected:``, so only the ``test`` sections are examined when present.
    """
    sections: list[str] = []
    for text in (result.stdout, result.stderr):
        matches = list(_SECTION.finditer(text))
        for index, match in enumerate(matches):
            if match.group(1) != "test":
                continue
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            sections.append(text[match.end() : end])
    if sections:
        return "\n".join(sections)
    return f"{result.stdout}\n{result.stderr}"


def _final_assertion_lines(test_code: str) -> range | None:
    """Return the 1-based line span of the last ``expect(`` statement."""
    lines = test_code.splitlines()
    starts = [number for number, line in enumerate(lines, 1) if "expect(" in line]
    if not starts:
        return None
    start = starts[-1]
    end = next(
        (number for number in range(start, len(lines) + 1) if ";" in lines[number - 1]),
        len(lines),
    )
    return range(start, end + 1)


def _failing_lines(output: str, test_file_name: str) -> set[int]:
    """Line numbers Playwright's report attributes the failure to.

    These come from the ``> 29 |`` code frame and ``at .../file.js:28:5``
    stack frames.  The ``1) file.js:3:1 › title`` header names where the test
    *starts*, not where it failed, so it is deliberately not matched.
    """
    lines = {int(m.group(1)) for m in re.finditer(r"^\s*>\s*(\d+)\s*\|", output, re.MULTILINE)}
    basename = posixpath.basename(test_file_name or "")
    if basename:
        pattern = r"\bat\s+\S*" + re.escape(basename.lower()) + r":(\d+):\d+"
        lines |= {int(m.group(1)) for m in re.finditer(pattern, output)}
    return lines


def _error_detail(output: str) -> str:
    """The first Playwright ``Error:`` line, plus what it was waiting for.

    This is the one line a reader (or the model refining the next attempt)
    needs, and it survives even when the full streams are truncated.
    """
    error = re.search(r"^\s*Error: (.+?)\s*$", output, re.MULTILINE)
    if not error:
        return ""
    detail = error.group(1)
    waiting = re.search(r"^\s*- (waiting for .+?)\s*$", output, re.MULTILINE)
    if waiting:
        detail += f" ({waiting.group(1)})"
    return detail


def _keywords(expected_failure: str) -> list[str]:
    seen: list[str] = []
    for token in re.findall(r"[a-z0-9]{3,}", (expected_failure or "").lower()):
        if token not in _STOPWORDS and token not in seen:
            seen.append(token)
    return seen


def _matches_expected_failure(output: str, expected_failure: str) -> tuple[list[str], list[str]]:
    """Return ``(matched, keywords)`` for the plan's expected failure.

    Distinctive words from the expected failure are looked for in the
    Playwright output. Substring matching lets ``visible`` match
    ``toBeVisible`` and ``editor`` match ``"Editor"``.
    """
    keywords = _keywords(expected_failure)
    matched = [word for word in keywords if word in output]
    return matched, keywords


def classify(result: ExecutionResult, plan: ReproductionPlan) -> ExecutionResult:
    """Decide whether a run actually reproduced the bug described by ``plan``.

    Returns a new :class:`ExecutionResult`; the input is not mutated.
    """
    if result.stage != "test":
        return replace(result, reproduced=False)

    if result.exit_code == 0:
        return replace(
            result, reproduced=False, reason="Playwright passed; the reported bug was not reproduced"
        )

    raw_output = _test_stage_output(result)
    output = raw_output.lower()
    if any(marker in output for marker in _INFRASTRUCTURE_MARKERS):
        detail = _error_detail(raw_output)
        return replace(
            result,
            reproduced=False,
            reason="Playwright could not complete due to a test or browser failure"
            + (f": {detail}" if detail else ""),
        )
    if not any(marker in output for marker in _ASSERTION_MARKERS):
        return replace(
            result,
            reproduced=False,
            reason="Playwright failed, but no assertion failure proved the reported bug",
        )

    final = _final_assertion_lines(plan.test_code or "")
    failing = _failing_lines(output, plan.test_file_name)
    if final and failing:
        hits = sorted(failing & set(final))
        if hits:
            return replace(
                result,
                reproduced=True,
                reason=(
                    f"Playwright failed at the plan's final assertion (line {hits[0]}); "
                    "bug reproduced"
                ),
            )
        return replace(
            result,
            reproduced=False,
            reason=(
                f"Playwright failed at line {min(failing)}, before the plan's final "
                f"assertion (lines {final.start}-{final.stop - 1}); precondition or "
                "unrelated assertion, not a reproduction"
            ),
        )

    matched, keywords = _matches_expected_failure(output, plan.expected_failure)
    if not keywords:
        return replace(
            result,
            reproduced=False,
            reason="Playwright assertion failed, but the plan has no expected failure to verify it against",
        )
    # Two distinctive words in common is enough to tie the assertion to the
    # plan; a one- or two-word expectation must match completely.
    if len(matched) >= min(2, len(keywords)):
        return replace(
            result,
            reproduced=True,
            reason=(
                "Playwright assertion failed as expected "
                f"(matched: {', '.join(matched)}); bug reproduced"
            ),
        )
    return replace(
        result,
        reproduced=False,
        reason=(
            "Playwright assertion failed, but it does not match the expected failure "
            f"(looked for: {', '.join(keywords)})"
        ),
    )
