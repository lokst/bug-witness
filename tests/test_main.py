import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from src import main
from src.models import ExecutionResult, ReproductionPlan, RepositoryContext


class OrchestratorIntegrationTests(unittest.TestCase):
    def test_passes_commands_to_daytona_and_saves_attempt(self):
        plan = ReproductionPlan("demo", "", "nested/reproduce.spec.js", "test()", "failure")
        execution = ExecutionResult(1, "assertion", "", True, "bug reproduced", ["shot.png"])
        with tempfile.TemporaryDirectory() as temp, patch.object(
            main, "OUTPUT_DIR", Path(temp)
        ), patch.object(main, "gather_context", return_value=RepositoryContext()), patch.object(
            main, "generate_reproduction_test", return_value=plan
        ), patch.object(main, "run_in_daytona", return_value=execution) as execute:
            reproduced = main.run(
                "https://example.test/repo.git",
                "issue",
                1,
                setup_command="npm ci",
                start_command="npm start",
            )

            self.assertTrue(reproduced)
            execute.assert_called_once_with(
                "https://example.test/repo.git",
                plan,
                setup_command="npm ci",
                start_command="npm start",
            )
            self.assertEqual(
                (Path(temp) / "attempt-1/nested/reproduce.spec.js").read_text(),
                "test()",
            )
            saved = json.loads((Path(temp) / "attempt-1/attempt.json").read_text())
            self.assertEqual(saved["plan"]["test_code"], "test()")
            self.assertEqual(saved["result"]["stdout"], "assertion")

    def test_failed_attempt_evidence_changes_second_strategy(self):
        failed = ExecutionResult(
            1, "page loaded", "selector timed out", False, "wrong selector", ["failure.png"]
        )
        reproduced = ExecutionResult(1, "assertion", "", True, "bug reproduced")
        generated = []

        def generate(issue, context, evidence):
            generated.append(evidence.copy())
            return ReproductionPlan(
                f"attempt {len(generated)}", "", "reproduce.spec.js",
                "await page.reload()" if not evidence else "await page.getByRole('button').click()",
                "failure",
            )

        with tempfile.TemporaryDirectory() as temp, patch.object(
            main, "OUTPUT_DIR", Path(temp)
        ), patch.object(main, "gather_context", return_value=RepositoryContext()), patch.object(
            main, "generate_reproduction_test", side_effect=generate
        ), patch.object(main, "run_in_daytona", side_effect=[failed, reproduced]):
            self.assertTrue(main.run("repo", "issue", 3))

        evidence = generated[1][0]
        self.assertEqual(evidence.plan.test_code, "await page.reload()")
        self.assertEqual(evidence.result.stdout, "page loaded")
        self.assertEqual(evidence.result.stderr, "selector timed out")
        self.assertEqual(evidence.result.reason, "wrong selector")
        self.assertEqual(evidence.result.artifacts, ["failure.png"])

    def test_stops_after_max_attempts(self):
        plan = ReproductionPlan("demo", "", "reproduce.spec.js", "test()", "failure")
        failed = ExecutionResult(0, "passed", "", False, "not reproduced")
        with tempfile.TemporaryDirectory() as temp, patch.object(
            main, "OUTPUT_DIR", Path(temp)
        ), patch.object(main, "gather_context", return_value=RepositoryContext()), patch.object(
            main, "generate_reproduction_test", return_value=plan
        ) as generate, patch.object(main, "run_in_daytona", return_value=failed) as execute:
            self.assertFalse(main.run("repo", "issue", 2))
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(execute.call_count, 2)


if __name__ == "__main__":
    unittest.main()
