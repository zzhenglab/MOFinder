"""Offline checks for literature retrieval inventories and desktop control decisions."""

from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from mofinder.literature_retrieval import common


HAS_TABLE_DEPENDENCIES = all(importlib.util.find_spec(name) is not None for name in ("pandas", "openpyxl"))


@unittest.skipUnless(HAS_TABLE_DEPENDENCIES, "Install the literature retrieval extra for literature retrieval tests.")
class LiteratureRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pandas as pd
        from mofinder.literature_retrieval import papers, si
        cls.pd, cls.papers, cls.si = pd, papers, si

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def frame(self, statuses, field="Downloaded"):
        return self.pd.DataFrame({"DOI": [f"10.0000/group{i}" for i in range(len(statuses))],
                                  "Publisher": ["publisher_A"] * len(statuses), field: statuses})

    def test_neutral_ids_are_explicit_and_case_insensitive(self):
        self.assertEqual(common.publisher_key(" Publisher_a "), "publisher_A")
        self.assertIsNone(common.publisher_key("10.0000/article"))
        self.assertIsNone(common.publisher_key("unknown"))
        self.assertIsNone(common.publisher_key(None))

    def test_csv_and_xlsx_roundtrip_preserve_status_strings(self):
        expected = ["", "0", "1"]
        for extension in (".csv", ".xlsx"):
            with self.subTest(extension=extension):
                path = self.folder / ("inventory" + extension)
                common.write_inventory(self.frame(expected), path)
                frame = common.read_inventory(path)
                self.assertEqual(frame["Downloaded"].tolist(), expected)
                frame.at[0, "Downloaded"] = "1"
                common.write_inventory(frame, path)
                self.assertEqual(common.read_inventory(path)["Downloaded"].tolist(), ["1", "0", "1"])

    def test_explicit_profile_column_takes_precedence(self):
        frame = self.frame([""])
        frame["Publisher"] = "descriptive metadata"
        frame["Publisher ID"] = "publisher_R"
        path = self.folder / "inventory.csv"
        common.write_inventory(frame, path)
        self.assertEqual(common.read_inventory(path).at[0, "Publisher"], "publisher_R")

    def test_working_copy_retains_progress_and_separates_sources(self):
        source = self.folder / "source.csv"
        common.write_inventory(self.frame(["", "0"]), source)
        initial_bytes = source.read_bytes()
        settings = {"mode": "papers", "workbook": source, "working_dir": self.folder / "working"}
        working = common.prepare_local_inventory(settings)
        frame = common.read_inventory(working)
        frame.at[0, "Downloaded"] = "1"
        common.write_inventory(frame, working)
        self.assertEqual(source.read_bytes(), initial_bytes)
        self.assertEqual(common.prepare_local_inventory(settings), working)
        self.assertEqual(common.read_inventory(working).at[0, "Downloaded"], "1")
        second = self.folder / "second.csv"
        second.write_bytes(initial_bytes)
        self.assertNotEqual(common.prepare_local_inventory({**settings, "workbook": second}), working)
        self.assertEqual(common.prepare_local_inventory({**settings, "workbook": working}), working)

    def test_classified_inventory_adds_only_local_status_and_preserves_labels(self):
        labels = ["Chemical synthesis", "Theory & modeling"]
        for mode, module, status in (("papers", self.papers, "Downloaded"),
                                     ("si", self.si, "SI Downloaded")):
            with self.subTest(mode=mode):
                source = self.folder / f"classified_{mode}.csv"
                frame = self.frame(["", ""]).drop(columns=["Downloaded"])
                frame["Classification"] = labels
                common.write_inventory(frame, source)
                initial = source.read_bytes()
                working = common.prepare_local_inventory({"mode": mode, "workbook": source,
                                                           "working_dir": self.folder / mode})
                with patch.object(module, "log"):
                    prepared = module.load_and_prepare_excel(working)
                    self.assertEqual(prepared[status].tolist(), ["", ""])
                    prepared.at[0, status] = "1"
                    module.save_progress(prepared, working)
                self.assertEqual(source.read_bytes(), initial)
                saved = common.read_inventory(working)
                self.assertEqual(saved["Classification"].tolist(), labels)
                self.assertEqual(saved[status].tolist(), ["1", ""])

    def test_missing_coordinates_do_not_reuse_another_machine(self):
        for module in (self.papers, self.si):
            with self.subTest(module=module.__name__), patch.object(module, "CAL_FILE", self.folder / f"{module.__name__}.json"):
                calibration = module.load_calibration()
                self.assertIsNone(calibration["GLOBAL_SAVE"]["save_xy"])

    def test_article_icon_sequence_uses_numeric_steps_only(self):
        for name in ("publisher_A_10.png", "publisher_A_2.png", "publisher_A_1.png", "publisher_A_1_copy.png", "publisher_A_SI_1.png", "publisher_R_1.png"):
            (self.folder / name).touch()
        names = [p.name for p in self.papers.list_icon_sequence("publisher_A", self.folder)]
        self.assertEqual(names, ["publisher_A_1.png", "publisher_A_2.png", "publisher_A_10.png"])

    def test_si_status_normalization(self):
        self.assertEqual([self.si.si_norm(v) for v in ["", None, "SKIP", "0", "0.0", False, "1", "1.0", True]],
                         ["", "", "", "0", "0", "0", "1", "1", "1"])

    def test_article_start_selects_only_blank_statuses(self):
        module = self.papers
        path = self.folder / "inventory.csv"
        frame = self.frame(["", "0", "1", " "])
        common.write_inventory(frame, path)
        app = module.App.__new__(module.App)
        app.excel_path_var = Mock(get=Mock(return_value=str(path)))
        app.cal_data = {"GLOBAL_SAVE": {"save_xy": [20, 30]}}
        app.ui_queue = queue.Queue()
        app.root = Mock()
        app._save_last_excel = Mock()
        app.refresh_icon_availability = Mock()
        with patch.object(module, "_local_inventory", return_value=path), patch.object(module, "load_and_prepare_excel", return_value=frame), patch.object(module.threading, "Thread"), patch.object(module, "log"):
            app.start()
        self.assertEqual(app.pending_set, {0, 3})
        self.assertEqual(app.initial_done, 2)

    def run_papers(self, statuses, outcomes, threshold=20):
        module = self.papers
        frame = self.frame(statuses)
        app = module.App.__new__(module.App)
        app.cal_data = {"GLOBAL_SAVE": {"save_xy": [20, 30]}, "publisher_A": {"actions": [{"type": "click", "x": 1, "y": 2}]}}
        app.pending_set = {i for i, status in enumerate(statuses) if not status.strip()}
        app.journal_fail_counts = {}
        app.skip_journal_keys = set()
        app.get_paper_processing_icon_dir = Mock(return_value=self.folder)
        app.ui_queue = queue.Queue()
        calls = []
        answers = iter(outcomes)
        def action(actions, target, coordinates):
            calls.append(target.name)
            success = next(answers)
            if success:
                target.write_bytes(b"offline fixture")
            return success
        with ExitStack() as stack:
            for name, value in {"abort_now": False, "save_requested": False, "MAX_JOURNAL_FAILS": threshold,
                                "DOWNLOAD_DIR": self.folder, "run_actions_then_save": action}.items():
                stack.enter_context(patch.object(module, name, value))
            for name in ("save_progress", "reset_to_desktop", "open_in_chrome", "go_to_address_bar_and_open", "close_all_chrome", "log"):
                stack.enter_context(patch.object(module, name))
            stack.enter_context(patch.object(module.time, "sleep"))
            app.process_rows(frame, self.folder / "inventory.csv", list(range(len(frame))))
        return frame, calls

    def test_article_retries_and_preserves_finished_rows(self):
        frame, calls = self.run_papers(["", "0", "1"], [False, True])
        self.assertEqual(frame["Downloaded"].tolist(), ["1", "0", "1"])
        self.assertEqual(len(calls), 2)

    def test_article_journal_threshold_leaves_later_rows_blank(self):
        frame, calls = self.run_papers([""] * 3, [False] * 4, threshold=2)
        self.assertEqual(frame["Downloaded"].tolist(), ["0", "0", ""])
        self.assertEqual(len(calls), 4)

    def run_si(self, statuses, outcomes, *, double_check=False, test_mode=False, publishers=None):
        module = self.si
        frame = self.frame(statuses, "SI Downloaded")
        if publishers is not None:
            frame["Publisher"] = publishers
        frame["DOI Link"] = frame["DOI"].map(module.doi_to_link)
        work = frame[["DOI", "DOI Link", "SI Downloaded"]].copy()
        work["TargetStem"] = work["DOI"].map(module.doi_stem)
        app = module.App.__new__(module.App)
        app.test_mode_var = Mock(get=Mock(return_value=test_mode))
        app.succ_count = statuses.count("1")
        app.fail_count = statuses.count("0")
        app.ui_queue = queue.Queue()
        calls, available = [], set()
        answers = iter(outcomes)
        def flow(icon_dir, coordinates, target):
            calls.append(target.name)
            result = next(answers)
            if result is True:
                available.add(str(target))
            return result
        def existing(target, timeout):
            return target.with_suffix(".pdf") if str(target) in available else None
        with ExitStack() as stack:
            for name, value in {"abort_now": False, "save_requested": False, "PAPER_PROCESSING_ICON_DIR": self.folder,
                                "PUBLISHER_FLOW": {"publisher_A": flow}, "fresh_file_ready_any": existing}.items():
                stack.enter_context(patch.object(module, name, value))
            stack.enter_context(patch.object(module, "ensure_si_download_dir", return_value=self.folder))
            stack.enter_context(patch.object(module, "load_calibration", return_value={"GLOBAL_SAVE": {"save_xy": [20, 30]}}))
            for name in ("save_progress", "ensure_chrome_closed", "safe_reset_to_desktop", "open_in_chrome", "go_to_address_bar_and_open", "move_cursor_top_center", "log"):
                stack.enter_context(patch.object(module, name))
            stack.enter_context(patch.object(module.time, "sleep"))
            app.process_rows(frame, work, self.folder / "inventory.csv", double_check)
        return work, calls

    def test_si_normal_mode_retries_blanks_and_preserves_zero_one(self):
        work, calls = self.run_si(["", "0", "1"], [False, True])
        self.assertEqual(work["SI Downloaded"].tolist(), ["1", "0", "1"])
        self.assertEqual(len(calls), 2)

    def test_si_double_check_processes_only_zero(self):
        work, calls = self.run_si(["", "0", "1"], [True], double_check=True)
        self.assertEqual(work["SI Downloaded"].tolist(), ["", "1", "1"])
        self.assertEqual(len(calls), 1)

    def test_si_skip_and_unmapped_rows_stay_blank(self):
        work, calls = self.run_si(["", ""], ["SKIP"], publishers=["publisher_A", "unmapped"])
        self.assertEqual(work["SI Downloaded"].tolist(), ["", ""])
        self.assertEqual(len(calls), 1)

    def test_si_journal_threshold_preserves_unattempted_rows(self):
        work, calls = self.run_si([""] * 6, [False] * 10)
        self.assertEqual(work["SI Downloaded"].tolist(), ["0"] * 5 + [""])
        self.assertEqual(len(calls), 10)

    def test_si_three_successes_double_journal_failure_allowance(self):
        work, calls = self.run_si([""] * 14, [True] * 3 + [False] * 20)
        self.assertEqual(work["SI Downloaded"].tolist(), ["1"] * 3 + ["0"] * 10 + [""])
        self.assertEqual(len(calls), 23)

    def test_si_test_mode_limits_pending_rows_to_five(self):
        work, calls = self.run_si([""] * 7, [True] * 5, test_mode=True)
        self.assertEqual(work["SI Downloaded"].tolist(), ["1"] * 5 + [""] * 2)
        self.assertEqual(len(calls), 5)

    def test_corner_fail_safe_is_not_swallowed_by_image_search(self):
        class PointerStop(Exception):
            pass
        for module in (self.papers, self.si):
            gui = SimpleNamespace(FailSafeException=PointerStop, locateCenterOnScreen=Mock(side_effect=PointerStop()))
            with self.subTest(module=module.__name__), patch.object(module, "pyautogui", gui, create=True), patch.object(module, "abort_now", False), patch.object(module, "save_requested", False):
                with self.assertRaises(SystemExit):
                    module.locate_center_on_screen(self.folder / "icon.png", 0.87)
                self.assertTrue(module.abort_now)
                self.assertTrue(module.save_requested)

    def test_headless_help_and_validation_do_not_import_gui_or_write_files(self):
        path = self.folder / "inventory.csv"
        common.write_inventory(self.frame(["", "0", "1"]), path)
        config = {"project_root": ".", "paper_processing_icon_dir": "icons"}
        for mode in ("papers", "si"):
            config[mode] = {"workbook": "inventory.csv", "working_dir": f"working/{mode}",
                            "calibration_file": f"working/{mode}/calibration.json",
                            "app_settings_file": f"working/{mode}/app_settings.json", "download_dir": f"downloads/{mode}"}
        configuration = self.folder / "literature_retrieval.json"
        configuration.write_text(json.dumps(config), encoding="utf-8")
        before = {p.relative_to(self.folder): p.read_bytes() for p in self.folder.rglob("*") if p.is_file()}
        blocker = """import importlib.abc, runpy, sys
class NoDesktop(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'tkinter', 'pyautogui', 'pynput', 'pyperclip'}:
            raise AssertionError('Desktop import attempted: ' + fullname)
sys.meta_path.insert(0, NoDesktop())
module = sys.argv.pop(1)
runpy.run_module(module, run_name='__main__')
"""
        for mode in ("papers", "si"):
            for arguments in (["--help"], ["--config", str(configuration), "--validate"]):
                result = subprocess.run([sys.executable, "-c", blocker, f"mofinder.literature_retrieval.{mode}", *arguments], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
        after = {p.relative_to(self.folder): p.read_bytes() for p in self.folder.rglob("*") if p.is_file()}
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
