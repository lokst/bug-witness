# Bug Reproduction Agent — Daytona + Nosana

## Concept

Build an agent that takes a natural-language bug report or GitHub issue and automatically determines whether the bug can be reproduced.

The core idea is to give **Nosana** and **Daytona** clear, complementary roles:

- **Nosana = AI reasoning and test generation**
- **Daytona = isolated execution and verification**

The end result is a deterministic reproduction test that proves whether the reported bug exists.

---

## User Flow

1. A user provides a GitHub repository and issue.
2. The agent sends the issue, relevant code, and application context to a model running on **Nosana**.
3. The model generates a **bug reproduction strategy**, such as:
   - setup instructions;
   - actions to perform;
   - expected behaviour;
   - failure conditions;
   - Playwright test code and assertions.
4. A **Daytona sandbox** is created for the repository.
5. Inside Daytona, the system:
   - clones the repository;
   - installs dependencies;
   - starts the application;
   - executes the generated reproduction test.
6. The result is collected:
   - test output;
   - browser console logs;
   - screenshots;
   - application logs;
   - stack traces.
7. If the bug is not reproduced, the evidence is returned to the model on **Nosana**.
8. Nosana reasons about why the reproduction failed and generates an improved reproduction strategy.
9. Daytona executes the new attempt.
10. The loop continues until:
    - the bug is successfully reproduced; or
    - the agent concludes that it cannot reproduce the issue within the configured attempt limit.

---

## Architecture

```text
                    GitHub Issue
                         |
                         v
                 +----------------+
                 |  Orchestrator  |
                 +----------------+
                    |          ^
                    |          |
          issue + code         | results / evidence
                    |          |
                    v          |
             +--------------+  |
             |    Nosana    |  |
             |              |  |
             | AI reasoning |  |
             | Generate /   |  |
             | refine test  |  |
             +--------------+  |
                    |          |
              reproduction     |
              test / plan      |
                    |          |
                    v          |
             +--------------+  |
             |   Daytona    |--+
             |   Sandbox    |
             |              |
             | Clone repo   |
             | Run app      |
             | Run browser  |
             | Run tests    |
             +--------------+
                    |
                    v
             Reproduced?
              /       \
            Yes       No
             |         |
             v         +----> feedback to Nosana
      Reproduction
      confirmed
```

---

## Why Nosana Is Necessary

Nosana is not simply used as generic model hosting.

Its role is the **reasoning engine for reproduction**.

The model has to interpret an imperfect human-written bug report and turn it into an executable hypothesis:

> "Given this issue description and this codebase, what sequence of actions would demonstrate that this bug actually exists?"

After each unsuccessful execution, the model receives real-world evidence and adjusts its hypothesis.

For example:

### Attempt 1

Issue:

> Clicking "Save" after changing a user's role sometimes leaves the old role visible.

Nosana generates:

```text
1. Login as administrator.
2. Open Users.
3. Select a user.
4. Change role from Viewer to Editor.
5. Click Save.
6. Reload the page.
7. Assert that "Editor" is displayed.
```

Daytona executes it.

Result:

```text
PASS — could not reproduce.
```

Nosana receives the evidence and reasons:

> The issue may depend on navigation rather than a full reload. Try returning to the users list immediately after saving.

It generates Attempt 2.

Daytona executes it.

```text
FAIL

Expected: Editor
Received: Viewer
```

The bug has now been reproduced.

---

## Why Daytona Is Necessary

The generated reproduction procedure must actually be executed against the software.

Daytona provides a disposable, isolated environment where the agent can safely:

- clone arbitrary repositories;
- install dependencies;
- run application servers;
- run Playwright/browser automation;
- execute generated code;
- capture logs and screenshots;
- destroy the environment afterwards.

This separation is important:

> **Nosana proposes what should reproduce the bug. Daytona proves whether it does.**

---

## The Agent Loop

The loop can live in a lightweight orchestrator rather than inside a Daytona instance.

```python
for attempt in range(MAX_ATTEMPTS):

    reproduction_test = nosana.generate_test(
        issue=issue,
        repository_context=context,
        previous_results=results,
    )

    result = daytona.run(
        repository=repo,
        test=reproduction_test,
    )

    if result.reproduced:
        return confirmed_bug(result)

    results.append(result)
```

This keeps the architecture clean:

```text
Orchestrator
   |
   +----> Nosana: Think
   |
   +----> Daytona: Execute
   |
   +----> Nosana: Reflect
   |
   +----> Daytona: Execute again
```

---

## Hackathon MVP

For a five-hour hackathon, keep the scope narrow.

### Input

- GitHub repository
- GitHub issue text

### Nosana

Generate or refine a Playwright reproduction test.

### Daytona

- clone repository;
- start application;
- run Playwright;
- capture output and screenshots.

### Output

Either:

```text
✅ BUG REPRODUCED
Attempt: 2/3

Expected:
Role = Editor

Observed:
Role = Viewer

Reproduction test:
tests/reproduce-123.spec.ts
```

or:

```text
⚠️ UNABLE TO REPRODUCE
3 reproduction strategies attempted.
```

---

## Demo Story

The demo should focus on one simple transformation:

> **Natural-language bug report → reproducible automated test**

### 1. Show the issue

> "Users report that changing someone's role occasionally appears not to save."

### 2. Start the agent

Explain:

> "Nosana reads the issue and generates a hypothesis for how to reproduce it."

### 3. Show Daytona

A fresh sandbox starts, the repository is cloned, and the generated Playwright test runs.

### 4. First attempt fails to reproduce

This is actually useful for the demo.

Show that the system feeds the evidence back into Nosana.

### 5. Nosana revises the test

A second reproduction strategy is generated automatically.

### 6. Daytona executes it

```text
❌ Assertion failed

Expected: Editor
Actual: Viewer
```

### 7. Reveal

> "We've converted an ambiguous GitHub issue into a deterministic failing test."

That failing test is now something an engineer — or another coding agent — can work from.

---

## Possible Extension: From Reproduction to Repair

If the reproduction agent works early enough, the next stage is straightforward:

```text
Issue
  ↓
Nosana
Generate reproduction
  ↓
Daytona
Confirm failure
  ↓
Nosana
Generate candidate fix
  ↓
Daytona
Apply patch + rerun reproduction
  ↓
Fail → iterate
Pass → verified patch
```

However, **bug reproduction alone is already a complete hackathon use case**.

It has a very clear division of responsibilities:

> **Nosana understands the bug.  
> Daytona tries to make it happen.**

And it produces a valuable engineering artifact at the end:

> **A deterministic failing regression test.**
