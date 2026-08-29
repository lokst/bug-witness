# Hackathon Task Breakdown — Bug Reproduction Agent

## Goal

Build a working MVP that turns a natural-language GitHub issue into an automated reproduction attempt using:

- **Nosana** for AI reasoning and Playwright test generation
- **Daytona** for isolated repository setup and test execution

The demo should show:

```text
GitHub issue → generated reproduction test → sandbox execution → reproduced / unable to reproduce result
```

---

## MVP Scope

### Inputs

- GitHub repository URL
- GitHub issue text or issue URL
- Optional setup command
- Optional app start command

### Outputs

- Reproduction status
- Attempt count
- Generated Playwright test
- Test output
- Logs/screenshots if available

### Hard Limit

Keep the first version focused on **one repository type**, ideally a simple JavaScript/TypeScript web app that can run with npm.

---

## Task 1 — Define the Demo Repository and Bug

**Owner:** Person 2

### Steps

1. Pick a small web app repository.
2. Confirm it can run locally.
3. Identify or create a simple bug scenario.
4. Write a natural-language issue description.
5. Define the expected failing assertion.

### Deliverable

A demo issue like:

```text
When changing a user's role from Viewer to Editor and returning to the users list, the old role is still displayed.
```

### Done When

- The repo can be cloned and started.
- The bug can be manually demonstrated or simulated.

---

## Task 2 — Create the Python Orchestrator Skeleton

**Owner:** Person 1

### Steps

1. Create a small Python CLI app.
2. Accept input:
   - repo URL
   - issue text
   - max attempts
3. Add a main loop:

```python
for attempt in range(MAX_ATTEMPTS):
    test = generate_reproduction_test(issue, previous_results)
    result = run_in_daytona(repo, test)
    if result.reproduced:
        break
```

4. Store every attempt in an output folder.

### Deliverable

A CLI command like:

```bash
python -m src.main --repo <repo-url> --issue issue.txt
```

### Done When

- The loop runs with mocked Nosana and mocked Daytona functions.

---

## Task 3 — Build the Nosana Test Generation Step

**Owner:** Person 1

### Steps

1. Create a prompt that asks the model to generate a Playwright test.
2. Include:
   - issue text
   - repository context
   - previous attempt results
3. Require structured output:

```json
{
  "summary": "...",
  "setupNotes": "...",
  "testFileName": "reproduce.spec.ts",
  "testCode": "...",
  "expectedFailure": "..."
}
```

4. Add retry/refinement prompt for failed attempts.

### Deliverable

A Python function:

```python
def generate_reproduction_test(
    issue: str,
    context: RepositoryContext,
    previous_results: list[ExecutionResult],
) -> ReproductionPlan:
    ...
```

### Done When

- Given an issue, the model returns valid Playwright test code.
- On failed reproduction, it can generate a modified second attempt.

---

## Task 4 — Gather Repository Context

**Owner:** Person 1

### Steps

1. Clone or inspect the repository.
2. Collect useful files:
   - `package.json`
   - README
   - existing tests
   - relevant source files
3. Keep context small enough for the model.
4. Summarize the project structure.

### Deliverable

A context object:

```json
{
  "packageJson": "...",
  "readme": "...",
  "fileTree": "...",
  "relevantFiles": []
}
```

### Done When

- Nosana receives enough repo information to generate a plausible Playwright test.

---

## Task 5 — Integrate Daytona Sandbox Execution

**Owner:** Person 2

### Steps

1. Create a Daytona sandbox.
2. Clone the target repository inside it.
3. Install dependencies.
4. Write the generated Playwright test into the repo.
5. Start the application.
6. Run Playwright.
7. Capture:
   - stdout
   - stderr
   - exit code
   - screenshots/videos if available

### Deliverable

A Python function:

```python
def run_in_daytona(
    repo_url: str,
    plan: ReproductionPlan,
    setup_command: str | None = None,
    start_command: str | None = None,
) -> ExecutionResult:
    ...
```

### Done When

- A generated Playwright test can be executed in a clean sandbox.
- The result is returned to the orchestrator.

---

## Task 6 — Determine Reproduced vs Not Reproduced

**Owner:** Person 2

### Steps

1. Treat a failing Playwright assertion as potential reproduction.
2. Distinguish between:
   - app setup failure
   - dependency failure
   - test syntax failure
   - actual bug reproduction
3. Return a structured result:

```json
{
  "reproduced": true,
  "reason": "Assertion failed: expected Editor, received Viewer",
  "exitCode": 1,
  "logs": "..."
}
```

### Deliverable

A result classifier.

### Done When

