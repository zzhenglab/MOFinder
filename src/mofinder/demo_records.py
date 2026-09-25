"""Expected-output comparisons and persistent records for the offline demos."""
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from uuid import uuid4

import pandas as pd

from mofinder.display import display_path


def verify_files(output_dir, expected_dir, filenames, *, rtol=0, atol=0):
    """Compare saved artifacts without modifying either actual or expected files."""
    checks = []
    for name in filenames:
        actual, expected = Path(output_dir) / name, Path(expected_dir) / name
        check = {"file": name, "expected_rows": None, "actual_rows": None, "passed": False,
                 "expected_sha256": hashlib.sha256(expected.read_bytes()).hexdigest() if expected.is_file() else None,
                 "actual_sha256": hashlib.sha256(actual.read_bytes()).hexdigest() if actual.is_file() else None}
        try:
            if actual.suffix == ".csv":
                actual_table = pd.read_csv(actual, keep_default_na=False)
                expected_table = pd.read_csv(expected, keep_default_na=False)
                check.update(expected_rows=len(expected_table), actual_rows=len(actual_table))
                pd.testing.assert_frame_equal(actual_table, expected_table, check_dtype=False,
                                              check_exact=rtol == atol == 0, rtol=rtol, atol=atol)
                check["detail"] = "All columns, rows, and values match the expected table."
            elif actual.suffix == ".jsonl":
                actual_text, expected_text = actual.read_text(encoding="utf-8"), expected.read_text(encoding="utf-8")
                check.update(expected_rows=len(expected_text.splitlines()), actual_rows=len(actual_text.splitlines()))
                if actual_text != expected_text:
                    raise AssertionError("JSONL records differ from expected output (line endings ignored).")
                check["detail"] = "All JSONL records match, including order and labels."
            else:
                if json.loads(actual.read_text(encoding="utf-8")) != json.loads(expected.read_text(encoding="utf-8")):
                    raise AssertionError("JSON values differ from expected output.")
                check["detail"] = "All JSON values match the expected output."
            check["passed"] = True
        except (AssertionError, OSError, ValueError) as error:
            check["detail"] = display_path(str(error))[:1000]
        checks.append(check)
    return {"passed": bool(checks) and all(item["passed"] for item in checks), "checks": checks}


class _Tee:
    def __init__(self, target, capture):
        self.target, self.capture = target, capture

    def write(self, text):
        self.target.write(text)
        return self.capture.write(text)

    def flush(self):
        self.target.flush()


class DemoRun:
    """Keep an independent output snapshot and log, even when a check fails."""
    def __init__(self, demo_dir, output_dir, inputs, *, history_dir=None):
        self.demo_dir, self.output_dir = Path(demo_dir), Path(output_dir)
        self.repo = self.demo_dir.parents[1]
        self.started = datetime.now(timezone.utc)
        run_id = self.started.strftime("%Y%m%dT%H%M%S.%fZ") + "_" + uuid4().hex[:8]
        self.folder = Path(history_dir or self.demo_dir / "run_history") / run_id
        self.work_dir = self.folder / "outputs"
        self.record_path = self.folder / "run_record.json"
        self.inputs = inputs
        self.verification = {"passed": None, "checks": [], "status": "not_requested"}
        self.log = io.StringIO()

    def reference(self, path):
        path = Path(path).resolve()
        try:
            return path.relative_to(self.repo.resolve()).as_posix()
        except ValueError:
            return path.name

    def __enter__(self):
        self.folder.mkdir(parents=True, exist_ok=False)
        self.work_dir.mkdir()
        self.input_records = {}
        for name, value in self.inputs.items():
            path = Path(value)
            source_code = path.suffix == ".py"
            contents = None
            if path.is_file():
                # Git may check out Python with CRLF on Windows; identify its code
                # with normalized line endings while preserving raw dataset hashes.
                contents = path.read_text(encoding="utf-8").encode("utf-8") if source_code else path.read_bytes()
            self.input_records[name] = {
                "path": self.reference(path), "hash_format": "utf-8-lf" if source_code else "bytes",
                "sha256": hashlib.sha256(contents).hexdigest() if contents is not None else None,
            }
        self.stdout = redirect_stdout(_Tee(sys.stdout, self.log))
        self.stderr = redirect_stderr(_Tee(sys.stderr, self.log))
        self.stdout.__enter__()
        self.stderr.__enter__()
        return self

    def __exit__(self, exc_type, error, traceback):
        self.stderr.__exit__(exc_type, error, traceback)
        self.stdout.__exit__(exc_type, error, traceback)
        artifacts = []
        # Every run generates into a fresh directory. Partial outputs survive failures,
        # and no earlier run's files can be mistaken for this run's artifacts.
        for destination in sorted(self.work_dir.glob("*")):
            if not destination.is_file():
                continue
            generated_sha256 = hashlib.sha256(destination.read_bytes()).hexdigest()
            # Generated provenance contains local absolute paths; publish portable paths.
            if destination.suffix == ".json":
                contents = destination.read_text(encoding="utf-8")
                portable = display_path(contents, project_root=self.repo)
                if portable != contents:
                    destination.write_text(portable, encoding="utf-8", newline="\n")
            artifacts.append({"path": "outputs/" + destination.name,
                              "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                              "generated_sha256": generated_sha256})
            if error is None:
                self.output_dir.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(destination, self.output_dir / destination.name)
        try:
            revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo, stderr=subprocess.DEVNULL).decode().strip()
            modified = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=self.repo).strip())
        except (OSError, subprocess.CalledProcessError):
            revision, modified = None, None
        finished = datetime.now(timezone.utc)
        record = {
            "schema_version": 1, "demo": self.demo_dir.name,
            "started_at": self.started.isoformat(), "finished_at": finished.isoformat(),
            "elapsed_seconds": round((finished - self.started).total_seconds(), 3),
            "status": "failed" if error else "completed",
            "python_version": platform.python_version(), "pandas_version": pd.__version__,
            "source_revision": revision, "source_has_local_changes": modified,
            "inputs": self.input_records, "verification": self.verification,
            "artifacts": artifacts, "log": "run.log",
        }
        if error:
            record["error"] = display_path(str(error), project_root=self.repo)
        (self.folder / "run.log").write_text(display_path(self.log.getvalue(), project_root=self.repo), encoding="utf-8")
        self.record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return False
