You are given a bug report and context about the repository it concerns.

Your task is to write a Playwright test that demonstrates the bug exists. The
test should fail when the bug is present and pass once it is fixed.

## Issue

{issue}

## Repository context

package.json:
{package_json}

README:
{readme}

File tree:
{file_tree}

## Requirements

- Use `@playwright/test`.
- Assume the application is already running and reachable at the base URL.
- Prefer role and label based selectors over CSS selectors.
- Assert the specific behaviour the issue describes, not incidental details.
- Keep the test to a single focused scenario.

## Output

Return JSON only, matching this shape:

```json
{
  "summary": "One sentence on what this test does and why it should reproduce the bug",
  "setupNotes": "Anything that must be true before the test runs",
  "testFileName": "reproduce.spec.ts",
  "testCode": "The complete Playwright test file",
  "expectedFailure": "The assertion failure you expect to see if the bug is real"
}
```
