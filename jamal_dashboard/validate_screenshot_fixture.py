"""Validate the screenshot-inspired fixture through the real dashboard reader.

Run from any directory: python validate_screenshot_fixture.py [fixture_directory]
Python dashboard dependencies and Node.js are required. Inputs are read-only;
the dashboard's parsing cache lives in a temporary directory for this check.
Expected forces come from the fixture manifest, with separate absolute-pressure
quadrature and affine-field area checks here. Screenshots are approximate source
material, so this verifies the synthetic data, not numerical agreement with CFD.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

import jamal_dashboard_launcher_v25 as launcher
import jamal_distributions as distributions


ROOT = Path(__file__).resolve().parent
DEFAULT_FIXTURE = ROOT / 'JAMAL_SYNTHETIC_MULTIELEMENT_SCREENSHOTS'


class Checks:
    def __init__(self):
        self.count = 0

    def require(self, condition, message):
        self.count += 1
        if not condition:
            raise AssertionError(message)

    def near(self, actual, expected, message, absolute=2e-7, relative=2e-8):
        self.require(isinstance(actual, (int, float)) and math.isfinite(actual)
                     and math.isclose(actual, expected, abs_tol=absolute, rel_tol=relative),
                     f'{message}: {actual!r} != {expected!r}')


def read_curve(path):
    """Deliberately independent of the dashboard's curve parser."""
    rows, active = [], False
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if 'ABSCISSA' in line.upper() and 'ORDINATE' in line.upper():
            active = True
            continue
        if active and line.strip().upper().startswith('*END'):
            return rows
        if active and line.strip() and not line.lstrip().startswith('$'):
            columns = line.split()
            if len(columns) != 2:
                raise ValueError(f'Invalid curve row in {path}: {line}')
            rows.append(tuple(float(value.replace('D', 'E').replace('d', 'e')) for value in columns))
    raise ValueError(f'Missing curve terminator: {path}')


def polygon_area(points):
    # Translate before area accumulation to retain small-area accuracy.
    ox, oz = points[0]
    shifted = [(x-ox, z-oz) for x, z in points]
    return math.fsum(a[0]*b[1]-b[0]*a[1]
                     for a, b in zip(shifted, shifted[1:]+shifted[:1]))/2


def absolute_pressure_force(points, pressure):
    """Panel outward normals; body X forward/Z down, section X aft/Z up."""
    sign = 1 if polygon_area(points) > 0 else -1
    fx, fz = [], []
    for i, a in enumerate(points):
        j = (i+1) % len(points)
        b = points[j]
        panel_pressure = (pressure[i]+pressure[j])/2
        fx.append(sign*panel_pressure*(b[1]-a[1]))
        fz.append(-sign*panel_pressure*(b[0]-a[0]))
    return math.fsum(fx), math.fsum(fz)


def curve_paths(base, polar, state, station):
    directory = base / f'03-RESULTS/DISTCLCP/{polar}/WING'
    # Do not depend on a particular textual spelling of negative/zero stations.
    def find(prefix):
        matches = [p for p in directory.glob(prefix+'*')
                   if math.isclose(float(p.name[len(prefix):]), station, abs_tol=1e-9)]
        if len(matches) != 1:
            raise AssertionError(f'{polar} {prefix}{station}: expected one source file, found {len(matches)}')
        return matches[0]
    return find('section_state1_station'), find(f'cp_dist_state{state}_station')


