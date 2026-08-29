"""Reproduction test generation and refinement on Nosana.

Task 3. The model reads the issue, the repository context and the evidence from
previous attempts, and returns a Playwright reproduction hypothesis.

Nosana serves models through Ollama, which exposes an OpenAI-compatible chat
completions endpoint, so any client speaking that protocol works. Configuration
comes from the environment rather than the source, because deployment URLs are
disposable and this repository may become public.
"""

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from .models import ExecutionResult, ReproductionPlan, RepositoryContext

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

DEFAULT_MODEL = "qwen3.6:27b"

# Warm generation takes about a minute, but the first call after a deployment
# starts also waits for the model to load into VRAM.
DEFAULT_TIMEOUT = 600

# Evidence from earlier attempts, trimmed so a long log cannot crowd out the
# repository context.
MAX_EVIDENCE_CHARS = 3000

# A fenced block and its language tag. The tag is captured rather than skipped
# so a ```json block can be preferred over a ```js one.
_FENCE = re.compile(r"```([A-Za-z0-9_+-]*)[ \t]*\r?\n?(.*?)```", re.DOTALL)


class GenerationError(RuntimeError):
    """Raised when the model could not be reached or its reply was unusable."""


def _endpoint() -> str:
    base = os.environ.get("NOSANA_BASE_URL", "").strip().rstrip("/")
    if not base:
        raise GenerationError(
            "NOSANA_BASE_URL is not set. Point it at a running deployment, or "
            "pass --mock to use canned responses."
        )
    return f"{base}/v1/chat/completions"


def _load_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text()


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... truncated ...\n"


def _format_context(context: RepositoryContext) -> dict[str, str]:
    return {
        "package_json": context.package_json or "(none found)",
        "readme": context.readme or "(none found)",
        "file_tree": context.file_tree or "(empty)",
        "relevant_files": "\n\n".join(context.relevant_files) or "(none selected)",
    }


def _format_evidence(previous_results: list[ExecutionResult]) -> str:
    """Render earlier attempts as the evidence the model reasons about."""
    blocks = []
    for index, result in enumerate(previous_results, start=1):
        blocks.append(
            f"### Attempt {index}\n"
            f"Exit code: {result.exit_code}\n"
            f"Outcome: {result.reason or 'unknown'}\n\n"
            f"stdout:\n{_truncate(result.stdout, MAX_EVIDENCE_CHARS)}\n\n"
            f"stderr:\n{_truncate(result.stderr, MAX_EVIDENCE_CHARS)}"
        )
    return "\n\n".join(blocks)


def _fill(template: str, values: dict[str, str]) -> str:
    """Substitute {placeholders} without tripping over JSON braces in the text."""
    filled = template
    for key, value in values.items():
        filled = filled.replace("{" + key + "}", value)
    return filled


def _strip_reasoning(text: str) -> str:
    """Remove the thinking block that reasoning models emit before answering."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _candidates(cleaned: str) -> list[str]:
    """Payloads that might hold the plan, most promising first.

    A reply often carries more than one fenced block -- typically the test
    code first and the JSON plan second -- so every fence is a candidate,
    those labelled ``json`` ahead of the rest. The whole reply stays a
    candidate too: narrowing to a fence must never discard an object that
    sits outside it.
    """
    labelled: list[str] = []
    unlabelled: list[str] = []
    for match in _FENCE.finditer(cleaned):
        target = labelled if match.group(1).lower() == "json" else unlabelled
        target.append(match.group(2).strip())
    return [*labelled, *unlabelled, cleaned]


def extract_json(text: str) -> dict:
    """Pull a JSON object out of a model reply.

    Models wrap their output in prose, code fences, or reasoning traces even
    when told not to, so locating the object matters more than trusting the
    format.
    """
    cleaned = _strip_reasoning(text)

    saw_object = False
    failure: json.JSONDecodeError | None = None
    for candidate in _candidates(cleaned):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

        # Fall back to the outermost braces, which survives trailing commentary.
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end <= start:
            continue
        saw_object = True
        try:
            return json.loads(candidate[start : end + 1])
        except json.JSONDecodeError as exc:
            # Keep looking: a later candidate may hold the real object.
            failure = exc

    if saw_object:
        raise GenerationError(f"Model reply was not valid JSON: {failure}")
    raise GenerationError("Model reply contained no JSON object")


def _plan_from(payload: dict) -> ReproductionPlan:
    """Build a plan from a model reply, requiring the fields that matter."""
    test_code = payload.get("testCode", "").strip()
    if not test_code:
        raise GenerationError("Model reply contained no testCode")

    return ReproductionPlan(
        summary=payload.get("summary", "").strip(),
        setup_notes=payload.get("setupNotes", "").strip(),
        test_file_name=payload.get("testFileName", "reproduce.spec.js").strip(),
        test_code=test_code,
        expected_failure=payload.get("expectedFailure", "").strip(),
    )


def _complete(prompt: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Send one chat completion request and return the reply text."""
    body = json.dumps(
        {
            "model": os.environ.get("NOSANA_MODEL", DEFAULT_MODEL),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "stream": False,
        }
    ).encode()

    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("NOSANA_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(_endpoint(), data=body, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise GenerationError(
            f"Nosana returned {exc.code}: {exc.read().decode(errors='replace')[:400]}"
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise GenerationError(f"Could not reach Nosana: {exc}") from exc

    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise GenerationError(f"Unexpected response shape: {payload}") from exc


def generate_reproduction_test(
    issue: str,
    context: RepositoryContext,
    previous_results: list[ExecutionResult],
) -> ReproductionPlan:
    """Generate a reproduction plan, refining it against previous evidence."""
    values = _format_context(context)
    values["issue"] = issue

    if previous_results:
        template = _load_prompt("refine_test.md")
        values["previous_attempts"] = _format_evidence(previous_results)
    else:
        template = _load_prompt("generate_test.md")

    reply = _complete(_fill(template, values))
    return _plan_from(extract_json(reply))
