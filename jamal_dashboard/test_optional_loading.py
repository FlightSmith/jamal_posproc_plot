"""Optional inputs are genuinely skipped, including discovery and warm caches."""
import builtins
import contextlib
import io
import itertools
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import jamal_dashboard_launcher_v25 as launcher


engine = launcher.ENGINE
FIXTURE = Path(__file__).parent / 'JAMAL_SYNTHETIC_CFD'
FLAGS = ('load_convergence', 'load_distributions', 'load_drag_rise')


class OptionalLoadingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='jamal_optional_')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name) / 'CFD'
        # Copy only the inputs under test; never copy reports, screenshots or caches.
        for relative in ('02-RUNS/POLAR-001', '03-RESULTS/DISTCLCP/POLAR-001',
                         '03-RESULTS/DRAG-RISE/BASELINE'):
            shutil.copytree(FIXTURE / relative, self.base / relative,
                            ignore=shutil.ignore_patterns('VTAIL', 'DASHBOARD', '.jamal_cache'))
        adf = self.base / '03-RESULTS/ADF'
        adf.mkdir(parents=True)
        shutil.copyfile(FIXTURE / '03-RESULTS/ADF/POLAR-001.adf', adf / 'POLAR-001.adf')
        self.payload = {'configurations': [{
            'label': 'Synthetic', 'base_directory': str(self.base), 'polars': [1],
            'drag_rise_dirs': ['BASELINE'], 'distribution_input': 'cp',
        }]}
        self.output = self.base / '03-RESULTS/DASHBOARD'
        self.generation = 0

    def generate(self, **options):
        self.generation += 1
        identifier = f'optional-{id(self)}-{self.generation}'
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            launcher._run_generation_job(identifier, {**self.payload, **options})
        job = launcher.job_snapshot(identifier)
        self.assertEqual(job['status'], 'complete', job.get('error'))
        report = json.loads(Path(job['result']['json_path']).read_text(encoding='utf-8'))
        return report, job['result']

    @contextlib.contextmanager
    def forbid_optional_access(self, **options):
        """Fail even if a reader catches an access exception and emits a warning."""
        attempts = []

        def check(path):
            if not isinstance(path, (str, bytes, os.PathLike)):
                return
            name = os.fsdecode(path).replace('\\', '/').lower()
            parts = name.split('/')
            forbidden = ((not options.get('load_distributions', True) and 'distclcp' in parts)
                         or (not options.get('load_drag_rise', True) and 'drag-rise' in parts)
                         or (not options.get('load_convergence', True)
                             and (parts[-1] == 'fluent_log' or parts[-1].endswith('.trn')
                                  or 'transcript' in parts[-1])))
            if forbidden:
                attempts.append(name)
                raise AssertionError(f'Disabled input accessed: {path}')

        def guarded(function):
            def wrapper(path, *args, **kwargs):
                check(path)
                return function(path, *args, **kwargs)
            return wrapper

        with contextlib.ExitStack() as stack:
            for owner, attribute in ((Path, 'stat'), (Path, 'open'), (Path, 'iterdir'),
                                     (os, 'scandir'), (builtins, 'open')):
                stack.enter_context(patch.object(owner, attribute,
                                                guarded(getattr(owner, attribute))))
            if not options.get('load_convergence', True):
                stack.enter_context(patch.object(engine, 'find_fluent_log',
                    side_effect=AssertionError('Disabled Fluent discovery called')))
                stack.enter_context(patch.object(engine, 'process_polar_convergence',
                    side_effect=AssertionError('Disabled Fluent parser called')))
            if not options.get('load_distributions', True):
                stack.enter_context(patch.object(engine.jamal_distributions, 'read_distributions',
                    side_effect=AssertionError('Disabled distribution loader called')))
            if not options.get('load_drag_rise', True):
                stack.enter_context(patch.object(engine, 'read_drag_rise_file',
                    side_effect=AssertionError('Disabled drag-rise parser called')))
                stack.enter_context(patch.object(launcher, 'shallow_drag_rise_listing',
                    side_effect=AssertionError('Disabled drag-rise discovery called')))
            yield
        self.assertEqual(attempts, [], 'Disabled input access was swallowed by a reader')

    def assert_optional_content(self, report, options):
        self.assertEqual(bool(report['history']), options['load_convergence'])
        self.assertEqual(bool(report['results']), options['load_convergence'])
        self.assertEqual(bool(report['distributions']['series']), options['load_distributions'])
        self.assertEqual(bool(report['drag_rise']['curves']), options['load_drag_rise'])
        self.assertEqual(report['provenance']['load_options'], options)
        if not options['load_convergence']:
            self.assertFalse(any('fluent_log' in row and row['fluent_log']
                                 for row in report['provenance']['run_files']))
            self.assertFalse(any(row['check'] == 'Convergence unavailable'
                                 for row in report['integrity_checks']))
        if not options['load_distributions']:
            self.assertEqual(report['provenance']['distribution_sources'], [])
        if not options['load_drag_rise']:
            self.assertEqual(report['provenance']['drag_rise_files'], [])

    def test_defaults_preserve_all_three_optional_modules(self):
        configurations = launcher._normalize_configurations(self.payload)
        self.assertTrue(all(configurations[0][name] is True for name in FLAGS))
        report, _ = self.generate()
        self.assert_optional_content(report, dict.fromkeys(FLAGS, True))

    def test_each_flag_combination_preserves_adf_references_and_static_margin(self):
        baseline, _ = self.generate()
        self.assertTrue(baseline['adf']['static_margin'])
        reference = baseline['summaries'][0]
        for values in itertools.product((False, True), repeat=3):
            options = dict(zip(FLAGS, values))
            with self.subTest(**options), self.forbid_optional_access(**options):
                report, _ = self.generate(**options, force_full_rebuild=True)
                self.assert_optional_content(report, options)
                self.assertEqual(report['adf'], baseline['adf'])
                self.assertEqual(report['summaries'][0]['meta'], reference['meta'])
                self.assertEqual(report['summaries'][0]['deflections'], reference['deflections'])

    def test_all_disabled_skips_discovery_and_source_access_with_primed_caches(self):
        self.generate()
        options = dict.fromkeys(FLAGS, False)
        for force in (False, True):
            with self.subTest(force=force), self.forbid_optional_access(**options):
                scan = launcher.scan_base_directory(str(self.base), load_drag_rise=False)
                self.assertEqual([row['number'] for row in scan['polars']], [1])
                self.assertEqual(scan['drag_rise_directories'], [])
                report, _ = self.generate(**options, force_full_rebuild=force)
                self.assert_optional_content(report, options)

    def test_skipping_inputs_then_reenabling_reads_changes_and_reuses_unchanged_cache(self):
        before, _ = self.generate()
        options = dict.fromkeys(FLAGS, False)
        with self.forbid_optional_access(**options):
            self.generate(**options)

        log = self.base / '02-RUNS/POLAR-001/FLUENT_LOG'
        lines = log.read_text().splitlines()
        # Change a final residual, preserving the actual Fluent transcript structure.
        for index in range(len(lines) - 1, -1, -1):
            fields = lines[index].split()
            if fields and fields[0] == '1200':
                fields[1] = '9.0000000000E-04'
                lines[index] = ' '.join(fields)
                break
        else:
            self.fail('Expected final Fluent row missing from fixture')
        log.write_text('\n'.join(lines) + '\n')

        pressure = self.base / '03-RESULTS/DISTCLCP/POLAR-001/WING/cp_dist_state1_station0.000'
        lines = pressure.read_text().splitlines()
        marker = next(index for index, line in enumerate(lines) if 'ABSCISSA' in line)
        x, value = lines[marker + 2].split()
        lines[marker + 2] = f'{x} {float(value) - 0.15:.12E}'
        pressure.write_text('\n'.join(lines) + '\n')

        drag = self.base / '03-RESULTS/DRAG-RISE/BASELINE/drag_rise_cl0p20.dat'
        lines = drag.read_text().splitlines()
        columns = lines[0].split()
        fields = lines[-1].split()
        fields[columns.index('CDS')] = '0.123456789'
        lines[-1] = ' '.join(fields)
        drag.write_text('\n'.join(lines) + '\n')
        # Ensure change detection remains deterministic on coarse timestamp filesystems.
        for source in (log, pressure, drag):
            stat = source.stat()
            os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))

        with self.forbid_optional_access(**options):
            skipped, _ = self.generate(**options)
            self.assert_optional_content(skipped, options)
        after, result = self.generate()
        self.assert_optional_content(after, dict.fromkeys(FLAGS, True))
        self.assertNotEqual(after['history'], before['history'])
        self.assertNotEqual(after['results'], before['results'])
        self.assertNotEqual(after['distributions']['series'], before['distributions']['series'])
        self.assertNotEqual(after['drag_rise']['curves'], before['drag_rise']['curves'])
        self.assertEqual(after['adf'], before['adf'])
        self.assertEqual(result['parsed_polars'], 1)

        with patch.object(engine, 'process_polar_convergence',
                          side_effect=AssertionError('Reparsed unchanged Fluent log')), \
             patch.object(engine, 'read_drag_rise_file',
                          side_effect=AssertionError('Reparsed unchanged drag-rise input')):
            warm, result = self.generate()
        self.assertEqual(result['reused_polars'], 1)
        for key in ('adf', 'history', 'results', 'drag_rise'):
            self.assertEqual(warm[key], after[key])
        self.assertEqual(warm['distributions']['series'], after['distributions']['series'])

    def test_removed_output_override_is_ignored_in_old_setup_files(self):
        external = Path(self.temp.name) / 'Obsolete report destination'
        normalized = launcher._normalize_configurations({**self.payload, 'output_directory': str(external)})
        self.assertEqual(launcher.output_directory(normalized), self.output)
        report, result = self.generate(output_directory=str(external), **dict.fromkeys(FLAGS, False))
        self.assertEqual(Path(result['report_path']), self.output / 'dashboard.html')
        self.assertFalse(external.exists())
        self.assertTrue(report['adf']['curves'])


if __name__ == '__main__':
    unittest.main()
