import unittest

from src.nosana import GenerationError, _read_stream, extract_json

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


class StreamTests(unittest.TestCase):
    def test_deltas_are_reassembled_in_order(self):
        stream = [
            b'data: {"choices":[{"delta":{"content":"{\\"sum"}}]}\n',
            b"\n",
            b'data: {"choices":[{"delta":{"content":"mary\\": \\"x\\"}"}}]}\n',
            b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n',
            b"data: [DONE]\n",
        ]
        self.assertEqual(_read_stream(stream), '{"summary": "x"}')

    def test_unparseable_lines_are_skipped(self):
        # A proxy can inject keep-alive comments between events.
        stream = [
            b": ping\n",
            b"data: not json\n",
            b'data: {"choices":[{"delta":{"content":"ok"}}]}\n',
            b"data: [DONE]\n",
        ]
        self.assertEqual(_read_stream(stream), "ok")


if __name__ == "__main__":
    unittest.main()
