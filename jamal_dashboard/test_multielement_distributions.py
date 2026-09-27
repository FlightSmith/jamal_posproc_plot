"""Analytical checks for separate pressure contours with overlapping X ranges.

The synthetic main-element recess and aft element reproduce the topology shown
in the supplied Excel screenshots; these are not transcribed production data.
"""
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import jamal_distributions as dist


ROOT = Path(__file__).parent
MAIN = [
    (0, 0), (.25, .10), (.8, .08), (1, .05),
    (.9, .05), (.9, -.05), (1, -.05), (.8, -.08),
    (.25, -.10), (0, 0),
]
FLAP = [(1.4, 0), (1.15, -.03), (.95, 0), (1.15, .03), (1.4, 0)]


def area(contour):
    """Geometric area, independent of the pressure integration implementation."""
    return abs(sum(x0*z1-x1*z0 for (x0, z0), (x1, z1)
                   in zip(contour, contour[1:]))) / 2


def rotate_closed(contour, offset):
    points = contour[:-1]
    points = points[offset:] + points[:offset]
    return points + points[:1]


def write_curve(path, rows):
    path.write_text('*KEYWORD\n*DEFINE_CURVE_TITLE\nSynthetic multi-element\n'
                    '$ ABSCISSA ORDINATE\n'
                    + '\n'.join(f'{x:.16g} {value:.16g}' for x, value in rows)
                    + '\n*END\n', encoding='utf-8')


