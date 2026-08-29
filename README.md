# Bug Reproduction Agent

Turns a natural-language bug report into a deterministic failing test.

Given a repository and an issue, the agent asks a model to hypothesise how the
bug might be reproduced, runs that hypothesis in an isolated sandbox, and feeds
the resulting evidence back so the model can try again. It stops when the bug
reproduces or the attempt limit is reached.

- **Nosana** does the reasoning: reading the issue and generating or refining a
  Playwright reproduction test.
- **Daytona** does the execution: cloning the repository, starting the app,
  running the test, and capturing the output.

The artifact at the end is a failing regression test an engineer can work from.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Provide `DAYTONA_API_KEY` in the environment or in an ignored project-root
`.env` file. `DAYTONA_API_URL` and `DAYTONA_TARGET` are optional.

## Usage

```bash
python -m src.main --repo <repo-url> --issue issue.txt
```

Options:

- `--repo` — GitHub repository URL
- `--issue` — path to a file containing the issue text
- `--max-attempts` — how many reproduction strategies to try (default 3)
- `--setup-command` — override dependency/setup commands
- `--start-command` — override the application start command

Each attempt is written to `outputs/attempt-N/`, containing the generated test,
the plan, captured stdout and stderr, and `attempt.json`, which pairs the full
generated plan with the classified execution result and artifact paths. Failed
attempts are passed back as evidence before the next strategy is generated.

## Selected demo

The Daytona execution layer is live. Until the Nosana provider is finalized,
the deterministic generator emits the selected YesFundMe reproduction from
`TASK1_DEMO.md`. Its retry path is evidence-aware and materially changes the
second Playwright strategy, but it does not yet call a live Nosana transport.

```bash
python -m src.main \
  --repo https://github.com/Gauntlet-HQ/yes-build-me.git \
  --issue task1_fixture/issue.txt \
  --max-attempts 1 \
  --setup-command "git fetch --depth 1 origin 079886d51a871b2c4e43377a1a33e456d93cdd91 && git checkout 079886d51a871b2c4e43377a1a33e456d93cdd91 && npm ci && npm run seed && npm install --no-save --package-lock=false @playwright/test@1.62.1 && npx playwright install --with-deps chromium" \
  --start-command "npm run dev"
```

The command should exit successfully after classifying the expected failing
Playwright assertion as a reproduced product bug.

For an offline demo, `task1_fixture/known_daytona_run.txt`,
`mock_execution_result.json`, and `known_failure.png` preserve evidence from a
successful live Daytona run.

## Layout

```text
src/
  main.py        CLI and the reproduction loop
  models.py      Shared data models
  nosana.py      Test generation and refinement
  daytona.py     Sandbox execution
  context.py     Repository context gathering
  classifier.py  Reproduced vs not reproduced
prompts/
  generate_test.md
  refine_test.md
```
