"""Additive DISTCLCP reader. Physics tested with synthetic fixtures; production validation pending."""
from __future__ import annotations

import hashlib
from bisect import bisect_right
import json
import math
import os
from pathlib import Path
import re
import tempfile

VERSION = '0.3 pressure integration'
STATION_TOLERANCE = 1e-6  # metres
NUMBER = r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eEdD][-+]?\d+)?'
STATION_PATTERN = re.compile(rf'^(section|cp_dist)_state([1-9]\d*)_station({NUMBER})$', re.I)
FORCE_PATTERN = re.compile(r'^total_force_state([1-9]\d*)$', re.I)


def finite_number(token):
    value = float(token.replace('D', 'E').replace('d', 'e'))
    if not math.isfinite(value):
        raise ValueError('Non-finite numeric value')
    return value


def parse_curve(path):
    """Preserve surface order; skip all numeric metadata before the axis header."""
    points, started, ended = [], False, False
    with Path(path).open(encoding='utf-8-sig') as source:
        for line_number, line in enumerate(source, 1):
            if not started:
                started = 'ABSCISSA' in line.upper() and 'ORDINATE' in line.upper()
                continue
            text = line.strip()
            if text.upper().startswith('*END'):
                ended = True
                break
            if not text or text.startswith('$'):
                continue
            columns = text.split()
            if len(columns) != 2:
                raise ValueError(f'{path.name}:{line_number}: expected two curve columns')
            points.append([finite_number(value) for value in columns])
    if not started or not ended or len(points) < 2:
        raise ValueError(f'{path.name}: missing curve header, *END, or curve points')
    return points


def parse_force(path):
    rows = []
    with Path(path).open(encoding='utf-8-sig') as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            columns = line.split()
            if len(columns) != 4:
                raise ValueError(f'{path.name}:{line_number}: expected Y FX FY FZ')
            rows.append([finite_number(value) for value in columns])
    if not rows:
        raise ValueError(f'{path.name}: empty force table')
    return rows


def fingerprint(path):
    stat = path.stat()
    return {'path': str(path.resolve()), 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}


def cached_parse(path, kind, cache_dir, force, counts):
    """Cache raw geometry and per-state inputs independently from aerodynamic caches."""
    before = fingerprint(path)
    key = hashlib.sha256(str(path.resolve()).encode('utf-8')).hexdigest()
    target = cache_dir / kind / (key + '.json')
    if not force:
        try:
            cached = json.loads(target.read_text(encoding='utf-8'))
            if (cached['version'] == VERSION and cached['fingerprint'] == before
                    and isinstance(cached['data'], list) and cached['data']
                    and all(isinstance(row, list) and len(row) == (4 if kind == 'forces' else 2)
                            and all(isinstance(v, (int, float)) and math.isfinite(v) for v in row)
                            for row in cached['data'])):
                counts['cached'] += 1
                return cached['data'], before
        except (OSError, ValueError, KeyError, TypeError):
            pass
    data = parse_force(path) if kind == 'forces' else parse_curve(path)
    if fingerprint(path) != before:
        raise ValueError(f'{path.name}: source changed during parsing; retry generation')
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=key, suffix='.tmp', dir=target.parent)
    temp = Path(name)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            json.dump({'version': VERSION, 'fingerprint': before, 'data': data}, output, allow_nan=False)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    counts['parsed'] += 1
    return data, before


