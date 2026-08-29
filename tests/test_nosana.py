import unittest

from src.nosana import GenerationError, extract_json

# What a reasoning model actually sends back when it explains itself first:
# the test in a ```js block, then the plan in a ```json block.
CODE_THEN_PLAN = """\
Here is the reproduction test I propose:

```js
const { test, expect } = require('@playwright/test');
test('repro', async ({ page }) => { await page.goto('/'); });
```

And here is the structured plan:

```json
{"summary": "s", "testCode": "const { test } = require('x');"}
```
"""


class ExtractJsonTests(unittest.TestCase):
    def test_prefers_the_json_block_when_code_is_fenced_first(self):
        self.assertEqual(
            extract_json(CODE_THEN_PLAN),
            {"summary": "s", "testCode": "const { test } = require('x');"},
        )

    def test_language_tag_is_not_captured_as_payload(self):
        self.assertEqual(extract_json('```json\n{"testCode": "x"}\n```'), {"testCode": "x"})

    def test_object_outside_a_fence_survives_an_unrelated_fence(self):
        reply = '```js\nconsole.log(1)\n```\n{"testCode": "x"}'
        self.assertEqual(extract_json(reply), {"testCode": "x"})

    def test_unlabelled_fences_are_tried_in_order(self):
        reply = '```\nnot json\n```\n```\n{"testCode": "x"}\n```'
        self.assertEqual(extract_json(reply), {"testCode": "x"})

    def test_reasoning_block_is_stripped(self):
        reply = '<think>weighing options</think>\n```json\n{"testCode": "x"}\n```'
        self.assertEqual(extract_json(reply), {"testCode": "x"})

    def test_bare_object_with_trailing_commentary(self):
        self.assertEqual(extract_json('Sure:\n{"testCode": "x"}\nHope that helps'), {"testCode": "x"})

    def test_reply_without_any_object_is_reported(self):
        with self.assertRaisesRegex(GenerationError, "no JSON object"):
            extract_json("I cannot help with that.")

    def test_malformed_object_is_reported_as_invalid_json(self):
        with self.assertRaisesRegex(GenerationError, "not valid JSON"):
            extract_json('{"testCode": "x",}')


if __name__ == "__main__":
    unittest.main()