- The orchestrator can decide whether to stop or retry.

---

## Task 7 — Implement the Retry Loop

**Owner:** Person 1, with both people integrating

### Steps

1. Feed unsuccessful results back into Nosana.
2. Include:
   - previous generated test
   - stdout/stderr
   - screenshots/log notes
   - reason attempt failed
3. Generate a revised reproduction test.
4. Repeat up to `MAX_ATTEMPTS`.

### Deliverable

A working multi-attempt flow.

### Done When

- Attempt 2 can differ from Attempt 1 based on execution evidence.

---

## Task 8 — Build the Demo Output

**Owner:** Person 1

### Steps

1. Print a clear terminal summary.
2. Save generated tests to an output directory.
3. Save logs per attempt.
4. Show final status.

### Example Output

```text
✅ BUG REPRODUCED
Attempt: 2/3

Expected:
Role = Editor

Observed:
Role = Viewer

Generated test:
outputs/attempt-2/reproduce.spec.ts
```

### Done When

- Judges can understand what happened without reading raw logs.

---

## Task 9 — Prepare Fallback Demo Path

**Owner:** Person 2

### Steps

1. Record or save a known successful run.
2. Keep a local fixture repo if live cloning fails.
3. Keep generated test examples ready.
4. Have mocked Nosana/Daytona responses available.

### Deliverable

A reliable backup demo.

### Done When

- The team can demo even if APIs or sandboxes fail.

---

## Two-Person Parallel Work Plan

Define the shared models in `src/models.py` before splitting up:

```python
from dataclasses import dataclass, field


@dataclass
class RepositoryContext:
    package_json: str = ""
    readme: str = ""
    file_tree: str = ""
    relevant_files: list[str] = field(default_factory=list)


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
```

This allows both people to work in parallel:

- **Person 1** mocks `run_in_daytona()` while building Tasks 2, 3, 4, 7, and 8.
- **Person 2** uses a hard-coded `ReproductionPlan` while building Tasks 1, 5, 6, and 9.
- Avoid waiting for the other integration until Hour 4.

## Suggested 5-Hour Schedule

### Hour 1 — Parallel Foundations

**Person 1**

- Create the Python project, shared models, and CLI.
- Build the orchestrator against mocked Nosana and Daytona functions.

**Person 2**

- Pick and verify the repository and bug.
- Document exact clone, install, start, and test commands.
- Write a hand-crafted Playwright reproduction test.

Person 2 should share the selected issue and commands as soon as they are ready.

### Hours 2–3 — Parallel Integrations

**Person 1**

- Gather repository context.
- Implement Nosana generation and refinement prompts.
- Save each mocked attempt to the output directory.

**Person 2**

- Create the Daytona sandbox flow.
- Clone the repository, install dependencies, and start the app.
- Run the hand-crafted Playwright test.
- Implement result classification using real and sample logs.

### Hour 4 — Integrate Together

Connect the complete flow:

```text
Issue → repository context → Nosana plan → Daytona execution
      → result classification → evidence-based retry
```

Prioritize one working retry over additional features.

### Hour 5 — Polish and Fallback

**Person 1**

- Improve terminal output and save final artifacts.

**Person 2**

- Save a known-good run, fixture repository, and mocked responses.

**Both**

- Rehearse the demo and fix integration issues.

---

## Priority Order

If time is short, build in this order:

1. Manual issue input
2. Nosana generates Playwright test
3. Daytona runs generated test
4. Capture pass/fail output
5. Retry once with evidence
6. Pretty final summary

Do **not** spend early time on:

- Full GitHub OAuth
- Supporting many languages/frameworks
- Complex UI
- Automatic issue scraping
- Auto-repairing the bug

---

## Minimal File Structure

```text
bug-reproduction-agent/
  src/
    __init__.py
    main.py
    models.py
    nosana.py
    daytona.py
    context.py
    classifier.py
  prompts/
    generate_test.md
    refine_test.md
  outputs/
    attempt-1/
    attempt-2/
  requirements.txt
  README.md
```

---

## Final Demo Script

1. Show the GitHub issue.
2. Run the agent.
3. Explain that Nosana generates the reproduction hypothesis.
4. Show Daytona creating a clean sandbox and running the app.
5. Show Attempt 1 result.
6. Show Nosana refining the test.
7. Show Attempt 2 reproducing the bug.
8. End with the generated failing Playwright test.

---

## Success Criteria

The hackathon project succeeds if it can show:

- A natural-language bug report as input
- AI-generated reproduction test
- Real sandbox execution
- Evidence-based retry
- Final reproduced/unreproduced result