def pressure_section(points, geometry, reference_pressure, qdin, input_kind='pressure', surface_order='section'):
    """Single-element contour, X aft and ordinate up; pressure rows follow geometry.

    Close the contour with a straight edge (also handles a blunt trailing edge).
    Pressure is linear on each segment. No global X sorting or force-file input.
    """
    if not math.isfinite(qdin) or qdin <= 0:
        raise ValueError('positive finite qdin is required')
    if input_kind not in ('pressure', 'cp') or surface_order not in ('section', 'reverse'):
        raise ValueError('invalid pressure format or surface order')
    if input_kind == 'pressure' and (reference_pressure is None or not math.isfinite(reference_pressure)):
        raise ValueError('infout p[Pa] is required for absolute pressure')
    outline = list(reversed(geometry)) if surface_order == 'reverse' else geometry
    if len(points) != len(outline) or any(abs(p[0]-g[0]) > STATION_TOLERANCE for p, g in zip(points, outline)):
        raise ValueError('pressure/section point order does not match; matched contour samples are required')
    xs = [p[0] for p in points]
    lo, hi = min(xs), max(xs)
    chord = hi-lo
    if chord <= 0 or len(points) < 5:
        raise ValueError('a nonzero chord and two resolved surfaces are required')
    tol = min(STATION_TOLERANCE, chord*1e-7)
    at = lambda x, edge: abs(x-edge) <= tol
    if at(xs[0], hi) and at(xs[-1], hi):
        turn = xs.index(lo)
    elif at(xs[0], lo) and at(xs[-1], lo):
        turn = xs.index(hi)
    else:
        raise ValueError('single-element contour must run edge-to-edge and back; element boundaries are unresolved')
    branches = [list(range(turn+1)), list(range(turn, len(xs)))]
    for branch in branches:
        if len(branch) < 3:
            raise ValueError('both surfaces need at least three samples')
        if xs[branch[0]] > xs[branch[-1]]:
            branch.reverse()
        if any(xs[b] <= xs[a] for a, b in zip(branch, branch[1:])):
            raise ValueError('surface contains repeated X or extra turns; multi-element/overhanging contours are unresolved')
    def ordinate_mean(indices):
        return sum((outline[a][1]+outline[b][1])*(xs[b]-xs[a])/2 for a,b in zip(indices,indices[1:]))/chord
    means = [ordinate_mean(branch) for branch in branches]
    if abs(means[0]-means[1]) < chord*1e-10:
        raise ValueError('upper/lower geometry is ambiguous')
    # With matched X samples, reject intersecting upper/lower branches rather than guessing.
    def interpolate_z(indices, coordinates, x):
        pos=max(0,min(len(indices)-2,bisect_right(coordinates,x)-1))
        a,b=indices[pos:pos+2]
        return outline[a][1]+(outline[b][1]-outline[a][1])*(x-xs[a])/(xs[b]-xs[a])
    upper_index = 0 if means[0] > means[1] else 1
    upper, lower = branches[upper_index], branches[1-upper_index]
    upper_x, lower_x = [xs[i] for i in upper], [xs[i] for i in lower]
    for x in sorted(set(xs)):
        if interpolate_z(upper,upper_x,x) < interpolate_z(lower,lower_x,x)-tol:
            raise ValueError('section surfaces cross; contour cannot be classified')
    values = [(p[1]-reference_pressure)/qdin if input_kind=='pressure' else p[1] for p in points]
    if not all(math.isfinite(v) for v in values):
        raise ValueError('non-finite pressure coefficient')
    area2 = sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(outline,outline[1:]+outline[:1]))
    if abs(area2) < chord*chord*1e-12:
        raise ValueError('section contour has zero enclosed area')
    direction = 1 if area2 > 0 else -1
    # Body X points forward, Z down; pressure force is minus outward normal.
    fx, fz = 0., 0.
    for i,a in enumerate(outline):
        j=(i+1)%len(outline); b=outline[j]
        pressure = qdin*(values[i]+values[j])/2
        fx += direction*pressure*(b[1]-a[1])
        fz -= direction*pressure*(b[0]-a[0])
    surfaces = {name: {'x':[xs[i] for i in branch], 'xc':[(xs[i]-lo)/chord for i in branch],
                       'values':[values[i] for i in branch]}
                for name,branch in [('upper',upper),('lower',lower)]}
    return {'x':xs, 'xc':[(x-lo)/chord for x in xs], 'values':values, 'surfaces':surfaces,
            'fx':fx, 'fz':fz}


def attach_global_lift(data, adf_data):
    """Associate global stability CLS by conditions, never by sorted row position."""
    for series in data['series']:
        rows = [row for curve in adf_data.get('curves', [])
                if curve['case_label']==series['configuration'] and curve['polar']==series['polar']
                for row in curve.get('rows', [])
                if all(isinstance(row.get(k), (int,float)) and isinstance(series.get(v),(int,float))
                       and math.isclose(row[k],series[v],rel_tol=1e-6,abs_tol=1e-7)
                       for k,v in [('ALPHA','alpha'),('BETA','beta'),('MACH','mach'),('REYNOLDS','reynolds')])]
        series['cl_global'] = rows[0].get('CLS') if len(rows)==1 else None
        if series['cl_global'] is None:
            series['cl_global_warning'] = 'A unique ADF CLS at the same ALPHA/BETA/Mach/Re is required.'


