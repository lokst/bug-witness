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

## Usage

```bash
python -m src.main --repo <repo-url> --issue issue.txt
```

Options:

- `--repo` — GitHub repository URL
- `--issue` — path to a file containing the issue text
- `--max-attempts` — how many reproduction strategies to try (default 3)

Each attempt is written to `outputs/attempt-N/`, containing the generated test,
the plan, and the captured stdout and stderr.

## Status

The reasoning and execution layers are currently mocked, so the loop runs end
to end without external services. The first attempt does not reproduce the bug
and the second one does, which exercises the evidence-based retry path.

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
