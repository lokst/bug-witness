import json
import unittest
from pathlib import Path

from src import mocks
from src.classifier import classify
from src.models import ExecutionResult, ReproductionPlan

PLAN = ReproductionPlan(
    summary="stale role",
    setup_notes="",
    test_file_name="tests/reproduce.spec.ts",
    test_code="",
    expected_failure="expected Editor, received Viewer",
)

MATCHING_ASSERTION = (
    "Error: expect(received).toBe(expected)\n"
    "Expected: \"Editor\"\nReceived: \"Viewer\"\n"
    "  at tests/reproduce.spec.ts:12:5"
)
UNRELATED_ASSERTION = (
    "Error: expect(received).toBe(expected)\n"
    "Expected: 200\nReceived: 500\n"
    "  at tests/reproduce.spec.ts:4:5"
)


# Line 4 is a login precondition; the bug assertion spans lines 6-8.
LOCATED_TEST = """\
const { test, expect } = require('@playwright/test');

test('shows the API error', async ({ page }) => {
  await expect(page).toHaveURL(/dashboard/);
  await page.getByRole('button', { name: 'Create' }).click();
  await expect(
    page.getByText('Service temporarily unavailable'),
  ).toBeVisible();
});
"""
LOCATED_PLAN = ReproductionPlan(
    summary="",
    setup_notes="",
    test_file_name="reproduce.spec.js",
    test_code=LOCATED_TEST,
    expected_failure="Nothing happens.",
)


def make_result(exit_code, stdout, stderr="", stage="test"):
    return ExecutionResult(exit_code, stdout, stderr, stage=stage)


