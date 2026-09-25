"""Offline checks for durable screening records and explicit resume behavior."""

import asyncio
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from mofinder.config import load_triage_config
from mofinder.literature import triage


ROOT = Path(__file__).resolve().parents[1]


class ScreeningTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.config = json.loads((ROOT / 'configs/abstract_triage.json').read_text())
        self.config.update(project_root=str(ROOT), input_file='Demo/03_triage_extraction/inputs/triage_metadata.csv',
                           ground_truth_file='Demo/03_triage_extraction/inputs/triage_ground_truth.csv',
                           models=[self.config['models'][0]], max_papers=3, bootstraps=20)
        self.config_file = self.folder / 'config.json'
        self.write_config()
        self.run_folder = self.folder / 'screening'

    def write_config(self):
        self.config_file.write_text(json.dumps(self.config))

    def client(self, *, error=None):
        response = SimpleNamespace(output_text='Y', status='completed', id='mock', model='mock')
        create = AsyncMock(side_effect=error, return_value=response)
        return SimpleNamespace(responses=SimpleNamespace(create=create))

    def invoke(self, client, resume=False):
        with redirect_stdout(io.StringIO()):
            return asyncio.run(triage.screen(self.config_file, output_dir=self.run_folder,
                                              resume=resume, client=client))

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

    def test_resume_sends_only_unrecorded_requests_and_keeps_errors(self):
        run = triage.prepare_screening(self.config_file, output_dir=self.run_folder)
        client = self.client(error=RuntimeError('Transient failure'))
        first = asyncio.run(triage.classify_one(client, run.papers[0], run.config['models'][0], 1,
                            prompt=run.prompt, run_id=run.manifest['run_id'], max_output_tokens=8192))
        original = (json.dumps(first) + '\n').encode()
        journal = self.run_folder / 'responses.jsonl'
        journal.write_bytes(original)
        client = self.client()
        resumed = self.invoke(client, resume=True)
        self.assertEqual(client.responses.create.await_count, 2)
        self.assertEqual(len(resumed.rows), 3)
        self.assertEqual(resumed.rows[0]['Status'], 'api_error')
        self.assertEqual(resumed.manifest['valid_answers'], 2)
        self.assertTrue(journal.read_bytes().startswith(original))
        # Reopening a completed run must not repeat any request.
        before = journal.read_bytes()
        client = self.client()
        self.invoke(client, resume=True)
        self.assertEqual(client.responses.create.await_count, 0)
        self.assertEqual(journal.read_bytes(), before)

    def test_changed_config_is_rejected_before_requests_or_file_changes(self):
        self.invoke(self.client())
        before = {p.name: p.read_bytes() for p in self.run_folder.iterdir()}
        self.config['max_output_tokens'] += 1
        self.write_config()
        client = self.client()
        with self.assertRaisesRegex(ValueError, 'Cannot resume'):
            self.invoke(client, resume=True)
        self.assertEqual(client.responses.create.await_count, 0)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.run_folder.iterdir()})

    def test_duplicate_or_fractional_saved_round_is_rejected(self):
        self.invoke(self.client())
        journal = self.run_folder / 'responses.jsonl'
        original = journal.read_text()
        for fractional in [False, True]:
            rows = [json.loads(line) for line in original.splitlines()]
            if fractional:
                rows[0]['Round'] = 1.5
            else:
                rows.append(rows[0])
            journal.write_text(''.join(json.dumps(row) + '\n' for row in rows))
            client = self.client()
            with self.assertRaises(ValueError):
                self.invoke(client, resume=True)
            self.assertEqual(client.responses.create.await_count, 0)

    def test_configuration_error_stops_dispatch_without_negative_labels(self):
        error = RuntimeError('No model access')
        error.status_code = 403
        client = self.client(error=error)
        run = self.invoke(client)
        self.assertEqual(client.responses.create.await_count, 1)
        self.assertEqual(run.rows[0]['Agent_YN'], '')
        self.assertEqual(run.rows[0]['Status'], 'configuration_error')
        self.assertEqual(run.manifest['expected_requests'], 3)
        self.assertEqual(run.manifest['valid_answers'], 0)
        self.assertEqual(run.manifest['stopped_configurations'], ['GPT-4o'])
        client = self.client()
        self.invoke(client, resume=True)
        self.assertEqual(client.responses.create.await_count, 0)

    def test_existing_run_requires_explicit_resume(self):
        self.invoke(self.client())
        client = self.client()
        with self.assertRaises(FileExistsError):
            self.invoke(client)
        self.assertEqual(client.responses.create.await_count, 0)

    def test_config_paths_are_relative_to_configured_project_root(self):
        loaded = load_triage_config(self.config_file)
        self.assertEqual(loaded['input_file'], ROOT / 'Demo/03_triage_extraction/inputs/triage_metadata.csv')
        self.assertEqual(loaded['prompt_file'], ROOT / 'prompts/abstract_triage.txt')
        self.assertEqual(loaded['output_root'], ROOT / 'results/abstract_triage')


if __name__ == '__main__':
    unittest.main()
