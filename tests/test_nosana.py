import unittest

from src.models import AttemptEvidence, ExecutionResult, RepositoryContext
from src.nosana import DEMO_TEST, REFINED_DEMO_TEST, generate_reproduction_test


class DeterministicNosanaTests(unittest.TestCase):
    def test_second_attempt_materially_changes_playwright_strategy(self):
        first = generate_reproduction_test("issue", RepositoryContext(), [])
        evidence = AttemptEvidence(
            1,
            first,
            ExecutionResult(
                1,
                "page loaded",
                "timed out waiting for response",
                False,
                "Playwright could not complete",
                ["trace.zip", "failure.png"],
            ),
            ["Screenshot shows the form was submitted"],
        )
        second = generate_reproduction_test("issue", RepositoryContext(), [evidence])

        self.assertEqual(first.test_code, DEMO_TEST)
        self.assertEqual(second.test_code, REFINED_DEMO_TEST)
        self.assertNotEqual(first.test_code, second.test_code)
        self.assertIn("waitForResponse", second.test_code)
        self.assertIn("Playwright could not complete", second.summary)

    def test_prompt_data_contains_full_evidence_and_optional_notes(self):
        first = generate_reproduction_test("issue", RepositoryContext(), [])
        evidence = AttemptEvidence(
            1,
            first,
            ExecutionResult(2, "stdout", "stderr", False, "setup failed", ["trace.zip"]),
            ["Screenshot shows login page"],
        ).as_prompt_data()

        self.assertEqual(evidence["plan"]["test_code"], DEMO_TEST)
        self.assertEqual(evidence["result"]["stdout"], "stdout")
        self.assertEqual(evidence["result"]["stderr"], "stderr")
        self.assertEqual(evidence["result"]["reason"], "setup failed")
        self.assertEqual(evidence["result"]["artifacts"], ["trace.zip"])
        self.assertEqual(evidence["artifactNotes"], ["Screenshot shows login page"])


if __name__ == "__main__":
    unittest.main()