class MultiElementPressureTests(unittest.TestCase):
    p, q = 100000., 2000.

    def section(self, contours, pressure_functions=None):
        if pressure_functions is None:
            pressure_functions = [lambda x, z: .4*x-.7*z+.2] * len(contours)
        geometry, pressures = [], []
        for contour, cp in zip(contours, pressure_functions):
            geometry.extend(contour)
            pressures.extend((x, self.p+self.q*cp(x, z)) for x, z in contour)
        return dist.pressure_section(pressures, geometry, self.p, self.q)

    def test_recess_and_overlapping_x_ranges_have_independent_analytic_forces(self):
        main = rotate_closed(MAIN, 1)  # Starts on a surface, not at an extremum.
        section = self.section([main, FLAP])
        self.assertEqual(len(section['elements']), 2)
        self.assertNotIn('surfaces', section)
        total_area = area(MAIN)+area(FLAP)
        self.assertAlmostEqual(section['fx'], self.q*.4*total_area, places=8)
        self.assertAlmostEqual(section['fz'], self.q*-.7*total_area, places=8)
        for index, (element, contour) in enumerate(zip(section['elements'], [main, FLAP]), 1):
            self.assertEqual(element['id'], f'element-{index}')
            self.assertEqual(element['name'], f'Element {index}')
            self.assertAlmostEqual(element['fx'], self.q*.4*area(contour), places=8)
            self.assertAlmostEqual(element['fz'], self.q*-.7*area(contour), places=8)
            self.assertIn('upper', element['surfaces'])
            self.assertIn('lower', element['surfaces'])
            coordinates = list(zip(element['airfoil']['x'], element['airfoil']['ordinate']))
            self.assertEqual(len(coordinates), len(element['values']))
            for (x, z), cp in zip(coordinates, element['values']):
                self.assertAlmostEqual(cp, .4*x-.7*z+.2, places=10)
            plotted = {(round(x, 12), round(cp, 12))
                       for branch in element['surfaces'].values()
                       for x, cp in zip(branch['x'], branch['values'])}
            recorded = {(round(x, 12), round(cp, 12))
                        for x, cp in zip(element['x'], element['values'])}
            self.assertEqual(plotted, recorded, 'Every contour pressure must remain plotted')
            for side, sign in [('upper', 1), ('lower', -1)]:
                branch = element['surfaces'][side]
                for x, cp in zip(branch['x'], branch['values']):
                    inferred_z = (.4*x+.2-cp)/.7
                    self.assertGreaterEqual(sign*inferred_z, -1e-10)
        cove = section['elements'][0]
        geometry = list(zip(cove['airfoil']['x'], cove['airfoil']['ordinate']))
        self.assertIn((.9, .05), geometry)
        self.assertIn((.9, -.05), geometry)
        self.assertTrue(any(x0 == x1 == .9 and z0 != z1
                            for (x0, z0), (x1, z1) in zip(geometry, geometry[1:])))
        # Section x/c keeps the physical gap/overlap instead of rescaling each element.
        for element in section['elements']:
            for x, xc in zip(element['x'], element['xc']):
                self.assertAlmostEqual(xc, x/1.4)

    def test_separate_pressure_levels_and_third_contour_do_not_add_bridge_loads(self):
        third = [(2.2, .2), (2.0, .15), (1.8, .2), (2.0, .25), (2.2, .2)]
        levels = [-2., 1.5, 4.]
        section = self.section([rotate_closed(MAIN, 2), FLAP, third],
                               [lambda x, z, level=level: level for level in levels])
        self.assertEqual(len(section['elements']), 3)
        for element, level in zip(section['elements'], levels):
            self.assertAlmostEqual(element['fx'], 0, places=8)
            self.assertAlmostEqual(element['fz'], 0, places=8)
            self.assertTrue(all(abs(cp-level) < 1e-12 for cp in element['values']))
        self.assertAlmostEqual(section['fx'], 0, places=8)
        self.assertAlmostEqual(section['fz'], 0, places=8)

    def test_each_element_winding_and_start_point_are_independent(self):
        expected = self.section([MAIN, FLAP])
        for reverse_main, reverse_flap in [(True, False), (False, True), (True, True)]:
            contours = [rotate_closed(MAIN, 3), rotate_closed(FLAP, 2)]
            if reverse_main:
                contours[0] = list(reversed(contours[0]))
            if reverse_flap:
                contours[1] = list(reversed(contours[1]))
            section = self.section(contours)
            self.assertEqual(len(section['elements']), 2)
            self.assertAlmostEqual(section['fx'], expected['fx'], places=8)
            self.assertAlmostEqual(section['fz'], expected['fz'], places=8)
            for actual, original in zip(section['elements'], expected['elements']):
                self.assertAlmostEqual(actual['fx'], original['fx'], places=8)
                self.assertAlmostEqual(actual['fz'], original['fz'], places=8)

    def test_repeated_identical_points_do_not_create_empty_elements(self):
        main = rotate_closed(MAIN, 1)
        main = main[:1]+main[:1]+main[1:5]+main[4:5]+main[5:]
        flap = FLAP[:1]+FLAP
        section = self.section([main, flap])
        self.assertEqual(len(section['elements']), 2)
        total_area = area(MAIN)+area(FLAP)
        self.assertAlmostEqual(section['fx'], self.q*.4*total_area, places=8)
        self.assertAlmostEqual(section['fz'], self.q*-.7*total_area, places=8)

    def test_single_closed_contour_may_start_away_from_le_or_te(self):
        section = self.section([rotate_closed(MAIN, 2)])
        self.assertEqual(len(section['elements']), 1)
        self.assertEqual(section['surfaces'], section['elements'][0]['surfaces'])
        self.assertAlmostEqual(section['fx'], self.q*.4*area(MAIN), places=8)
        self.assertAlmostEqual(section['fz'], self.q*-.7*area(MAIN), places=8)

    def test_unclosed_second_element_and_self_crossing_contours_are_rejected(self):
        with self.assertRaises(ValueError):
            self.section([MAIN, FLAP[:-1]])
        # Unequal lobes avoid relying on a zero-area rejection.
        crossing = [(2, 0), (2.5, .2), (2, .2), (2.4, 0), (2, 0)]
        with self.assertRaises(ValueError):
            self.section([MAIN, crossing])

    def test_intersecting_elements_are_rejected(self):
        overlapping = [(x-.35, z) for x, z in FLAP]
        with self.assertRaises(ValueError):
            self.section([MAIN, overlapping])

    def test_pressure_geometry_pairing_still_required_at_element_boundary(self):
        geometry = MAIN+FLAP
        points = [[x, self.p+self.q*(.4*x-.7*z)] for x, z in geometry]
        with self.assertRaisesRegex(ValueError, 'point order'):
            dist.pressure_section(points[:-1], geometry, self.p, self.q)
        points[len(MAIN)][0] += .01
        with self.assertRaisesRegex(ValueError, 'point order'):
            dist.pressure_section(points, geometry, self.p, self.q)

    def test_loader_projects_combined_force_and_interpolates_matching_element_points(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            component = root/'03-RESULTS/DISTCLCP/POLAR-001/WING'
            component.mkdir(parents=True)
            run = root/'02-RUNS/POLAR-001'
            run.mkdir(parents=True)
            (run/'infout').write_text('synthetic; parsed values provided below', encoding='utf-8')
            geometry = rotate_closed(MAIN, 1)+FLAP[:1]+FLAP
            write_curve(component/'section_state1_station0', geometry)
            for state, multiplier in [(1, 1.), (2, 3.)]:
                write_curve(component/f'cp_dist_state{state}_station0',
                            [(x, self.p+self.q*multiplier*(.4*x-.7*z+.2)) for x, z in geometry])
                (component/f'total_force_state{state}').write_text('must not be parsed', encoding='utf-8')
            info = {'meta': {'p': self.p, 'qdin': self.q, 'bref': 10., 'mach': .2, 'reynolds': 1e6},
                    'cases': [{'case': str(index), 'alpha': alpha, 'beta': 0., 'mach': .2, 'reynolds': 1e6}
                              for index, alpha in [(1, 0.), (2, 10.)]]}
            configurations = [{'label': 'Synthetic multi-element', 'polars': [1],
                               'base_directory': str(root), 'runs_directory': str(root/'02-RUNS')}]
            with patch.object(dist, 'parse_force', side_effect=AssertionError('force file read')):
                data = dist.read_distributions(configurations, [], lambda _: info, root/'cache')
            self.assertEqual(data['issues'], [])
            self.assertEqual(data['counts'], {'parsed': 3, 'cached': 0})
            total_area = area(MAIN)+area(FLAP)
            for series, multiplier in zip(data['series'], [1., 3.]):
                section = series['span'][0]
                expected_fx = self.q*multiplier*.4*total_area
                expected_fz = self.q*multiplier*-.7*total_area
                expected_lift = expected_fx*math.sin(math.radians(series['alpha']))-expected_fz*math.cos(math.radians(series['alpha']))
                self.assertAlmostEqual(section['fx'], expected_fx, places=8)
                self.assertAlmostEqual(section['fz'], expected_fz, places=8)
                self.assertAlmostEqual(section['lift'], expected_lift, places=8)
                self.assertAlmostEqual(section['cl'], expected_lift/(self.q*1.4), places=8)
                self.assertEqual(len(series['cp'][0]['elements']), 2)
            adf = {'curves': [{'case_label': 'Synthetic multi-element', 'polar': 'POLAR-001', 'rows': [
                {'ALPHA': alpha, 'BETA': 0., 'MACH': .2, 'REYNOLDS': 1e6, 'CLS': cl}
                for alpha, cl in [(0., .2), (10., 1.)]]}]}
            dist.attach_global_lift(data, adf)
            node = shutil.which('node')
            self.assertIsNotNone(node, 'Install Node.js for target-distribution checks')
            script = r'''
const assert=require('node:assert/strict');
const {distributionAtTarget}=require(MODULE);
const states=STATES, before=JSON.stringify(states);
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-8, `${a} != ${b}`);
for(const [mode,target] of [['alpha',5],['cl',.6]]) {
  const result=distributionAtTarget(states,mode,target);
  assert.equal(result.error,null); const s=result.series;
  near(s.alpha,5); near(s.cl_global,.6);
  assert.equal(s.cp[0].elements.length,2);
  for(let j=0;j<2;j++) {
    const e=s.cp[0].elements[j], a=states[0].cp[0].elements[j], b=states[1].cp[0].elements[j];
    assert.equal(e.id,a.id); assert.deepEqual(e.airfoil,a.airfoil);
    assert.deepEqual(e.x,a.x); assert.deepEqual(e.xc,a.xc);
    assert.equal(e.values.length,a.values.length);
    e.values.forEach((value,i)=>near(value,(a.values[i]+b.values[i])/2));
    for(const [surface,branch] of Object.entries(e.surfaces)) {
      assert.deepEqual(branch.x,a.surfaces[surface].x);
      branch.values.forEach((value,i)=>near(value,(a.surfaces[surface].values[i]+b.surfaces[surface].values[i])/2));
    }
  }
  near(s.span[0].fx,EXPECTED_FX); near(s.span[0].fz,EXPECTED_FZ);
  const lift=EXPECTED_FX*Math.sin(5*Math.PI/180)-EXPECTED_FZ*Math.cos(5*Math.PI/180);
  near(s.span[0].lift,lift);near(s.span[0].cl,lift/(2000*1.4));
}
assert.equal(JSON.stringify(states),before);
'''.replace('MODULE', json.dumps(str(ROOT/'distribution_interpolation.js')))
            script = script.replace('STATES', json.dumps(data['series']))
            script = script.replace('EXPECTED_FX', f'({self.q*2*.4*total_area!r})')
            script = script.replace('EXPECTED_FZ', f'({self.q*2*-.7*total_area!r})')
            result = subprocess.run([node, '-e', script], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)


if __name__ == '__main__':
    unittest.main()