def read_distributions(configurations, summaries, parse_infout, cache_dir, force=False, progress=None):
    result = {'version': VERSION, 'station_tolerance': STATION_TOLERANCE,
              'series': [], 'issues': [], 'sources': [], 'counts': {'parsed': 0, 'cached': 0},
              'validation': 'Synthetic fixture verified; production validation pending'}

    def issue(cfg, polar, component, state, message):
        result['issues'].append({'severity': 'WARNING', 'configuration': cfg['label'],
                                 'polar': polar, 'check': 'Distributions',
                                 'details': f'{component} Â· state {state}: {message}'})

    for cfg in configurations:
        for number in cfg['polars']:
            polar = f'POLAR-{number:03d}'
            root = Path(cfg['base_directory']) / '03-RESULTS' / 'DISTCLCP' / polar
            if not root.is_dir():
                continue  # Optional module; no DISTCLCP is not an error.
            try:
                info = parse_infout(Path(cfg['runs_directory']) / polar / 'infout')
            except (OSError, ValueError, KeyError, IndexError) as error:
                issue(cfg, polar, 'All components', 'all', f'infout unavailable: {error}')
                continue
            meta, cases = info['meta'], info['cases']
            components = sorted((p for p in root.iterdir() if p.is_dir() and not p.is_symlink()), key=lambda p: p.name)
            for component in components:
                if progress:
                    progress(f"{cfg['label']} Â· {polar} Â· {component.name}")
                geometry, cps = [], {}
                outlines = {}
                span_reference = meta.get('bref')
                reference_source = 'infout BREF'
                planar_geometry = True
                reference_path = component / 'component_reference.json'
                if reference_path.is_file():
                    try:
                        reference = json.loads(reference_path.read_text(encoding='utf-8'))
                        # A local section-normal ordinate cannot be used as body Z.
                        # No 3D orientation/span Jacobian is inferred from a component name.
                        planar_geometry = ('local' not in str(reference.get('curve_ordinate','')).lower()
                                           and not reference.get('cant_degrees'))
                        span_reference = float(reference['span_reference_m'])
                        if not math.isfinite(span_reference) or span_reference <= 0:
                            raise ValueError('span_reference_m must be positive and finite')
                        reference_source = 'component_reference.json'
                        result['sources'].append({**fingerprint(reference_path), 'configuration': cfg['label'],
                                                  'polar': polar, 'component': component.name, 'kind': 'reference', 'state': None})
                    except (OSError, ValueError, TypeError, KeyError) as exc:
                        span_reference = None
                        planar_geometry = False
                        issue(cfg, polar, component.name, 'all', f'invalid component span reference: {exc}')
                for path in sorted(component.iterdir()):
                    if not path.is_file() or path.is_symlink():
                        continue
                    station_match = STATION_PATTERN.fullmatch(path.name)
                    if not station_match:
                        continue
                    state = int(station_match.group(2))
                    kind = 'geometry' if station_match.group(1).lower() == 'section' else 'cp'
                    if kind == 'geometry' and state != 1:
                        continue
                    try:
                        rows, source = cached_parse(path, kind, cache_dir, force, result['counts'])
                        result['sources'].append({**source, 'configuration': cfg['label'], 'polar': polar,
                                                  'component': component.name, 'kind': kind, 'state': state})
                        if kind == 'geometry':
                            y = finite_number(station_match.group(3))
                            xs = [row[0] for row in rows]
                            chord = max(xs) - min(xs)
                            if chord <= 0:
                                raise ValueError('non-positive chord')
                            geometry.append({'y': y, 'xmin': min(xs), 'xmax': max(xs), 'chord': chord})
                            outlines[y] = rows
                        elif kind == 'cp':
                            cps.setdefault(state, []).append((finite_number(station_match.group(3)), rows))
                    except (OSError, ValueError, UnicodeError) as exc:
                        issue(cfg, polar, component.name, state, f'{path.name}: {exc}')

                geometry.sort(key=lambda g: g['y'])
                duplicate_geometry = {g['y'] for g in geometry
                                      if sum(abs(g['y'] - other['y']) <= STATION_TOLERANCE for other in geometry) > 1}
                if duplicate_geometry:
                    issue(cfg, polar, component.name, 1, 'duplicate geometry stations; ambiguous stations omitted')
                    geometry = [g for g in geometry if g['y'] not in duplicate_geometry]

                def match(y):
                    matches = [g for g in geometry if abs(g['y'] - y) <= STATION_TOLERANCE]
                    return matches[0] if len(matches) == 1 else None

                for unexpected in set(cps) - set(range(1, len(cases) + 1)):
                    issue(cfg, polar, component.name, unexpected, 'state has no matching infout case; omitted')
                for state, case in enumerate(cases, 1):
                    series = {'configuration': cfg['label'], 'polar': polar, 'component': component.name,
                              'state': state, 'case': case['case'], 'alpha': case['alpha'], 'beta': case['beta'],
                              'mach': case['mach'], 'reynolds': case['reynolds'], 'bref': meta.get('bref'),
                              'span_reference': span_reference, 'span_reference_source': reference_source,
                              'qdin': meta.get('qdin'), 'p': meta.get('p'),
                              'input_kind': cfg.get('distribution_input', 'pressure'),
                              'load_method': 'closed-contour pressure force projected to lift; no viscous shear',
                              'span': [], 'cp': []}
                    q = meta.get('qdin')
                    valid_q = q is not None and math.isfinite(q) and q > 0
                    # A single flow-condition qdin cannot be assigned across changing Mach/Re cases.
                    same_flow = all(c.get(k) is not None and meta.get(k) is not None
                                    and math.isclose(c[k], meta[k], rel_tol=1e-6, abs_tol=1e-9)
                                    for c in cases for k in ('mach', 'reynolds'))
                    angles_valid = all(case.get(k) is not None and math.isfinite(case[k]) for k in ('alpha', 'beta'))
                    valid_lift = valid_q and same_flow and angles_valid and abs(case['beta']) <= 1e-9 and planar_geometry
                    if not valid_lift:
                        issue(cfg, polar, component.name, state,
                              'sectional cl unavailable: local/canted section geometry requires a section-to-body and span mapping'
                              if not planar_geometry else 'sectional cl unavailable: requires positive qdin, constant flow and beta=0')
                    if state not in cps:
                        issue(cfg, polar, component.name, state, 'missing pressure state')
                    cp_stations = [y for y, _ in cps.get(state, [])]
                    cp_used = set()
                    for y, points in cps.get(state, []):
                        g = match(y)
                        if not g:
                            issue(cfg, polar, component.name, state, f'Cp station {y:g} has no unique geometry match')
                            continue
                        if sum(abs(y-other) <= 2*STATION_TOLERANCE for other in cp_stations) > 1:
                            issue(cfg, polar, component.name, state, f'duplicate Cp station {y:g}; omitted')
                            continue
                        if any(x < g['xmin']-STATION_TOLERANCE or x > g['xmax']+STATION_TOLERANCE for x, _ in points):
                            issue(cfg, polar, component.name, state, f'Cp station {y:g} extends beyond geometry chord')
                        cp_used.add(g['y'])
                        outline = outlines[g['y']]
                        if not valid_q or not same_flow or (series['input_kind']=='pressure' and meta.get('p') is None):
                            issue(cfg, polar, component.name, state,
                                  f'pressure station {y:g}: Cp requires p[Pa], positive qdin and constant infout flow')
                            continue
                        values = [(p[1]-meta['p'])/q if series['input_kind']=='pressure' else p[1] for p in points]
                        cp = {**g, 'x':[p[0] for p in points], 'values':values,
                              'xc':[(p[0]-g['xmin'])/g['chord'] for p in points],
                              'airfoil':{'x':[r[0] for r in outline], 'ordinate':[r[1] for r in outline]}}
                        span = {**g, 'fx':None, 'fz':None, 'lift':None, 'cl':None}
                        try:
                            pressure = pressure_section(points, outline, meta.get('p'), q, series['input_kind'])
                            cp['surfaces'] = pressure['surfaces']
                            if planar_geometry:
                                span.update(fx=pressure['fx'], fz=pressure['fz'])
                            if valid_lift:
                                alpha = math.radians(case['alpha'])
                                lift = pressure['fx']*math.sin(alpha)-pressure['fz']*math.cos(alpha)
                                span.update(lift=lift, cl=lift/(q*g['chord']))
                        except ValueError as error:
                            issue(cfg, polar, component.name, state, f'pressure station {y:g}: {error}; cl unavailable')
                        series['span'].append(span)
                        series['cp'].append(cp)
                    series['span'].sort(key=lambda r: r['y'])
                    series['cp'].sort(key=lambda r: r['y'])
                    for g in geometry:
                        if g['y'] not in cp_used:
                            issue(cfg, polar, component.name, state, f"geometry station {g['y']:g} has no valid Cp station")
                    result['series'].append(series)
    return result


def add_to_html(html, data):
    """Read UI assets at generation time and embed them for a portable single-file report."""
    root = Path(__file__).parent
    panel = (root / 'distributions.html').read_text(encoding='utf-8')
    script = (root / 'distribution_interpolation.js').read_text(encoding='utf-8') + '\n' + (root / 'distributions.js').read_text(encoding='utf-8')
    payload = json.dumps(data or {'series': [], 'issues': [], 'sources': []}, allow_nan=False).replace('<', '\\u003c')
    nav = '<button data-section="distributions" onclick="showSection(\'distributions\', this)">Distributions</button>'
    html = html.replace('<button data-section="convergence"', nav + '\n  <button data-section="convergence"', 1)
    return html.replace('</body>', panel + '\n<script>\nconst distributionData = ' + payload + ';\n' + script + '\n</script>\n</body>')
