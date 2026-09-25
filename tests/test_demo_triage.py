"""Exercise the combined API demo without contacting the OpenAI API."""

import ast
import asyncio
from contextlib import redirect_stdout
import csv
from html import escape
import inspect
import io
import json
import os
from pathlib import Path
import runpy
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from mofinder.literature import triage


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "Demo/03_api_demo/mof_api_demo.ipynb"


class DemoTriageTests(unittest.TestCase):
    def setUp(self):
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        self.cells = {
            cell["id"]: "".join(cell["source"])
            for cell in notebook["cells"] if cell["cell_type"] == "code"
        }
        self.namespace = {}
        self.stdout = io.StringIO()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.output_root = self.folder / "runs"

        # Rendering and transport are replaced; the notebook and screening code run normally.
        display_module = ModuleType("IPython.display")
        display_module.HTML = lambda value: SimpleNamespace(data=value)
        self.display = display_module.display = Mock()
        self.create = AsyncMock()
        context = AsyncMock()
        context.__aenter__.return_value = SimpleNamespace(
            responses=SimpleNamespace(create=self.create)
        )
        sdk_module = ModuleType("openai")
        self.sdk = sdk_module.AsyncOpenAI = Mock(return_value=context)
        self.start_patch(patch.dict("sys.modules", {
            "IPython": ModuleType("IPython"), "IPython.display": display_module,
            "openai": sdk_module,
        }))
        self.start_patch(patch.dict(os.environ, {"OPENAI_API_KEY": ""}))
        self.key_prompt = self.start_patch(patch("getpass.getpass", return_value=""))
        self.start_patch(patch("pathlib.Path.cwd", return_value=ROOT))

        self.execute("load-abstracts")
        config = json.loads((ROOT / "Demo/03_api_demo/configs/triage.json").read_text())
        config.update(project_root=str(ROOT), output_root=str(self.output_root))
        for key in ("input_file", "ground_truth_file", "prompt_file"):
            source = ROOT / config[key]
            destination = self.folder / source.name
            destination.write_bytes(source.read_bytes())
            config[key] = str(destination)
        config_file = self.folder / "config.json"
        config_file.write_text(json.dumps(config), encoding="utf-8")
        self.namespace["CONFIG_FILE"] = config_file
        self.reload_inputs()
        self.execute("preview-requests")

    def reload_inputs(self):
        config, validated, prompt = self.namespace["read_triage_inputs"](
            self.namespace["CONFIG_FILE"]
        )
        self.namespace.update(config=config, validated=validated, prompt=prompt,
                              papers=validated["papers"], model_config=config["models"][0])

    def start_patch(self, patcher):
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def execute(self, cell_id, *, live=False, switch="RUN_TRIAGE"):
        tree = ast.parse(self.cells[cell_id])
        if live:
            # Simulate the user's documented edit, retaining the rest of the actual cell.
            enabled = False
            for node in tree.body:
                if (isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == switch
                                for target in node.targets)):
                    node.value = ast.Constant(value=True)
                    enabled = True
            self.assertTrue(enabled, f"No {switch} assignment in {cell_id}")
            ast.fix_missing_locations(tree)
        code = compile(tree, f"{NOTEBOOK.name}:{cell_id}", "exec",
                       flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
        with redirect_stdout(self.stdout):
            result = eval(code, self.namespace)
            if inspect.isawaitable(result):
                asyncio.run(result)

    @staticmethod
    def response(answer):
        return SimpleNamespace(output_text=answer, status="completed",
                               id="offline-response", model="gpt-4o")

    def test_all_code_cells_compile_with_notebook_await_support(self):
        for cell_id, source in self.cells.items():
            with self.subTest(cell=cell_id):
                compile(source, f"{NOTEBOOK.name}:{cell_id}", "exec",
                        flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)

    def test_cli_and_notebook_validate_the_same_four_abstracts(self):
        runner = runpy.run_path(str(NOTEBOOK.parent / "mof_api_demo.py"))
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(runner["main"](["triage"]), 0)
        summary = json.loads(output.getvalue())
        self.assertEqual(summary, triage.validation_summary(self.namespace["validated"]))
        self.assertEqual(summary["scheduled_publications"], 4)
        self.sdk.assert_not_called()

    def test_mining_setup_and_defaults_validate_without_live_calls(self):
        os.environ["OPENAI_API_KEY"] = "offline-test-key"
        runner = {
            "validate_positive": Mock(return_value={"ready_for_live_extraction": True}),
            "run_positive": Mock(),
            "run_negative": Mock(),
        }
        with patch("runpy.run_path", return_value=runner) as load_runner:
            self.execute("mining-setup")
        load_runner.assert_called_once_with(str(NOTEBOOK.parent / "mof_api_demo.py"))
        runner["validate_positive"].assert_called_once_with(NOTEBOOK.parent / "configs")
        self.execute("positive-api")
        self.execute("negative-api")
        runner["run_positive"].assert_not_called()
        runner["run_negative"].assert_not_called()
        self.sdk.assert_not_called()
        self.key_prompt.assert_not_called()

    def test_mining_switches_enable_only_the_selected_stage(self):
        runner = {
            "run_positive": Mock(return_value={"positive": "completed"}),
            "run_negative": Mock(return_value={"negative": "completed"}),
        }
        self.namespace.update(api_runner=runner, MINING_CONFIG_DIR=self.folder)
        self.execute("positive-api", live=True, switch="RUN_POSITIVE_MINING")
        runner["run_positive"].assert_called_once_with(self.folder)
        self.assertEqual(self.namespace["positive_result"], {"positive": "completed"})
        self.execute("negative-api")
        runner["run_negative"].assert_not_called()
        self.execute("negative-api", live=True, switch="RUN_NEGATIVE_MINING")
        runner["run_negative"].assert_called_once_with(live=True, config_dir=self.folder)
        self.assertEqual(self.namespace["negative_result"], {"negative": "completed"})
        runner["run_positive"].assert_called_once()

    def test_default_preview_shows_full_abstracts_without_requests_or_files(self):
        os.environ["OPENAI_API_KEY"] = "offline-test-key"
        self.execute("run-api")
        self.execute("show-results")

        self.assertEqual(len(self.namespace["papers"]), 4)
        html = "\n".join(call.args[0].data for call in self.display.call_args_list)
        for paper in self.namespace["papers"]:
            self.assertIn(escape(paper["abstract"]), html)
            self.assertIn(escape(paper["title"]), html)
        self.sdk.assert_not_called()
        self.create.assert_not_awaited()
        self.key_prompt.assert_not_called()
        self.assertFalse(self.output_root.exists())
        self.assertIsNone(self.namespace["screening_run"])
        self.assertEqual(self.namespace["comparison"], [])
        self.assertIn("No API run to display", self.stdout.getvalue())

    def test_stale_inputs_stop_before_key_prompt_api_client_or_run_files(self):
        config = self.namespace["config"]
        changes = {
            self.namespace["CONFIG_FILE"]: lambda value: value.replace('"max_papers": 4', '"max_papers": 3'),
            config["prompt_file"]: lambda value: value + "\nAdditional instruction.\n",
            config["input_file"]: lambda value: value.replace(self.namespace["papers"][0]["title"], "Changed title"),
            config["ground_truth_file"]: lambda value: value.replace(",Y,", ",N,", 1),
        }
        for path, change in changes.items():
            original = path.read_text(encoding="utf-8")
            modified = change(original)
            with self.subTest(path=path.name):
                self.assertNotEqual(modified, original)
                try:
                    path.write_text(modified, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "Rerun steps 1.1 and 1.2"):
                        self.execute("run-api", live=True)
                finally:
                    path.write_text(original, encoding="utf-8")
                self.key_prompt.assert_not_called()
                self.sdk.assert_not_called()
                self.create.assert_not_awaited()
                self.assertFalse(self.output_root.exists())

    def test_results_use_saved_reference_even_after_notebook_inputs_change(self):
        os.environ["OPENAI_API_KEY"] = "offline-test-key"
        self.create.return_value = self.response("Y")
        self.execute("run-api", live=True)
        reference_file = self.namespace["screening_run"].output_dir / "reference_used.csv"
        _, reference, _ = triage.read_table(reference_file)
        expected = {triage.doi_key(row["DOI"]): row["Consensus GT"] for row in reference}
        self.namespace["validated"]["ground_truth_by_doi"].clear()
        self.execute("show-results")
        self.assertEqual([row["Human reference"] for row in self.namespace["comparison"]],
                         [expected[triage.doi_key(paper["DOI"])] for paper in self.namespace["papers"]])

    def test_unreferenced_papers_are_predicted_but_excluded_from_agreement(self):
        os.environ["OPENAI_API_KEY"] = "offline-test-key"
        self.create.return_value = self.response("Y")
        config_file = self.namespace["CONFIG_FILE"]
        config = json.loads(config_file.read_text(encoding="utf-8"))
        config["benchmark_only"] = False
        config_file.write_text(json.dumps(config), encoding="utf-8")
        reference_file = Path(config["ground_truth_file"])
        headers, reference, _ = triage.read_table(reference_file)
        missing_key = triage.doi_key(self.namespace["papers"][0]["DOI"])
        triage.save_csv([row for row in reference if triage.doi_key(row["DOI"]) != missing_key],
                        reference_file, headers)
        self.reload_inputs()
        self.execute("preview-requests")
        self.execute("run-api", live=True)
        self.execute("show-results")
        comparison = self.namespace["comparison"]
        self.assertEqual(comparison[0]["GPT prediction"], "Y")
        self.assertEqual(comparison[0]["Human reference"], "Unavailable")
        self.assertEqual(comparison[0]["Agreement"], "Unscored")
        self.assertIn("Valid GPT answers: 4/4", self.stdout.getvalue())
        self.assertIn("/3 valid answers with reference labels", self.stdout.getvalue())

    def test_live_requests_match_previews_and_failures_remain_unscored(self):
        os.environ["OPENAI_API_KEY"] = "  offline-test-key  "
        self.create.side_effect = [
            self.response("Y"), self.response("N"), self.response("Yes"),
            RuntimeError("Simulated connection failure"),
        ]
        self.execute("run-api", live=True)
        run = self.namespace["screening_run"]
        expected_by_doi = {triage.doi_key(row["DOI"]): dict(row) for row in run.rows}
        # Result order is independent of asynchronous completion order.
        run.rows.reverse()
        self.execute("show-results")

        self.assertCountEqual([call.kwargs for call in self.create.await_args_list],
                              self.namespace["preview_requests"])
        self.sdk.assert_called_once_with(
            api_key="offline-test-key", timeout=self.namespace["config"]["request_timeout"],
            max_retries=2,
        )
        self.key_prompt.assert_not_called()
        self.assertIsNone(self.namespace["api_key"])
        comparison = self.namespace["comparison"]
        self.assertEqual([row["DOI"] for row in comparison],
                         [paper["DOI"] for paper in self.namespace["papers"]])
        for row in comparison:
            key = triage.doi_key(row["DOI"])
            record = expected_by_doi[key]
            reference = self.namespace["validated"]["ground_truth_by_doi"][key]["Consensus GT"]
            self.assertEqual(row["Human reference"], reference)
            self.assertEqual(row["Status"], record["Status"])
            self.assertEqual(row["Raw answer"], record["Raw answer"])
            if record["Status"] == "ok":
                self.assertEqual(row["GPT prediction"], record["Agent_YN"])
                self.assertEqual(row["Agreement"],
                                 "Yes" if record["Agent_YN"] == reference else "No")
            else:
                self.assertEqual(row["GPT prediction"], "Unscored")
                self.assertEqual(row["Agreement"], "Unscored")
                self.assertTrue(row["Error"])
        self.assertEqual([row["Status"] for row in comparison],
                         ["ok", "ok", "invalid_answer", "api_error"])
        self.assertIn("Valid GPT answers: 2/4", self.stdout.getvalue())
        with (run.output_dir / "demo_comparison.csv").open(encoding="utf-8-sig", newline="") as stream:
            self.assertEqual(list(csv.DictReader(stream)), comparison)

    def test_human_labels_cannot_enter_preview_or_api_requests(self):
        for paper, preview in zip(self.namespace["papers"], self.namespace["preview_requests"]):
            with self.subTest(doi=paper["DOI"]):
                enriched = {**paper, "Consensus GT": "PRIVATE_REFERENCE_SENTINEL"}
                request = triage.build_screening_request(
                    enriched, self.namespace["model_config"], prompt=self.namespace["prompt"],
                    max_output_tokens=self.namespace["config"]["max_output_tokens"],
                )
                self.assertEqual(request, preview)
                self.assertNotIn("PRIVATE_REFERENCE_SENTINEL", json.dumps(request))
                self.assertIn(paper["abstract"], request["input"][0]["content"])
                self.assertFalse(request["store"])

    def test_authentication_error_leaves_remaining_papers_unrequested(self):
        self.key_prompt.return_value = "  offline-prompt-key  "
        error = RuntimeError("Simulated invalid API key")
        error.status_code = 401
        self.create.side_effect = error
        self.execute("run-api", live=True)
        self.execute("show-results")

        self.key_prompt.assert_called_once()
        self.assertEqual(self.sdk.call_args.kwargs["api_key"], "offline-prompt-key")
        self.create.assert_awaited_once()
        comparison = self.namespace["comparison"]
        self.assertEqual([row["Status"] for row in comparison],
                         ["configuration_error", "not_requested", "not_requested", "not_requested"])
        self.assertTrue(all(row["GPT prediction"] == "Unscored" for row in comparison))
        self.assertTrue(all(row["Agreement"] == "Unscored" for row in comparison))
        self.assertIn("Valid GPT answers: 0/4", self.stdout.getvalue())

    def test_missing_key_stops_before_creating_api_client_or_run_files(self):
        self.key_prompt.return_value = "  "
        with self.assertRaisesRegex(ValueError, "API key is required"):
            self.execute("run-api", live=True)
        self.key_prompt.assert_called_once()
        self.sdk.assert_not_called()
        self.create.assert_not_awaited()
        self.assertFalse(self.output_root.exists())
        self.assertIsNone(self.namespace["api_key"])
        self.assertIsNone(self.namespace["screening_run"])


class DemoMiningTests(unittest.TestCase):
    def setUp(self):
        self.runner = runpy.run_path(str(NOTEBOOK.parent / "mof_api_demo.py"))
        self.namespace = self.runner["run_negative"].__globals__
        self.folder_context = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder_context.cleanup)
        self.folder = Path(self.folder_context.name)
        self.validation = {
            "eligible_dois": 1, "missing_inputs": [], "missing_documents": [],
            "missing_success_bases": [], "yes_dois_without_notes": [],
            "yes_dois_without_manifest": [],
        }
        self.key = Mock()
        replacements = {
            "require_api_key": self.key,
            "validate_positive": Mock(return_value={"placeholder_documents": []}),
            "validate_negative": Mock(return_value=self.validation),
        }
        patcher = patch.dict(self.namespace, replacements)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_document_templates_block_both_mining_stages_before_key_or_api(self):
        self.namespace["validate_positive"].return_value = {
            "placeholder_documents": [{"path": "template.pdf"}],
        }
        with patch("mofinder.extraction.positive.run_from_config") as positive, \
                patch("mofinder.extraction.negative.run_from_config") as negative:
            with self.assertRaisesRegex(ValueError, "Replace the document templates"):
                self.runner["run_positive"](self.folder)
            with self.assertRaisesRegex(ValueError, "Replace the document templates"):
                self.runner["run_negative"](live=True, config_dir=self.folder)
        self.key.assert_not_called()
        positive.assert_not_called()
        negative.assert_not_called()

    def test_incomplete_negative_inputs_stop_before_api(self):
        for field in ("missing_inputs", "missing_documents", "missing_success_bases",
                      "yes_dois_without_notes", "yes_dois_without_manifest"):
            with self.subTest(field=field), \
                    patch("mofinder.extraction.negative.run_from_config") as request:
                self.validation[field] = ["missing-example"]
                try:
                    with self.assertRaisesRegex(ValueError, "Inspect these inputs first"):
                        self.runner["run_negative"](live=True, config_dir=self.folder)
                finally:
                    self.validation[field] = []
                self.key.assert_not_called()
                request.assert_not_called()

    def test_no_eligible_documents_make_no_requests(self):
        self.validation["eligible_dois"] = 0
        with patch("mofinder.extraction.negative.run_from_config") as request, \
                patch("mofinder.extraction.negative.enumerate_from_config") as enumerate_saved:
            result = self.runner["run_negative"](live=True, config_dir=self.folder)
        self.assertEqual(result["eligible_dois"], 0)
        self.key.assert_not_called()
        request.assert_not_called()
        enumerate_saved.assert_not_called()

    def test_negative_preview_and_live_enumeration_use_matching_configuration(self):
        config = {"csv_out": str(self.folder / "plans.csv")}
        with patch("mofinder.extraction.negative.load_config", return_value=config), \
                patch("mofinder.extraction.negative.run_from_config", return_value={"plans": 1}) as plans, \
                patch("mofinder.extraction.negative.enumerate_from_config", return_value={"records": 2}) as enumerate_saved:
            self.runner["run_negative"](config_dir=self.folder)
            plans.assert_called_once_with(config, dry_run=True)
            self.key.assert_not_called()
            enumerate_saved.assert_not_called()
            plans.reset_mock()

            result = self.runner["run_negative"](live=True, config_dir=self.folder)
            plans.assert_called_once_with(config)
            self.assertIn("No plan CSV", result["message"])
            enumerate_saved.assert_not_called()

            Path(config["csv_out"]).write_text("doi\n", encoding="utf-8")
            result = self.runner["run_negative"](live=True, config_dir=self.folder)
            enumerate_saved.assert_called_once_with(config)
            self.assertEqual(result["enumeration"], {"records": 2})


if __name__ == "__main__":
    unittest.main()
