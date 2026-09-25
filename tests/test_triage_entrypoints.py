"""Check demonstration syntax and Python entry points with controlled responses."""

import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from mofinder.literature import triage
from mofinder.evaluation.triage import evaluate_counts


ROOT = Path(__file__).resolve().parents[1]




class TriageEntrypointTests(unittest.TestCase):
    def test_all_code_cells_compile_with_notebook_await(self):
        for path in (ROOT / "Demo").glob("*/*.ipynb"):
            notebook = json.loads(path.read_text(encoding="utf-8"))
            for index, cell in enumerate(notebook["cells"]):
                if cell["cell_type"] == "code":
                    with self.subTest(notebook=path.name, cell=index):
                        compile("".join(cell["source"]), f"cell_{index}", "exec",
                                flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)

    def test_strict_response_parsing_does_not_convert_failures_to_negative(self):
        from functools import partial
        classify = partial(triage.classify_one,
                           prompt=(ROOT / "prompts/abstract_triage.txt").read_text(encoding="utf-8"),
                           run_id="offline-test", max_output_tokens=100)
        paper = {"DOI": "10.1234/example", "title": "Example", "source": "Journal",
                 "author_keywords": "", "keywords_plus": "", "abstract": "Example abstract."}
        config = {"name": "test", "model": "gpt-4o", "reasoning_effort": None}
        for raw, status, expected_label, expected_status in [
            ("Y", "completed", "Y", "ok"),
            (" N\n", "completed", "N", "ok"),
            ("Y/N", "completed", "", "invalid_answer"),
            ("Yes", "completed", "", "invalid_answer"),
            ("n", "completed", "", "invalid_answer"),
            ("N", "incomplete", "", "incomplete"),
        ]:
            with self.subTest(raw=raw, status=status):
                response = SimpleNamespace(output_text=raw, status=status, id="mock", model="mock")
                create = AsyncMock(return_value=response)
                result = asyncio.run(classify(SimpleNamespace(responses=SimpleNamespace(create=create)),
                                               paper, config, 1))
                self.assertEqual(result["Agent_YN"], expected_label)
                self.assertEqual(result["Status"], expected_status)
                self.assertNotIn("reasoning", create.call_args.kwargs)
                self.assertFalse(create.call_args.kwargs["store"])

        create = AsyncMock(side_effect=RuntimeError("Request failed"))
        result = asyncio.run(classify(SimpleNamespace(responses=SimpleNamespace(create=create)),
                                       paper, {**config, "reasoning_effort": "high"}, 1))
        self.assertEqual(result["Agent_YN"], "")
        self.assertEqual(result["Status"], "api_error")
        self.assertEqual(create.call_args.kwargs["reasoning"], {"effort": "high"})

    def test_metrics_keep_failed_and_unscheduled_papers_in_coverage(self):
        summary, _ = evaluate_counts([1, 0], [1, 0], "test", 1, 4, 3, "Full reference",
                                     bootstraps=50, statistics_seed=42)
        self.assertEqual(summary["Reference N"], 4)
        self.assertEqual(summary["Scheduled reference N"], 3)
        self.assertEqual(summary["Scored N"], 2)
        self.assertEqual(summary["Unscored reference N"], 2)
        self.assertEqual(summary["Coverage of reference"], 0.5)
        self.assertEqual(summary["Accuracy"], 1)


if __name__ == "__main__":
    unittest.main()
