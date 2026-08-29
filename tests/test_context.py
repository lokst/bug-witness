"""Tests for repository context gathering.

The two behaviours worth pinning down are the ones that only misbehave at real
repository scale: the file tree has to stay inside its prompt budget, and a
pinned revision has to be fetched without downloading the whole history.
"""

import unittest
from pathlib import Path
from unittest import mock

from src import context


def make_files(root: Path, relative: list[str]) -> list[Path]:
    return [root / name for name in relative]


class BuildFileTreeTests(unittest.TestCase):
    def test_shallow_paths_are_listed_individually(self):
        root = Path("/repo")
        files = make_files(root, ["package.json", "src/App.jsx", "src/pages/Home.jsx"])

        tree = context.build_file_tree(root, files)

        self.assertEqual(tree, "package.json\nsrc/App.jsx\nsrc/pages/Home.jsx")

    def test_paths_below_the_depth_limit_collapse_to_a_count(self):
        root = Path("/repo")
        files = make_files(
            root,
            [
                "src/a/b/deep-one.js",
                "src/a/b/deep-two.js",
                "src/a/b/deep-three.js",
                "README.md",
            ],
        )

        tree = context.build_file_tree(root, files)

        self.assertIn("src/a/b/ (3 more files)", tree)
        self.assertIn("README.md", tree)
        self.assertNotIn("deep-one.js", tree)

    def test_a_large_repository_is_held_within_the_budget(self):
        root = Path("/repo")
        files = make_files(
            root, [f"src/module{index}/nested/file{index}.js" for index in range(4000)]
        )

        tree = context.build_file_tree(root, files)

        self.assertLessEqual(len(tree), context.MAX_TREE_CHARS)

    def test_depth_is_reduced_before_the_tree_is_truncated(self):
        root = Path("/repo")
        files = make_files(
            root, [f"src/module{index}/file{index}.js" for index in range(600)]
        )

        tree = context.build_file_tree(root, files, max_chars=2000)

        self.assertLessEqual(len(tree), 2000)
        self.assertNotIn("... truncated ...", tree)
        self.assertIn("more files", tree)

    def test_an_unshrinkable_tree_is_truncated(self):
        root = Path("/repo")
        files = make_files(root, [f"file{index}.js" for index in range(5000)])

        tree = context.build_file_tree(root, files, max_chars=500)

        self.assertIn("... truncated ...", tree)
        self.assertLessEqual(len(tree), 500 + len("\n... truncated ...\n"))


class CloneRepositoryTests(unittest.TestCase):
    def test_an_unpinned_clone_is_shallow(self):
        with mock.patch.object(context, "_run", return_value="") as run:
            context.clone_repository("https://example.test/repo.git", Path("/tmp/x"))

        self.assertEqual(
            run.call_args_list[0].args[0],
            ["git", "clone", "--quiet", "--depth", "1", "https://example.test/repo.git", "/tmp/x"],
        )

    def test_a_pinned_ref_is_fetched_at_depth_one(self):
        with mock.patch.object(context, "_run", return_value="") as run:
            with mock.patch.object(Path, "mkdir"):
                context.clone_repository("https://example.test/repo.git", Path("/tmp/x"), "abc123")

        commands = [call.args[0] for call in run.call_args_list]
        self.assertIn(
            ["git", "fetch", "--quiet", "--depth", "1", "origin", "abc123"], commands
        )
        self.assertIn(["git", "checkout", "--quiet", "FETCH_HEAD"], commands)
        self.assertFalse(
            any("clone" in command for command in commands),
            "a pinned ref should not need a full clone",
        )

    def test_a_refused_shallow_fetch_falls_back_to_a_full_clone(self):
        def fake_run(args, cwd=None):
            if args[1] == "fetch":
                raise RuntimeError("server does not allow request for unadvertised object")
            return ""

        with mock.patch.object(context, "_run", side_effect=fake_run) as run:
            with mock.patch.object(Path, "mkdir"), mock.patch.object(context, "shutil"):
                context.clone_repository("https://example.test/repo.git", Path("/tmp/x"), "abc123")

        commands = [call.args[0] for call in run.call_args_list]
        self.assertIn(
            ["git", "clone", "--quiet", "https://example.test/repo.git", "/tmp/x"], commands
        )
        self.assertIn(["git", "checkout", "--quiet", "abc123"], commands)


if __name__ == "__main__":
    unittest.main()
