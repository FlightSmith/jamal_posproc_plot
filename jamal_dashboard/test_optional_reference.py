"""Optional Fluent loading retains aerodynamic reference metadata without log I/O."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_baseline import engine, make_fixture


class OptionalReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='jamal_reference_')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        make_fixture(self.base)
        self.run = self.base / '02-RUNS' / 'POLAR-001'
        self.adf = self.base / '03-RESULTS' / 'ADF'
        self.config = engine.CaseConfig('Baseline', self.adf, [1])

    def process(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return engine.process_optional_convergence('Baseline', 'POLAR-001', self.run, **kwargs)

    def adf_data(self):
        path = self.adf / 'POLAR-001.adf'
        polar = engine.PolarData('Baseline', 1, path, engine.read_polar_file(path), 'ALPHA')
        return engine.make_adf_plot_rows([polar], engine.compute_all_static_margin([polar]))

    def test_disabled_fluent_retains_reference_deflections_and_case_count_without_log_access(self):
        infout = self.run / 'infout'
        infout.write_text(infout.read_text() + '\nFLP1: 15\nRUD1: -2\n')
        expected = engine.parse_infout(infout)
        with patch.object(engine, 'find_fluent_log', side_effect=AssertionError('Log discovery disabled')), \
             patch.object(engine, 'parse_fluent_log_named_columns', side_effect=AssertionError('Log parsing disabled')):
            summary, rows, history = self.process(load_convergence=False)
        self.assertEqual(summary['meta'], expected['meta'])
        self.assertEqual(summary['deflections'], {'FLP1': 15, 'RUD1': -2})
        self.assertEqual(summary['n_cases_infout'], 3)
        self.assertEqual(summary['n_history_blocks'], 0)
        self.assertTrue(summary['convergence_skipped'])
        self.assertNotIn('convergence_unavailable', summary)
        self.assertNotIn('fluent_log', summary['files'])
        self.assertIn('infout_modified', summary['files'])
        self.assertEqual(rows, [])
        self.assertEqual(history, {})
        checks = engine.build_integrity_checks([self.config], [summary], [], self.adf_data(), {'curves': []})
        self.assertEqual([row['severity'] for row in checks], ['PASS'])

    def test_default_still_loads_fluent_history(self):
        summary, rows, history = self.process()
        self.assertNotIn('convergence_skipped', summary)
        self.assertEqual(len(rows), 3)
        self.assertEqual(len(history), 3)
        self.assertEqual(Path(summary['files']['fluent_log']), self.run / 'FLUENT_LOG')

    def test_missing_infout_reports_reference_problem_without_false_fluent_or_case_warning(self):
        (self.run / 'infout').unlink()
        with patch.object(engine, 'find_fluent_log', side_effect=AssertionError('Log discovery disabled')):
            summary, rows, history = self.process(load_convergence=False)
        self.assertEqual(summary['meta'], {})
        self.assertIsNone(summary['n_cases_infout'])
        checks = engine.build_integrity_checks([self.config], [summary], rows, self.adf_data(), {'curves': []})
        self.assertEqual([row['check'] for row in checks], ['Reference metadata unavailable'])
        self.assertEqual(checks[0]['severity'], 'WARNING')
        self.assertIn('infout', checks[0]['details'])

    def test_real_case_count_mismatch_is_still_reported_when_fluent_disabled(self):
        summary, rows, history = self.process(load_convergence=False)
        data = self.adf_data()
        data['curves'][0]['rows'].pop()
        checks = engine.build_integrity_checks([self.config], [summary], rows, data, {'curves': []})
        self.assertEqual([row['check'] for row in checks], ['Case count mismatch'])

    def test_disabled_report_notice_and_actual_provenance_rendering(self):
        summary, rows, history = self.process(load_convergence=False)
        data = self.adf_data()
        provenance = engine.build_provenance([self.config], [summary], data, {'curves': []})
        provenance['load_options'] = {'load_convergence': False, 'load_distributions': False,
                                      'load_drag_rise': False}
        html = engine.make_html([summary], rows, history, data, {'curves': []}, provenance, [])
        self.assertIn('Not loaded for this dashboard: Cp/load distributions, Fluent convergence histories, drag rise.', html)
        self.assertNotIn('loadOptionsNotice', engine.make_html([], [], {}, {'curves': [], 'static_margin': []},
                                                             {'curves': []}, {}, []))
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node.js is required for provenance rendering checks')
        function = html[html.index('function drawProvenance()'):html.index('drawCoeffPlot = function(data, divId')]
        harness = '''const assert = require('node:assert/strict');
const tbody = {innerHTML:''};
const heading = {innerHTML:''};
const document = {getElementById:()=>heading,querySelector:()=>tbody};
'''
        checks = '''
drawProvenance();
assert(tbody.innerHTML.includes('<td>infout</td>'));
assert(!tbody.innerHTML.includes('<td>FLUENT_LOG</td>'));
provenanceData.run_files[0].fluent_log = '/real/log';
drawProvenance();
assert(tbody.innerHTML.includes('<td>FLUENT_LOG</td>'));
assert(tbody.innerHTML.includes('/real/log'));
'''
        result = subprocess.run([node, '-e', harness + 'const provenanceData=' + json.dumps(provenance) + ';\n' + function + checks],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
