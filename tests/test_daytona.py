import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from src.daytona import ReproductionPlan, run_in_daytona


class FakeFS:
    def __init__(self, stage_results, artifacts=None):
        self.stage_results = stage_results
        self.artifacts = artifacts or {}
        self.uploads = {}

    def upload_file(self, content, remote_path):
        self.uploads[remote_path] = content

    def download_file(self, remote_path):
        if remote_path in self.artifacts:
            return self.artifacts[remote_path]
        for stage, result in self.stage_results.items():
            prefix = f"/home/daytona/repo/.repro-agent/{stage}."
            if remote_path == prefix + "stdout":
                return result[1].encode()
            if remote_path == prefix + "stderr":
                return result[2].encode()
            if remote_path == prefix + "exitcode":
                return str(result[0]).encode()
        if remote_path.endswith("app.stdout") or remote_path.endswith("app.stderr"):
            return b""
        raise FileNotFoundError(remote_path)


class FakeProcess:
    def __init__(self, artifact_listing=""):
        self.commands = []
        self.artifact_listing = artifact_listing

    def exec(self, command, **kwargs):
        self.commands.append((command, kwargs))
        result = self.artifact_listing if command.startswith("find test-results") else ""
        return SimpleNamespace(exit_code=0, result=result)


class FakeDaytona:
    def __init__(self, stage_results, artifact_listing="", artifacts=None):
        self.sandbox = SimpleNamespace()
        self.sandbox.fs = FakeFS(stage_results, artifacts)
        self.sandbox.process = FakeProcess(artifact_listing)
        self.sandbox.git = SimpleNamespace(clone=Mock())
        self.sandbox.delete = Mock()

    def create(self):
        return self.sandbox


PLAN = ReproductionPlan(
    summary="stale role",
    setup_notes="",
    test_file_name="tests/reproduce.spec.ts",
    test_code="import { test, expect } from '@playwright/test';",
    expected_failure="expected Editor, received Viewer",
)


class DaytonaRunnerTests(unittest.TestCase):
    def test_assertion_failure_is_reproduced_and_artifact_is_downloaded(self):
        stages = {
            "setup": (0, "installed", ""),
            "start": (0, "started", ""),
            "test": (1, "Error: expect(received) to be expected", "trace"),
        }
        remote = "/home/daytona/repo/test-results/failure.png"
        client = FakeDaytona(stages, "test-results/failure.png\n", {remote: b"png"})
        with tempfile.TemporaryDirectory() as temp:
            old = os.environ.get("DAYTONA_ARTIFACT_DIR")
            os.environ["DAYTONA_ARTIFACT_DIR"] = temp
            try:
                result = run_in_daytona("https://example.test/repo.git", PLAN, _daytona=client)
            finally:
                if old is None:
                    os.environ.pop("DAYTONA_ARTIFACT_DIR", None)
                else:
                    os.environ["DAYTONA_ARTIFACT_DIR"] = old

            self.assertTrue(result.reproduced)
            self.assertEqual(result.exit_code, 1)
            self.assertIn("expect(received)", result.stdout)
            self.assertEqual(len(result.artifacts), 1)
            self.assertEqual(Path(result.artifacts[0]).read_bytes(), b"png")
        client.sandbox.git.clone.assert_called_once_with(
            "https://example.test/repo.git", "/home/daytona/repo", depth=1
        )
        config = client.sandbox.fs.uploads[
            "/home/daytona/repo/.repro-agent.playwright.config.cjs"
        ].decode()
        self.assertIn("screenshot: 'only-on-failure'", config)
        self.assertIn("trace: 'retain-on-failure'", config)
        client.sandbox.delete.assert_called_once()

    def test_setup_failure_stops_before_start_and_test(self):
        client = FakeDaytona({"setup": (127, "", "npm: command not found")})
        result = run_in_daytona("https://example.test/repo.git", PLAN, _daytona=client)

        self.assertFalse(result.reproduced)
        self.assertEqual(result.exit_code, 127)
        self.assertEqual(result.reason, "Dependency setup failed with exit code 127")
        self.assertIn("npm: command not found", result.stderr)
        wrapped_commands = [
            command
            for command, _ in client.sandbox.process.commands
            if ".repro-agent/setup" in command
        ]
        self.assertEqual(len(wrapped_commands), 1)
        client.sandbox.delete.assert_called_once()

    def test_test_infrastructure_failure_is_not_a_reproduction(self):
        client = FakeDaytona(
            {
                "setup": (0, "", ""),
                "start": (0, "", ""),
                "test": (1, "SyntaxError: unexpected token", ""),
            }
        )
        result = run_in_daytona("https://example.test/repo.git", PLAN, _daytona=client)

        self.assertFalse(result.reproduced)
        self.assertIn("could not complete", result.reason)

    def test_rejects_test_path_traversal_without_creating_sandbox(self):
        client = Mock()
        bad_plan = ReproductionPlan("", "", "../escape.spec.ts", "", "")
        result = run_in_daytona("https://example.test/repo.git", bad_plan, _daytona=client)

        self.assertEqual(result.exit_code, -1)
        self.assertEqual(result.reason, "Invalid reproduction plan")
        client.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