def interpolation_expectations(expected, raw_values):
    targets = []
    for polar in expected['polars']:
        name = f"POLAR-{polar['number']:03d}"
        states = sorted(polar['states'], key=lambda row: row['alpha'])
        requested = [('alpha', 3.0), ('cl', .3)]
        requested += [('alpha', state['alpha']) for state in states]
        for mode, value in requested:
            alpha = value
            if mode == 'cl':
                roots = [s['alpha'] for s in states if math.isclose(s['CLS'], value, abs_tol=1e-10)]
                for a, b in zip(states, states[1:]):
                    if min(a['CLS'], b['CLS']) < value < max(a['CLS'], b['CLS']):
                        candidate = a['alpha']+(b['alpha']-a['alpha'])*(value-a['CLS'])/(b['CLS']-a['CLS'])
                        if not any(math.isclose(candidate, root, abs_tol=1e-9) for root in roots):
                            roots.append(candidate)
                if not roots:
                    targets.append({'polar': name, 'mode': mode, 'value': value, 'outside': True})
                    continue
                if len(roots) != 1:
                    raise AssertionError(f'{name}: synthetic CL={value} should have one ALPHA solution')
                alpha = roots[0]
            left = max((s for s in states if s['alpha'] <= alpha+1e-10), key=lambda s: s['alpha'])
            right = min((s for s in states if s['alpha'] >= alpha-1e-10), key=lambda s: s['alpha'])
            weight = 0 if left is right else (alpha-left['alpha'])/(right['alpha']-left['alpha'])
            blend = lambda a, b: a+weight*(b-a)
            sections = []
            for a in left['sections']:
                b = next(s for s in right['sections'] if s['y'] == a['y'])
                fx, fz = blend(a['fx'], b['fx']), blend(a['fz'], b['fz'])
                lift = fx*math.sin(math.radians(alpha))-fz*math.cos(math.radians(alpha))
                av = raw_values[name, left['state'], a['y']]
                bv = raw_values[name, right['state'], a['y']]
                sections.append({'y': a['y'], 'fx': fx, 'fz': fz, 'lift': lift,
                                 'cl': lift/(expected['qdin']*expected['chord']),
                                 'values': [blend(u, v) for u, v in zip(av, bv)],
                                 'elements': [{k: blend(u[k], v[k]) for k in ('fx', 'fz')}
                                              for u, v in zip(a['elements'], b['elements'])]})
            targets.append({'polar': name, 'mode': mode, 'value': value, 'alpha': alpha,
                            'weight': weight, 'states': [left['state']] if left is right else [left['state'], right['state']],
                            'cl_global': blend(left['CLS'], right['CLS']), 'sections': sections})
    return targets


def check_javascript(series, targets):
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Node.js is required to validate the actual target-interpolation code.')
    script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs');
