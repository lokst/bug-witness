import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import main
from src.models import ExecutionResult, ReproductionPlan, RepositoryContext


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


if __name__ == "__main__":
    unittest.main()
