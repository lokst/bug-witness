import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import main
from src.models import ExecutionResult, ReproductionPlan, RepositoryContext
from src.nosana import GenerationError


class OrchestratorIntegrationTests(unittest.TestCase):
    def test_passes_commands_to_daytona_and_saves_attempt(self):
        plan = ReproductionPlan(
            "demo", "", "nested/reproduce.spec.js", "test()", "expected Editor, received Viewer"
        )
        execution = ExecutionResult(
            1,
            'Error: expect(received).toBe(expected)\nExpected: "Editor"\nReceived: "Viewer"',
            "",
            artifacts=["shot.png"],
            stage="test",
        )
        with tempfile.TemporaryDirectory() as temp, patch.object(
            main, "OUTPUT_DIR", Path(temp)
        ), patch.object(main, "gather_context", return_value=RepositoryContext()), patch.object(
            main, "generate_reproduction_test", return_value=plan
        ), patch.object(main, "run_in_daytona", return_value=execution) as execute:
            reproduced = main.run(
                "https://example.test/repo.git",
                "issue",
                1,
                ref="079886d",
                setup_command="npm ci",
                start_command="npm start",
            )

            self.assertTrue(reproduced)
            execute.assert_called_once_with(
                "https://example.test/repo.git",
                plan,
                setup_command="npm ci",
                start_command="npm start",
                ref="079886d",
            )
            self.assertEqual(
                (Path(temp) / "attempt-1/nested/reproduce.spec.js").read_text(),
                "test()",
            )

    def test_generation_failure_costs_one_attempt_not_the_whole_run(self):
        """An unusable model reply must not abort the remaining attempts."""
        plan = ReproductionPlan("demo", "", "reproduce.spec.js", "test()", "boom")
        execution = ExecutionResult(1, "Error: expect(received).toBe(expected)\nboom", "", stage="test")

        with tempfile.TemporaryDirectory() as temp, patch.object(
            main, "OUTPUT_DIR", Path(temp)
        ), patch.object(main, "gather_context", return_value=RepositoryContext()), patch.object(
            main,
            "generate_reproduction_test",
            side_effect=[GenerationError("Model reply contained no JSON object"), plan],
        ) as generate, patch.object(main, "run_in_daytona", return_value=execution):
            reproduced = main.run("https://example.test/repo.git", "issue", 2)

            self.assertTrue(reproduced)
            self.assertEqual(generate.call_count, 2)
            # The failure is handed to the next attempt as evidence.
            evidence = generate.call_args_list[1].args[2]
            self.assertEqual(len(evidence), 1)
            self.assertEqual(evidence[0].stage, "generation")
            self.assertIn("could not be used", evidence[0].reason)

    def test_run_reports_cleanly_when_no_attempt_produces_a_test(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(
            main, "OUTPUT_DIR", Path(temp)
        ), patch.object(main, "gather_context", return_value=RepositoryContext()), patch.object(
            main, "generate_reproduction_test", side_effect=GenerationError("no JSON")
        ), patch.object(main, "run_in_daytona") as execute:
            self.assertFalse(main.run("https://example.test/repo.git", "issue", 2))
            execute.assert_not_called()

    @unittest.skipUnless(importlib.util.find_spec("dotenv"), "python-dotenv not installed")
    def test_load_environment_reads_project_dotenv_without_overriding_process(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / ".env").write_text("REPRO_TEST_A=from-file\nREPRO_TEST_B=from-file\n")
            os.environ["REPRO_TEST_B"] = "from-process"
            os.environ.pop("REPRO_TEST_A", None)
            try:
                main.load_environment(Path(temp))

                self.assertEqual(os.environ.get("REPRO_TEST_A"), "from-file")
                self.assertEqual(os.environ.get("REPRO_TEST_B"), "from-process")
            finally:
                os.environ.pop("REPRO_TEST_A", None)
                os.environ.pop("REPRO_TEST_B", None)


if __name__ == "__main__":
    unittest.main()