class ClassifierTests(unittest.TestCase):
    def test_passing_playwright_run_is_not_reproduced(self):
        result = classify(make_result(0, "1 passed"), PLAN)

        self.assertFalse(result.reproduced)
        self.assertIn("passed", result.reason)

    def test_syntax_error_is_infrastructure_failure(self):
        result = classify(make_result(1, "SyntaxError: unexpected token"), PLAN)

        self.assertFalse(result.reproduced)
        self.assertIn("could not complete", result.reason)

    def test_missing_browser_is_infrastructure_failure(self):
        result = classify(
            make_result(1, "", "browserType.launch: Executable doesn't exist"), PLAN
        )

        self.assertFalse(result.reproduced)
        self.assertIn("could not complete", result.reason)

    def test_infrastructure_reason_carries_the_playwright_error_detail(self):
        stdout = (
            "    Test timeout of 30000ms exceeded.\n"
            "    Error: locator.click: Test timeout of 30000ms exceeded.\n"
            "    Call log:\n"
            "      - waiting for getByRole('button', { name: /login/i })\n"
        )
        result = classify(make_result(1, stdout), PLAN)

        self.assertFalse(result.reproduced)
        self.assertIn("locator.click: Test timeout of 30000ms exceeded", result.reason)
        self.assertIn("waiting for getByRole('button', { name: /login/i })", result.reason)

    def test_failure_without_assertion_is_not_reproduced(self):
        result = classify(make_result(1, "Error: something else went wrong"), PLAN)

        self.assertFalse(result.reproduced)
        self.assertIn("no assertion", result.reason)

    def test_assertion_matching_expected_failure_is_reproduced(self):
        result = classify(make_result(1, MATCHING_ASSERTION), PLAN)

        self.assertTrue(result.reproduced)
        self.assertIn("bug reproduced", result.reason)

    def test_unrelated_assertion_is_not_reproduced(self):
        result = classify(make_result(1, UNRELATED_ASSERTION), PLAN)

        self.assertFalse(result.reproduced)
        self.assertIn("does not match", result.reason)

    def test_assertion_cannot_be_verified_without_expected_failure(self):
        plan = ReproductionPlan("", "", "reproduce.spec.ts", "", "")
        result = classify(make_result(1, MATCHING_ASSERTION), plan)

        self.assertFalse(result.reproduced)
        self.assertIn("no expected failure", result.reason)

    def test_earlier_stage_failures_keep_their_reason_and_never_reproduce(self):
        original = ExecutionResult(
            127, "", "npm: not found", reason="Dependency setup failed with exit code 127", stage="setup"
        )
        result = classify(original, PLAN)

        self.assertFalse(result.reproduced)
        self.assertEqual(result.reason, "Dependency setup failed with exit code 127")

    def test_only_the_test_section_of_combined_output_is_examined(self):
        stdout = (
            "===== setup stdout =====\nnpm WARN SyntaxError in optional dependency\n"
            f"===== test stdout =====\n{MATCHING_ASSERTION}"
        )
        result = classify(make_result(1, stdout), PLAN)

        self.assertTrue(result.reproduced)

    def test_classify_returns_a_new_result_without_mutating_input(self):
        original = make_result(1, MATCHING_ASSERTION)
        result = classify(original, PLAN)

        self.assertTrue(result.reproduced)
        self.assertFalse(original.reproduced)

    def test_failure_at_the_final_assertion_is_reproduced_despite_vague_expected_failure(self):
        stdout = (
            "  1) reproduce.spec.js:3:1 › shows the API error\n\n"
            "    Error: expect(locator).toBeVisible() failed\n\n"
            "    Locator: getByText('Service temporarily unavailable')\n"
            "    Expected: visible\n    Received: element(s) not found\n\n"
            "       6 |   await expect(\n"
            "    >  7 |     page.getByText('Service temporarily unavailable'),\n"
            "         |     ^\n"
            "       8 |   ).toBeVisible();\n"
        )
        result = classify(make_result(1, stdout), LOCATED_PLAN)

        self.assertTrue(result.reproduced)
        self.assertIn("final assertion", result.reason)

    def test_failure_at_a_precondition_assertion_is_not_reproduced_despite_matching_words(self):
        stdout = (
            "  1) reproduce.spec.js:3:1 › shows the API error\n\n"
            "    Error: expect(page).toHaveURL(expected) failed\n\n"
            "    Expected pattern: /dashboard/\n    Received string: \"http://localhost:5173/login\"\n\n"
            "    >  4 |   await expect(page).toHaveURL(/dashboard/);\n"
            "         |                      ^\n"
            "        at /home/daytona/repo/reproduce.spec.js:4:22\n"
        )
        plan = ReproductionPlan("", "", "reproduce.spec.js", LOCATED_TEST, "expected dashboard, received login")
        result = classify(make_result(1, stdout), plan)

        self.assertFalse(result.reproduced)
        self.assertIn("before the plan's final assertion", result.reason)

    def test_canned_mock_attempts_classify_like_a_real_run(self):
        first_plan = mocks.generate_reproduction_test("", None, [])
        first = classify(mocks.run_in_daytona("", first_plan), first_plan)
        second_plan = mocks.generate_reproduction_test("", None, [first])
        second = classify(mocks.run_in_daytona("", second_plan), second_plan)

        self.assertFalse(first.reproduced)
        self.assertTrue(second.reproduced)

    def test_demo_fixture_output_matches_demo_test_and_expected_failure(self):
        root = Path(__file__).parent.parent
        fixture = json.loads((root / "task1_fixture/mock_execution_result.json").read_text())
        plan = ReproductionPlan(
            summary="",
            setup_notes="",
            test_file_name="reproduce.spec.js",
            test_code=(root / "task1_fixture/reproduce.spec.js").read_text(),
            expected_failure=(
                "Service temporarily unavailable should be visible, but the element "
                "is not rendered."
            ),
        )
        result = classify(
            make_result(fixture["exit_code"], fixture["stdout"], fixture["stderr"]), plan
        )

        self.assertTrue(result.reproduced)

if __name__ == "__main__":
    unittest.main()
