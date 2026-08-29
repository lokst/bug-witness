A previous attempt to reproduce this bug did not succeed. Use the evidence from
that run to form a better hypothesis.

## Issue

{issue}

## Repository context

File tree:
{file_tree}

## Previous attempts

{previous_attempts}

## How to think about this

The test not failing does not mean the bug is absent. More often the test
missed the conditions the bug depends on. Consider:

- Did the test exercise the path the reporter actually described?
- Does the bug depend on navigation rather than a full reload, or the reverse?
- Does it need particular state, timing, or a second interaction to surface?
- If the test passed, does the bug require a condition that did not occur?
  An issue conditional on a failure, an error state, or unusual data will not
  reproduce against a healthy application, so the test may have to create that
  condition itself. Intercepting a network request and returning an error
  response is one way to do this.
- Did the run fail before reaching the assertion, because of setup, missing
  dependencies, or a bad selector? If so, fix that rather than changing the
  hypothesis.

## Requirements

- Change the reproduction strategy in a way the evidence justifies.
- Explain the change in the summary field.
- Keep everything else as constrained as the first attempt.

## Output

Return JSON only, matching this shape:

```json
{
  "summary": "What you changed and why the evidence points there",
  "setupNotes": "Anything that must be true before the test runs",
  "testFileName": "reproduce.spec.ts",
  "testCode": "The complete Playwright test file",
  "expectedFailure": "The assertion failure you expect to see if the bug is real"
}
```