const {distributionAtTarget}=require(process.argv[1]);
const input=JSON.parse(fs.readFileSync(0,'utf8'));let checks=0;
const near=(a,b,message)=>{checks++;assert.ok(Number.isFinite(a)&&Math.abs(a-b)<=2e-7+2e-8*Math.abs(b),`${message}: ${a} != ${b}`);};
const before=JSON.stringify(input.series);
for(const target of input.targets) {
  const states=input.series.filter(s=>s.polar===target.polar),result=distributionAtTarget(states,target.mode,target.value);
  if(target.outside) {assert.equal(result.series,null);assert.match(result.error,/outside/);checks++;continue;}
  assert.equal(result.error,null);assert.deepEqual(result.diagnostics,[]);checks+=2;
  const s=result.series;near(s.alpha,target.alpha,'ALPHA');near(s.cl_global,target.cl_global,'global CLS');
  near(s.interpolation.weight,target.weight,'weight');assert.deepEqual(s.source_states,target.states);checks++;
  assert.equal(s.interpolated,target.states.length>1);checks++;
  assert.equal(s.span.length,target.sections.length);assert.equal(s.cp.length,target.sections.length);checks+=2;
  for(const expected of target.sections) {
    const span=s.span.find(p=>p.y===expected.y),cp=s.cp.find(p=>p.y===expected.y);
    for(const key of ['fx','fz','lift','cl']) near(span[key],expected[key],`${target.polar} ${key}`);
    assert.equal(cp.values.length,603);assert.equal(cp.elements.length,2);checks+=2;
    cp.values.forEach((value,i)=>near(value,expected.values[i],'ordered Cp'));
    let offset=0;
    cp.elements.forEach((element,i)=>{
      assert.equal(element.values.length,[309,294][i]);checks++;
      for(const key of ['fx','fz']) near(element[key],expected.elements[i][key],`element ${i+1} ${key}`);
      element.values.forEach((value,j)=>near(value,expected.values[offset+j],'element Cp'));
      assert.ok(element.surfaces.upper&&element.surfaces.lower);checks++;
      for(const [name,branch] of Object.entries(element.surfaces)) {
        const source=states.find(t=>t.state===target.states[0]).cp.find(p=>p.y===expected.y).elements[i].surfaces[name];
        const end=states.find(t=>t.state===target.states.at(-1)).cp.find(p=>p.y===expected.y).elements[i].surfaces[name];
        assert.deepEqual(branch.x,source.x);checks++;
        branch.values.forEach((value,j)=>near(value,source.values[j]+target.weight*(end.values[j]-source.values[j]),'surface Cp'));
      }
      offset+=element.values.length;
    });
    assert.ok(cp.elements[0].surfaces['trailing edge / cove']);checks++;
    assert.equal(cp.elements[1].x[0],cp.elements[1].x[1]);checks++;
    assert.equal(cp.elements[1].airfoil.ordinate[0],cp.elements[1].airfoil.ordinate[1]);checks++;
  }
}
assert.equal(JSON.stringify(input.series),before);checks++;
process.stdout.write(JSON.stringify({checks,targets:input.targets.length}));
"""
    result = subprocess.run([node, '-e', script, str(ROOT/'distribution_interpolation.js')],
                            input=json.dumps({'series': series, 'targets': targets}, allow_nan=False),
                            text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(f'JavaScript interpolation validation failed:\n{result.stdout}\n{result.stderr}')
    return json.loads(result.stdout)


def validate(fixture=DEFAULT_FIXTURE, output=None):
    fixture = Path(fixture).resolve()
    expected = json.loads((fixture/'expected_values.json').read_text(encoding='utf-8'))
    base = fixture if (fixture/'02-RUNS').is_dir() else fixture/'CFD'
    check, raw_values = Checks(), {}
    check.near(expected['qdin'], .2*expected['p'], 'Selected qdin = 0.2 p convention')
    hashes = json.loads((fixture/'SHA256SUMS.json').read_text(encoding='utf-8'))
    for relative, digest in hashes.items():
        check.require(hashlib.sha256((fixture/relative).read_bytes()).hexdigest() == digest,
                      f'Synthetic source checksum changed: {relative}')
    configuration = launcher._normalize_configurations({'configurations': [{
        'label': 'Screenshot synthetic validation', 'base_directory': str(base),
        'polars': [p['number'] for p in expected['polars']], 'distribution_input': 'pressure'}]})
    with tempfile.TemporaryDirectory(prefix='jamal_screenshot_validation_') as temporary:
        data = distributions.read_distributions(configuration, [], launcher.ENGINE.parse_infout, Path(temporary))
    check.require(not data['issues'], f"Distribution warnings: {data['issues']}")
    check.require(len(data['series']) == 15, 'Expected 3 POLARs x 5 states')
    with contextlib.redirect_stdout(io.StringIO()):
        polars = launcher.ENGINE.load_all_adf_polars([launcher.ENGINE.CaseConfig(
            label=configuration[0]['label'], directory=base/'03-RESULTS/ADF', polars=configuration[0]['polars'])])
        margins = launcher.ENGINE.compute_all_static_margin(polars)
    check.require(len(polars) == 3, 'All three ADF polars must parse')
    adf = launcher.ENGINE.make_adf_plot_rows(polars, margins)
    distributions.attach_global_lift(data, adf)
    cancellation_checked = False
    for polar in expected['polars']:
        name = f"POLAR-{polar['number']:03d}"
        info = launcher.ENGINE.parse_infout(base/f'02-RUNS/{name}/infout')
        check.near(info['meta']['p'], expected['p'], f'{name} reference pressure')
        check.near(info['meta']['qdin'], expected['qdin'], f'{name} dynamic pressure')
        check.require([case['alpha'] for case in info['cases']] == polar['alphas'], f'{name} infout state order')
        adf_rows = next(curve['rows'] for curve in adf['curves'] if curve['polar'] == name)
        for state in polar['states']:
            series = next(s for s in data['series'] if s['polar'] == name and s['state'] == state['state'])
            check.near(series['alpha'], state['alpha'], f'{name} state ALPHA')
            check.near(series['cl_global'], state['CLS'], f'{name} matched ADF CLS')
            row = next(row for row in adf_rows if math.isclose(row['ALPHA'], state['alpha'], abs_tol=1e-9))
            for key in ('CLS', 'CDS', 'CMS25'):
                check.near(row[key], state[key], f'{name} ADF {key}')
            check.require([p['y'] for p in series['cp']] == expected['stations'], f'{name} Cp stations')
            check.require([p['y'] for p in series['span']] == expected['stations'], f'{name} load stations')
            for section in state['sections']:
                y = section['y']
                cp = next(p for p in series['cp'] if p['y'] == y)
                span = next(p for p in series['span'] if p['y'] == y)
                geometry_path, pressure_path = curve_paths(base, name, state['state'], y)
                geometry, pressure = read_curve(geometry_path), read_curve(pressure_path)
                check.require(len(geometry) == len(pressure) == 603, f'{name}/{y}: 603 paired samples')
                check.require(len(cp['elements']) == span['element_count'] == 2, f'{name}/{y}: two elements')
                check.near(cp['chord'], expected['chord'], f'{name}/{y}: overall section chord')
                check.near(span['chord'], expected['chord'], f'{name}/{y}: load reference chord')
                raw_values[name, state['state'], y] = [(p-expected['p'])/expected['qdin'] for x, p in pressure]
                for i, ((x, z), (px, p)) in enumerate(zip(geometry, pressure)):
                    check.near(px, x, 'paired geometry/pressure X', absolute=1e-10)
                    check.near(cp['x'][i], x, 'preserved source X', absolute=1e-10)
                    check.near(cp['airfoil']['ordinate'][i], z, 'preserved section ordinate', absolute=1e-10)
                    check.near(cp['values'][i], (p-expected['p'])/expected['qdin'], 'pressure-to-Cp conversion')
                offset = 0
                direct = []
                for index, size in enumerate((309, 294)):
                    element, wanted = cp['elements'][index], section['elements'][index]
                    points, pressures = geometry[offset:offset+size], pressure[offset:offset+size]
                    check.require(len(element['values']) == size, f'Element {index+1} point count')
                    check.require(points[0] == points[-1], f'Element {index+1} explicit closure')
                    check.require(element['airfoil']['x'] == [p[0] for p in points], 'Element geometry order')
                    check.require(element['airfoil']['ordinate'] == [p[1] for p in points], 'Element ordinate order')
                    fx, fz = absolute_pressure_force(points, [p[1] for p in pressures])
                    direct.append((fx, fz))
                    for key, force in (('fx', fx), ('fz', fz)):
                        check.near(element[key], wanted[key], f'Element expected {key}')
                        check.near(element[key], force, f'Element absolute-pressure integral {key}')
                    if polar['number'] == 3:
                        area = abs(polygon_area(points))
                        check.near(area, wanted['area'], 'Analytical element area', absolute=1e-11)
                        check.near(element['fx'], expected['qdin']*wanted['cp_dx']*area, 'Affine Cp exact Fx')
                        check.near(element['fz'], expected['qdin']*wanted['cp_dz']*area, 'Affine Cp exact Fz')
                    check.require('upper' in element['surfaces'] and 'lower' in element['surfaces'], 'Surface classification')
                    offset += size
                for key in ('fx', 'fz', 'lift', 'cl'):
                    check.near(span[key], section[key], f'{name}/{y} expected {key}')
                check.near(span['fx'], sum(v[0] for v in direct), 'Combined direct Fx')
                check.near(span['fz'], sum(v[1] for v in direct), 'Combined direct Fz')
                cove = cp['elements'][0]['surfaces'].get('trailing edge / cove')
                check.require(cove is not None, 'Rear cove retained')
                check.require(any(a == b for a, b in zip(cove['x'], cove['x'][1:])), 'Vertical repeated-X cove retained')
                check.require(geometry[309] == geometry[310], 'Duplicated flap starting point retained')
                if y == 0:
                    for value, target, label in ((geometry[0][0], 1.4791, 'Main arbitrary start X'),
                                                  (geometry[0][1], .010859, 'Main arbitrary start ordinate'),
                                                  (min(x for x, z in geometry[:309]), 1.4742, 'Main LE'),
                                                  (max(x for x, z in geometry[:309]), 1.9022, 'Main TE'),
                                                  (min(cove['x']), 1.8852, 'Cove recess'),
                                                  (min(x for x, z in geometry[309:]), 1.8972, 'Flap LE'),
                                                  (max(x for x, z in geometry[309:]), 2.0347, 'Flap TE')):
                        check.near(value, target, label, absolute=1e-9)
                    check.require(min(x for x, z in geometry[309:]) < max(x for x, z in geometry[:309]), 'Overlapping X extents')
                if not cancellation_checked:
                    topology = distributions.section_topology(geometry)
                    shifted = distributions.pressure_section([(x, p+3141.59) for x, p in pressure], geometry,
                                                              expected['p'], expected['qdin'], topology=topology)
                    uniform = distributions.pressure_section([(x, expected['p']+1000) for x, z in geometry], geometry,
                                                              expected['p'], expected['qdin'], topology=topology)
                    for key in ('fx', 'fz'):
                        check.near(shifted[key], span[key], f'Constant pressure offset cancels for {key}')
                        check.near(uniform[key], 0, f'Uniform pressure cancels for {key}')
                    cancellation_checked = True
            loads = sorted(series['span'], key=lambda point: point['y'])
            total_lift = math.fsum((b['y']-a['y'])*(a['lift']+b['lift'])/2
                                   for a, b in zip(loads, loads[1:]))
            check.near(series['cl_global'], total_lift/(expected['qdin']*info['meta']['sref']),
                       f'{name} ADF CLS agrees with span-integrated pressure lift')
    uniform_directory = fixture/'validation_cases/uniform_pressure'
    uniform_expected = json.loads((uniform_directory/'expected.json').read_text(encoding='utf-8'))
    uniform_geometry = read_curve(uniform_directory/'section_state1_station0.000')
    uniform_pressure = read_curve(uniform_directory/'cp_dist_state1_station0.000')
    uniform = distributions.pressure_section(uniform_pressure, uniform_geometry,
                                            uniform_expected['p'], uniform_expected['qdin'])
    check.require(len(uniform['elements']) == 2, 'Uniform test keeps two distinct pressure domains')
    for key in ('fx', 'fz'):
        check.near(uniform[key], uniform_expected[key], f'Uniform test combined {key}')
    for element, value in zip(uniform['elements'], uniform_expected['element_cp']):
        check.near(element['fx'], 0, 'Uniform element Fx cancellation')
        check.near(element['fz'], 0, 'Uniform element Fz cancellation')
        for cp in element['values']:
            check.near(cp, value, 'Uniform element pressure normalization')
    targets = interpolation_expectations(expected, raw_values)
    javascript = check_javascript(data['series'], targets)
    result = {'status': 'PASS', 'fixture': str(fixture), 'polars': 3, 'states': 15,
              'sections': 75, 'pressure_samples': 75*603, 'interpolation_targets': javascript['targets'],
              'interpolation_out_of_range': sum(target.get('outside', False) for target in targets),
              'uniform_pressure_case': 'PASS', 'verified_source_files': len(hashes),
              'python_checks': check.count, 'javascript_checks': javascript['checks']}
    if output is not None:
        Path(output).write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixture', nargs='?', type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument('--output', type=Path, help='Optionally save the passing validation report as JSON')
    arguments = parser.parse_args()
    validate(arguments.fixture, arguments.output)
