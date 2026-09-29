"""Scientific cache invalidation and network metadata regression checks."""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import jamal_distributions as dist


GEOMETRY = [[0., 0.], [.5, .1], [1., 0.], [.5, -.1], [0., 0.]]


def write_curve(path, rows):
    path.write_text('$ ABSCISSA ORDINATE\n'
                    + '\n'.join(f'{x:.16g} {value:.16g}' for x, value in rows)
                    + '\n*END\n', encoding='utf-8')


class TopologyCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='jamal_cache_')
        self.addCleanup(self.temporary.cleanup)
        self.cache = Path(self.temporary.name) / 'cache'
        self.geometry = copy.deepcopy(GEOMETRY)

    def prime(self):
        topology = dist.cached_topology(self.geometry, self.cache)
        target, = (self.cache / 'topology').glob('*.json')
        return topology, target

    def test_identical_ordered_geometry_reuses_validation_in_memory_and_on_disk(self):
        memo, counts = {}, {}
        with patch.object(dist, 'section_topology', wraps=dist.section_topology) as validate:
            expected = dist.cached_topology(self.geometry, self.cache, memo=memo, counts=counts)
            actual = dist.cached_topology(copy.deepcopy(self.geometry), self.cache,
                                          memo=memo, counts=counts)
            self.assertEqual(actual, expected)
            self.assertEqual(validate.call_count, 1)
        self.assertEqual(counts, {'validated': 1, 'reused': 1})
        with patch.object(dist, 'section_topology', side_effect=AssertionError('geometry revalidated')):
            self.assertEqual(dist.cached_topology(self.geometry, self.cache), expected)

    def test_coordinate_and_point_order_changes_require_new_validation(self):
        self.prime()
        changed = copy.deepcopy(self.geometry)
        changed[1][1] += .025
        reordered = list(reversed(self.geometry))
        expected = [dist.section_topology(geometry) for geometry in (changed, reordered)]
        with patch.object(dist, 'section_topology', wraps=dist.section_topology) as validate:
            for geometry, topology in zip((changed, reordered), expected):
                self.assertEqual(dist.cached_topology(geometry, self.cache), topology)
            # Each changed geometry must invoke validation even though its X range is unchanged.
            self.assertEqual(validate.call_count, 2)
        self.assertEqual(len(list((self.cache / 'topology').glob('*.json'))), 3)

    def test_force_and_algorithm_version_rebuild_persistent_validation(self):
        expected, _ = self.prime()
        with patch.object(dist, 'section_topology', wraps=dist.section_topology) as validate:
            self.assertEqual(dist.cached_topology(self.geometry, self.cache, force=True), expected)
            self.assertEqual(validate.call_count, 1)
        with patch.object(dist, 'TOPOLOGY_CACHE_VERSION', dist.TOPOLOGY_CACHE_VERSION + 1), \
             patch.object(dist, 'section_topology', wraps=dist.section_topology) as validate:
            self.assertEqual(dist.cached_topology(self.geometry, self.cache), expected)
            self.assertEqual(validate.call_count, 1)
            dist.cached_topology(self.geometry, self.cache)
            self.assertEqual(validate.call_count, 1)

    def test_corrupt_truncated_and_invalid_cache_records_are_revalidated(self):
        expected, target = self.prime()
        original = json.loads(target.read_text(encoding='utf-8'))
        damaged = copy.deepcopy(original)
        damaged['topology'][0]['direction'] *= -1  # Valid shape, stale checksum.
        invalid = copy.deepcopy(original)
        invalid['topology'][0]['surfaces']['upper'] = [len(self.geometry)]
        invalid['checksum'] = hashlib.sha256(json.dumps(
            invalid['topology'], separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
        missing = copy.deepcopy(original)
        del missing['checksum']
        for record in ('{"version":', 'null', json.dumps(damaged), json.dumps(invalid), json.dumps(missing)):
            with self.subTest(record=record[:100]):
                target.write_text(record, encoding='utf-8')
                with patch.object(dist, 'section_topology', wraps=dist.section_topology) as validate:
                    self.assertEqual(dist.cached_topology(self.geometry, self.cache), expected)
                    self.assertEqual(validate.call_count, 1)
                # A successful fallback replaces the damaged record with reusable data.
                with patch.object(dist, 'section_topology', side_effect=AssertionError('repair not cached')):
                    self.assertEqual(dist.cached_topology(self.geometry, self.cache), expected)

    def test_unwritable_cache_does_not_remove_valid_pressure_loads(self):
        expected = dist.section_topology(self.geometry)
        counts = {}
        with patch.object(dist.tempfile, 'mkstemp', side_effect=PermissionError('read-only cache')):
            topology = dist.cached_topology(self.geometry, self.cache, counts=counts)
        self.assertEqual(topology, expected)
        self.assertEqual(counts, {'validated': 1, 'write_failed': 1})
        points = [[x, 100000. + 2000. * x] for x, _ in self.geometry]
        pressure = dist.pressure_section(points, self.geometry, 100000., 2000., topology=topology)
        self.assertAlmostEqual(pressure['fx'], 200.)  # q * diamond area * dCp/dx
        self.assertAlmostEqual(pressure['fz'], 0.)

    def test_invalid_geometry_is_rejected_and_only_rechecked_once_per_run(self):
        crossing = [[0., 0.], [1., .2], [0., .2], [.8, 0.], [0., 0.]]
        memo = {}
        with patch.object(dist, 'section_topology', wraps=dist.section_topology) as validate:
            for _ in range(2):
                with self.assertRaises(ValueError):
                    dist.cached_topology(crossing, self.cache, memo=memo)
            self.assertEqual(validate.call_count, 1)
        self.assertFalse((self.cache / 'topology').exists())


class RawCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='jamal_raw_')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cache = self.root / 'cache'
        self.path = self.root / 'section_state1_station0'
        write_curve(self.path, GEOMETRY)

    def test_inventory_fingerprint_avoids_remote_stat_and_resolve_on_warm_read(self):
        expected, source = dist.cached_parse(self.path, 'geometry', self.cache, False,
                                             {'parsed': 0, 'cached': 0})
        counts = {'parsed': 0, 'cached': 0}
        with patch.object(Path, 'stat', side_effect=AssertionError('remote stat repeated')), \
             patch.object(Path, 'resolve', side_effect=AssertionError('remote resolve repeated')), \
             patch.object(dist, 'parse_curve', side_effect=AssertionError('raw data reparsed')):
            actual, fingerprint = dist.cached_parse(self.path, 'geometry', self.cache, False,
                                                    counts, source=source)
        self.assertEqual(actual, expected)
        self.assertEqual(fingerprint, source)
        self.assertEqual(counts, {'parsed': 0, 'cached': 1})

    def test_changed_inventory_fingerprint_invalidates_cached_raw_coordinates(self):
        _, source = dist.cached_parse(self.path, 'geometry', self.cache, False,
                                      {'parsed': 0, 'cached': 0})
        changed = copy.deepcopy(GEOMETRY)
        changed[1][1] = .125
        write_curve(self.path, changed)
        latest = dist.fingerprint(self.path, stat=os.stat(self.path), resolved_path=source['path'])
        counts = {'parsed': 0, 'cached': 0}
        with patch.object(Path, 'resolve', side_effect=AssertionError('remote resolve repeated')):
            actual, fingerprint = dist.cached_parse(self.path, 'geometry', self.cache, False,
                                                    counts, source=latest)
        self.assertEqual(actual, changed)
        self.assertEqual(fingerprint, latest)
        self.assertEqual(counts, {'parsed': 1, 'cached': 0})

    def test_source_change_during_parse_is_rejected_without_caching_mixed_data(self):
        source = dist.fingerprint(self.path)
        original = dist.parse_curve

        def racing_parse(path):
            rows = original(path)
            with path.open('a', encoding='utf-8') as output:
                output.write('\n')
            return rows

        counts = {'parsed': 0, 'cached': 0}
        with patch.object(dist, 'parse_curve', side_effect=racing_parse):
            with self.assertRaisesRegex(ValueError, 'source changed during parsing'):
                dist.cached_parse(self.path, 'geometry', self.cache, False, counts, source=source)
        self.assertEqual(counts, {'parsed': 0, 'cached': 0})
        self.assertFalse(self.cache.exists())


class LoaderCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='jamal_loader_')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cache = self.root / 'cache'
        self.component = self.root / '03-RESULTS/DISTCLCP/POLAR-001/WING'
        self.component.mkdir(parents=True)
        self.info = {'meta': {'p': 100000., 'qdin': 2000., 'bref': 10., 'mach': .2, 'reynolds': 1e6},
                     'cases': [{'case': '0001', 'alpha': 0., 'beta': 0., 'mach': .2, 'reynolds': 1e6}]}
        self.configurations = [{'label': 'Wing', 'polars': [1], 'base_directory': str(self.root),
                                'runs_directory': str(self.root / '02-RUNS')}]
        self.add_station(0)

    def add_station(self, station):
        write_curve(self.component / f'section_state1_station{station}', GEOMETRY)
        # Cp = x - 10z gives Fx = q*area, Fz = -10*q*area, independently of cache.
        write_curve(self.component / f'cp_dist_state1_station{station}',
                    [[x, 100000. + 2000.*(x - 10*z)] for x, z in GEOMETRY])

    def load(self):
        data = dist.read_distributions(self.configurations, [], lambda _: self.info, self.cache)
        self.assertEqual(data['issues'], [])
        return data

    def test_loader_shares_geometry_validation_between_stations_and_updates(self):
        self.add_station(1)
        with patch.object(dist, 'section_topology', wraps=dist.section_topology) as validate:
            first = self.load()
            self.assertEqual(validate.call_count, 1)
        self.assertEqual(first['topology_cache'], {'validated': 1, 'reused': 1})
        with patch.object(dist, 'section_topology', side_effect=AssertionError('unchanged geometry revalidated')), \
             patch.object(dist, 'parse_curve', side_effect=AssertionError('unchanged file reparsed')):
            second = self.load()
        self.assertEqual(second['series'], first['series'])
        self.assertEqual(second['topology_cache'], {'cached': 1, 'reused': 1})

    def test_pressure_reference_dynamic_pressure_and_alpha_always_refresh_physics(self):
        original = self.load()['series'][0]
        original_span = original['span'][0]
        self.assertAlmostEqual(original_span['fx'], 200.)
        self.assertAlmostEqual(original_span['fz'], -2000.)
        self.assertAlmostEqual(original_span['cl'], 1.)
        self.info['meta']['p'] += 1000.
        self.info['meta']['qdin'] *= 2
        self.info['cases'][0]['alpha'] = 30.
        with patch.object(dist, 'section_topology', side_effect=AssertionError('geometry revalidated')), \
             patch.object(dist, 'parse_curve', side_effect=AssertionError('unchanged pressure reparsed')):
            refreshed = self.load()['series'][0]
        span = refreshed['span'][0]
        self.assertEqual(refreshed['cp'][0]['values'],
                         [(cp - .5) / 2 for cp in original['cp'][0]['values']])
        self.assertAlmostEqual(span['fx'], 200.)
        self.assertAlmostEqual(span['fz'], -2000.)
        expected_lift = 200.*math.sin(math.radians(30)) + 2000.*math.cos(math.radians(30))
        self.assertAlmostEqual(span['lift'], expected_lift)
        self.assertAlmostEqual(span['cl'], expected_lift / 4000.)

    def test_scandir_ignores_unrelated_names_symlinks_and_nonfiles(self):
        unrelated = {'notes.txt', 'total_force_state1', 'cp_dist_state1_station0.bak'}
        for name in unrelated | {'section_state2_station0', 'cp_dist_state1_station99'}:
            (self.component / name).write_text('must not be read', encoding='utf-8')
        (self.component / 'cp_dist_state1_station98').mkdir()
        original_scandir = os.scandir

        class Snapshot:
            def __init__(self, entries):
                self.entries = entries
            def __enter__(self):
                return iter(self.entries)
            def __exit__(self, *args):
                return False

        class Entry:
            def __init__(self, actual):
                self.actual, self.name, self.path = actual, actual.name, actual.path
            def is_symlink(self):
                if self.name in unrelated:
                    raise AssertionError('Metadata requested for an unrelated filename')
                # Exercise the symlink branch without requiring Windows symlink privileges.
                return self.name == 'cp_dist_state1_station99' or self.actual.is_symlink()
            def is_file(self, **kwargs):
                if self.name == 'cp_dist_state1_station99':
                    raise AssertionError('Symlink should be skipped before checking its target')
                return self.actual.is_file(**kwargs)
            def stat(self, **kwargs):
                return self.actual.stat(**kwargs)

        def directory_entries(path):
            if Path(path) != self.component:
                return original_scandir(path)
            with original_scandir(path) as entries:
                return Snapshot([Entry(entry) for entry in entries])

        with patch.object(dist.os, 'scandir', side_effect=directory_entries), \
             patch.object(dist, 'parse_curve', wraps=dist.parse_curve) as parse:
            data = self.load()
        self.assertEqual(data['counts'], {'parsed': 2, 'cached': 0})
        self.assertEqual({call.args[0].name for call in parse.call_args_list},
                         {'section_state1_station0', 'cp_dist_state1_station0'})


if __name__ == '__main__':
    unittest.main()
