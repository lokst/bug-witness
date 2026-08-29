"""The prompt templates are a contract with what ``context.py`` gathers.

``_fill`` replaces only the placeholders a template mentions, so a value
that is gathered, ranked and formatted but never interpolated is dropped
with no error and no log line -- the model simply never sees the source it
was supposed to reason about.
"""

import re
import unittest

from src.models import RepositoryContext
from src.nosana import PROMPT_DIR, _fill, _format_context


class PromptTemplateTests(unittest.TestCase):
    """Context that is gathered but never interpolated is silently discarded.

    ``_fill`` only replaces placeholders the template mentions, so a value
    missing from the template costs the model that evidence with no error.
    """

    def _placeholders(self, name):
        template = (PROMPT_DIR / name).read_text()
        return set(re.findall(r"\{([a-z_]+)\}", template))

    def test_generate_prompt_consumes_every_gathered_value(self):
        context = RepositoryContext(
            package_json="{}", readme="r", file_tree="t", relevant_files=["f"]
        )
        provided = set(_format_context(context)) | {"issue"}
        self.assertEqual(provided - self._placeholders("generate_test.md"), set())

    def test_refine_prompt_consumes_the_repository_context(self):
        """Refining needs the evidence and the source the selectors come from.

        ``package_json`` and ``readme`` are deliberately not required here:
        the refine step already has the previous attempt to work from, so
        only the placeholders it reasons about are a contract.
        """
        placeholders = self._placeholders("refine_test.md")
        self.assertLessEqual(
            {"issue", "previous_attempts", "file_tree", "relevant_files"}, placeholders
        )

    def test_relevant_files_reach_the_filled_prompt(self):
        context = RepositoryContext(relevant_files=["--- Login.jsx ---\nSign in"])
        values = _format_context(context)
        values["issue"] = "i"
        filled = _fill((PROMPT_DIR / "generate_test.md").read_text(), values)
        self.assertIn("Sign in", filled)
        self.assertNotIn("{relevant_files}", filled)


if __name__ == "__main__":
    unittest.main()
