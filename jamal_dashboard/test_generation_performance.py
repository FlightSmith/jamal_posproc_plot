"""Generation diagnostics and fixed output/cache location below the first base."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import jamal_dashboard_launcher_v25 as launcher
from test_baseline import make_fixture


class GenerationPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='jamal_output_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.base = self.root / 'CFD inputs'
        self.payload = make_fixture(self.base)
        self.default_output = self.base / '03-RESULTS' / 'DASHBOARD'
        self.previous_output = self.root / 'Previous reports'

    def test_default_output_is_preserved_for_existing_setups(self):
        for field in ({}, {'output_directory': ''}, {'output_directory': '  '}):
            normalized = launcher._normalize_configurations({**self.payload, **field})
            self.assertEqual(launcher.output_directory(normalized), self.default_output)
            self.assertEqual(launcher.output_report_path(normalized), self.default_output / 'dashboard.html')

    def test_retired_output_setting_cannot_override_first_configuration(self):
        second_base = self.root / 'Second CFD'
        second = make_fixture(second_base)['configurations'][0]
        second['label'] = 'Second'
        for legacy_output in (str(self.previous_output), 'relative/reports'):
            payload = {**self.payload, 'output_directory': legacy_output,
                       'configurations': [self.payload['configurations'][0], second]}
            normalized = launcher._normalize_configurations(payload)
            self.assertEqual(launcher.output_directory(normalized), self.default_output)
            self.assertTrue(all('output_directory' not in cfg for cfg in normalized))
            self.assertEqual(launcher.output_directory(list(reversed(normalized))),
                             second_base / '03-RESULTS' / 'DASHBOARD')

    def test_generation_uses_first_base_and_keeps_phase_timings(self):
        before = {path.relative_to(self.base): path.read_bytes()
                  for path in self.base.rglob('*') if path.is_file()}
        payload = {**self.payload, 'output_directory': str(self.previous_output)}
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            launcher._run_generation_job('fixed-output-timings', payload)
        job = launcher.job_snapshot('fixed-output-timings')
        self.assertEqual(job['status'], 'complete', job.get('error'))
        result = job['result']
        self.assertEqual(Path(result['report_path']), self.default_output / 'dashboard.html')
        self.assertTrue(Path(result['json_path']).is_file())
        self.assertFalse(self.previous_output.exists())
        for relative, content in before.items():
            self.assertEqual((self.base / relative).read_bytes(), content)
        cache = self.default_output / '.jamal_cache'
        self.assertEqual(result['cache_directory'], str(cache))
        self.assertEqual(job['output_directory'], str(self.default_output))
        timings = result['timings_seconds']
        self.assertEqual(set(timings), {'scanning', 'polars', 'drag_rise', 'distributions',
                                       'derived', 'json', 'html', 'validation', 'publish'})
        self.assertTrue(all(value >= 0 for value in timings.values()))
        self.assertLessEqual(sum(timings.values()), result['elapsed_seconds'])
        self.assertEqual(job['timings_seconds'], timings)
        manifest = json.loads((cache / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['timings_seconds'], timings)
        self.assertEqual(manifest['cache_directory'], str(cache))
        self.assertIn('Timing · distributions:', job['log'])
        self.assertIn(str(cache), job['log'])

    def test_clear_cache_ignores_retired_override_and_preserves_other_files(self):
        previous_cache = self.previous_output / '.jamal_cache'
        source_cache = self.default_output / '.jamal_cache'
        for directory in (previous_cache, source_cache):
            directory.mkdir(parents=True)
            (directory / 'cache_entry').write_text('cache')
        report = self.default_output / 'dashboard.html'
        report.write_text('keep report')
        unrelated = self.default_output / 'other_data'
        unrelated.write_text('keep other data')
        result = launcher.clear_cache({**self.payload, 'output_directory': str(self.previous_output)})
        self.assertEqual(result['cache_directory'], str(source_cache))
        self.assertFalse(source_cache.exists())
        self.assertEqual((previous_cache / 'cache_entry').read_text(), 'cache')
        self.assertEqual(report.read_text(), 'keep report')
        self.assertEqual(unrelated.read_text(), 'keep other data')


if __name__ == '__main__':
    unittest.main()
