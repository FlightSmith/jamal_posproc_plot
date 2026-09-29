"""Additive DISTCLCP reader. Physics tested with synthetic fixtures; production validation pending."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time

VERSION = '0.4 multi-element pressure integration'
TOPOLOGY_CACHE_VERSION = 1
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


def fingerprint(path, stat=None, resolved_path=None):
    stat = path.stat() if stat is None else stat
    return {'path': str(path.resolve()) if resolved_path is None else str(resolved_path),
            'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}


def cached_parse(path, kind, cache_dir, force, counts, source=None):
    """Cache raw geometry and per-state inputs independently from aerodynamic caches."""
    before = fingerprint(path) if source is None else source
    key = hashlib.sha256(before['path'].encode('utf-8')).hexdigest()
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
    if fingerprint(path, resolved_path=before['path']) != before:
        raise ValueError(f'{path.name}: source changed during parsing; retry generation')
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=key[:12]+'.', suffix='.tmp', dir=target.parent)
    temp = Path(name)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            json.dump({'version': VERSION, 'fingerprint': before, 'data': data}, output, allow_nan=False)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    counts['parsed'] += 1
    return data, before


def cached_topology(geometry, cache_dir, force=False, memo=None, counts=None):
    """Reuse exact validated coordinates, without caching pressure or flow results.

    The geometry digest includes every original ordered row. The algorithm version
    invalidates old validation decisions; a result checksum detects damaged caches.
    Cache writes are optional: an unavailable cache must not remove valid loads.
    """
    encoded = json.dumps(geometry, separators=(',', ':'), allow_nan=False)
    key = hashlib.sha256(encoded.encode('utf-8')).hexdigest()
    memo = {} if memo is None else memo
    counts = {} if counts is None else counts
    def counted(name):
        counts[name] = counts.get(name, 0)+1
    if key in memo:
        counted('reused')
        value = memo[key]
        if isinstance(value, str):
            raise ValueError(value)
        return value
    target = Path(cache_dir) / 'topology' / (key+'.json')
    if not force:
        try:
            cached = json.loads(target.read_text(encoding='utf-8'))
            value = cached['topology']
            checksum = hashlib.sha256(json.dumps(value, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
            valid = (cached['version'] == TOPOLOGY_CACHE_VERSION and cached['geometry'] == key
                     and cached['checksum'] == checksum and isinstance(value, list) and bool(value)
                     and [i for e in value for i in e['indices']] == list(range(len(geometry))))
            if valid:
                for element in value:
                    indices = element['indices']
                    index_set = set(indices)
                    valid = (valid and len(indices) >= 4 and all(type(i) is int for i in indices)
                             and element['direction'] in (-1, 1) and isinstance(element['id'], str)
                             and isinstance(element['name'], str) and isinstance(element['surfaces'], dict)
                             and {'upper', 'lower'} <= element['surfaces'].keys()
                             and all(isinstance(branch, list) and bool(branch)
                                     and all(type(i) is int and i in index_set for i in branch)
                                     for branch in element['surfaces'].values()))
            if valid:
                counted('cached')
                memo[key] = value
                return value
        except (OSError, ValueError, KeyError, TypeError):
            pass
    counted('validated')
    try:
        value = section_topology(geometry)
    except ValueError as error:
        memo[key] = str(error)
        raise
    memo[key] = value
    temporary = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=key[:12]+'.', suffix='.tmp', dir=target.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            checksum = hashlib.sha256(json.dumps(value, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
            json.dump({'version': TOPOLOGY_CACHE_VERSION, 'geometry': key,
                       'checksum': checksum, 'topology': value}, output, separators=(',', ':'), allow_nan=False)
        temporary.replace(target)
    except OSError:
        counted('write_failed')
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    return value


def _segment_boxes_overlap(a, b, tolerance):
    """The conservative bounding-box rejection used by the exact predicate."""
    return not (a[1]+tolerance < b[0] or b[1]+tolerance < a[0]
                or a[3]+tolerance < b[2] or b[3]+tolerance < a[2])


def _segment_box_candidates(segments, tolerance, other_segments=None):
    """Yield all potentially touching pairs without scanning every segment pair.

    A bounding-box hierarchy prunes disjoint groups in both coordinates. Unlike
    an X-only sweep, this also handles densely sampled vertical cove walls. Box
    overlap is only a broad-phase test; callers retain the exact intersection
    predicate. Self-pairs are unique with i < j; cross-pairs retain input order.
    """
    def build(items):
        bounds = (min(p[0] for p in items), max(p[1] for p in items),
                  min(p[2] for p in items), max(p[3] for p in items))
        if len(items) <= 8:
            return bounds, None, None, items, len(items)
        axis = 0 if bounds[1]-bounds[0] >= bounds[3]-bounds[2] else 2
        ordered = sorted(items, key=lambda p: p[axis]/2+p[axis+1]/2)
        middle = len(ordered)//2
        return bounds, build(ordered[:middle]), build(ordered[middle:]), None, len(items)

    def tree(source):
        return build([(min(a[0],b[0]), max(a[0],b[0]),
                       min(a[1],b[1]), max(a[1],b[1]), i)
                      for i,(a,b) in enumerate(source)])

    def pairs(left, right, same=False):
        if not _segment_boxes_overlap(left[0], right[0], tolerance):
            return
        if left[3] is not None and right[3] is not None:
            for i,a in enumerate(left[3]):
                for b in (right[3][i+1:] if same else right[3]):
                    if _segment_boxes_overlap(a, b, tolerance):
                        yield a[4], b[4]
        elif same:
            yield from pairs(left[1], left[1], True)
            yield from pairs(left[1], left[2])
            yield from pairs(left[2], left[2], True)
        elif right[3] is not None or (left[3] is None and left[4] >= right[4]):
            yield from pairs(left[1], right)
            yield from pairs(left[2], right)
        else:
            yield from pairs(left, right[1])
            yield from pairs(left, right[2])

    if not segments or (other_segments is not None and not other_segments):
        return
    first = tree(segments)
    if other_segments is None:
        for i,j in pairs(first, first, True):
            yield (i,j) if i<j else (j,i)
    else:
        yield from pairs(first, tree(other_segments))


def section_topology(geometry):
    """Recover consecutive closed loops from matched, ordered section coordinates.

    Closure means the same X AND ordinate, never X alone. Only the legacy single
    edge-to-edge contour may omit its closing point. Do not infer gaps or join
    separate open elements. All returned indices address the original samples.
    """
    if len(geometry) < 4 or any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in geometry):
        raise ValueError('finite section coordinates and a resolved contour are required')
    lo, hi = min(p[0] for p in geometry), max(p[0] for p in geometry)
    chord = hi-lo
    if chord <= 0:
        raise ValueError('a nonzero section chord is required')
    tol = max(1e-12, min(STATION_TOLERANCE, chord*1e-8))
    near = lambda a,b: abs(a[0]-b[0]) <= tol and abs(a[1]-b[1]) <= tol
    contours, start = [], 0
    while start < len(geometry):
        end, edges = None, 0
        for i in range(start+1, len(geometry)):
            if not near(geometry[i-1], geometry[i]):
                edges += 1
            if edges >= 3 and near(geometry[start], geometry[i]):
                end = i
                # Preserve duplicate closure rows with their corresponding Cp.
                while end+1 < len(geometry) and near(geometry[start], geometry[end+1]):
                    end += 1
                break
        if end is None:
            if contours:
                raise ValueError('element boundaries unresolved: every element must return to its starting X and ordinate')
            # Compatibility with the original open/blunt single-element export.
            xs = [p[0] for p in geometry]
            at = lambda x, edge: abs(x-edge) <= tol
            if at(xs[0], hi) and at(xs[-1], hi):
                turn = xs.index(lo)
            elif at(xs[0], lo) and at(xs[-1], lo):
                turn = xs.index(hi)
            else:
                raise ValueError('element boundaries unresolved: closed contours are required')
            branches = [xs[:turn+1], xs[turn:]]
            if any(len(b)<3 or any((v-u)*(b[-1]-b[0]) <= 0 for u,v in zip(b,b[1:])) for b in branches):
                raise ValueError('open contour has extra turns; explicit element closure is required')
            end = len(geometry)-1
        contours.append(list(range(start,end+1)))
        start = end+1

    def cross(a,b,c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])

    def intersects(a,b,c,d):
        if (max(a[0],b[0])+tol < min(c[0],d[0]) or max(c[0],d[0])+tol < min(a[0],b[0])
                or max(a[1],b[1])+tol < min(c[1],d[1]) or max(c[1],d[1])+tol < min(a[1],b[1])):
            return False
        epsilon = tol*max(math.dist(a,b), math.dist(c,d),tol)
        ab, ac, cd, ca = cross(a,b,c), cross(a,b,d), cross(c,d,a), cross(c,d,b)
        return ((min(ab,ac) <= epsilon and max(ab,ac) >= -epsilon)
                and (min(cd,ca) <= epsilon and max(cd,ca) >= -epsilon))

    polygons, result = [], []
    for number, indices in enumerate(contours,1):
        # Geometry-only simplification for validity checks. Output/integration
        # retains every paired pressure row, including repeated X and zero edges.
        vertices = []
        for i in indices:
            if not vertices or not near(geometry[i],vertices[-1]):
                vertices.append(geometry[i])
        if len(vertices)>1 and near(vertices[0],vertices[-1]):
            vertices.pop()
        n = len(vertices)
        if n < 3:
            raise ValueError(f'element {number} has fewer than three distinct vertices')
        segments = list(zip(vertices,vertices[1:]+vertices[:1]))
        first_intersection = n
        for i,j in _segment_box_candidates(segments, tol):
            if j==i+1 or (i==0 and j==n-1) or i>=first_intersection:
                continue
            if intersects(*segments[i],*segments[j]):
                first_intersection = i
                if i==0:
                    break
        for i,(a,b) in enumerate(segments):
            # Preserve the original error precedence relative to adjacent
            # backtracking, independently of the hierarchy's traversal order.
            if i==first_intersection:
                raise ValueError(f'element {number} contour intersects or touches itself')
            c = vertices[(i+2)%n]
            if abs(cross(a,b,c)) <= tol*max(math.dist(a,b),math.dist(b,c)) and (
                    (a[0]-b[0])*(c[0]-b[0])+(a[1]-b[1])*(c[1]-b[1]) > tol*tol):
                raise ValueError(f'element {number} contour doubles back on itself')
        # Translate before the shoelace sum to avoid cancellation at large offsets.
        origin = vertices[0]
        area2 = math.fsum(cross(origin,a,b) for a,b in segments)
        if abs(area2) <= chord*chord*1e-12:
            raise ValueError(f'element {number} contour has zero enclosed area')
        polygons.append((vertices,segments))
        xs = [geometry[i][0] for i in indices]
        elo,ehi = min(xs),max(xs)
        if ehi-elo <= tol:
            raise ValueError(f'element {number} has no resolved X extent')
        # Two ordered paths from the forward X extreme to the first aft extreme
        # on each side. Their remaining connecting path is a blunt TE or cove;
        # its vertical walls/extra turns must not be sorted away.
        leading = xs.index(elo)
        def path_to_aft(step):
            path = [leading]
            while abs(xs[path[-1]]-ehi)>tol:
                path.append((path[-1]+step)%len(indices))
                if len(path)>len(indices):
                    raise ValueError(f'element {number} has unresolved surface paths')
            # Use the endpoint adjacent to the first real edge when closure
            # duplicates the LE. This also preserves separate LE-side pressures.
            while len(path)>1 and near(geometry[indices[path[0]]],geometry[indices[path[1]]]):
                path.pop(0)
            return path
        paths = [path_to_aft(1),path_to_aft(-1)]
        def ordinate_integral(path):
            return math.fsum((geometry[indices[a]][1]+geometry[indices[b]][1])*(xs[b]-xs[a])/2
                             for a,b in zip(path,path[1:]))
        means = [ordinate_integral(path) for path in paths]
        if abs(means[0]-means[1]) <= chord*chord*1e-12:
            raise ValueError(f'element {number} upper/lower geometry is ambiguous')
        upper = 0 if means[0]>means[1] else 1
        surfaces = {'upper':[indices[i] for i in paths[upper]],
                    'lower':[indices[i] for i in paths[1-upper]]}
        aft = [paths[0][-1]]
        while aft[-1] != paths[1][-1]:
            aft.append((aft[-1]+1)%len(indices))
        if any(not near(geometry[indices[a]],geometry[indices[b]]) for a,b in zip(aft,aft[1:])):
            surfaces['trailing edge / cove'] = [indices[i] for i in aft]
        result.append({'indices':indices, 'surfaces':surfaces, 'direction':1 if area2>0 else -1,
                       'id':f'element-{number}', 'name':f'Element {number}'})

    def contains(vertices, point):
        x,z = point
        inside = False
        for a,b in zip(vertices,vertices[1:]+vertices[:1]):
            if (a[1]>z)!=(b[1]>z) and x < a[0]+(b[0]-a[0])*(z-a[1])/(b[1]-a[1]):
                inside = not inside
        return inside
    for i,(vertices,segments) in enumerate(polygons):
        for other,edges in polygons[i+1:]:
            if (any(intersects(*segments[a],*edges[b])
                    for a,b in _segment_box_candidates(segments, tol, edges))
                    or contains(vertices,other[0]) or contains(other,vertices[0])):
                raise ValueError('element contours intersect, touch or overlap; separate non-overlapping solids are required')
    return result


def pressure_section(points, geometry, reference_pressure, qdin, input_kind='pressure', surface_order='section', topology=None):
    """Integrate matched pressure around each element, then sum body Fx/Fz.

    X is aft, ordinate up. Pressure is linear on each original contour segment.
    Common x/c and combined cl use the whole section's X extent, as selected by
    the user. Upper/lower/cove labels do not affect pressure quadrature.
    """
    if not math.isfinite(qdin) or qdin <= 0:
        raise ValueError('positive finite qdin is required')
    if input_kind not in ('pressure', 'cp') or surface_order not in ('section', 'reverse'):
        raise ValueError('invalid pressure format or surface order')
    if input_kind == 'pressure' and (reference_pressure is None or not math.isfinite(reference_pressure)):
        raise ValueError('infout p[Pa] is required for absolute pressure')
    outline = list(reversed(geometry)) if surface_order == 'reverse' else geometry
    if len(points) != len(outline) or any(abs(p[0]-g[0]) > STATION_TOLERANCE for p,g in zip(points,outline)):
        raise ValueError('pressure/section point order does not match; matched contour samples are required')
    topology = section_topology(outline) if topology is None or surface_order=='reverse' else topology
    xs = [p[0] for p in points]
    lo,hi = min(g[0] for g in outline),max(g[0] for g in outline)
    chord = hi-lo
    values = [(p[1]-reference_pressure)/qdin if input_kind=='pressure' else p[1] for p in points]
    if not all(math.isfinite(v) for v in xs+values):
        raise ValueError('non-finite pressure coefficient or coordinate')
    def curve(indices):
        return {'x':[xs[i] for i in indices], 'xc':[(xs[i]-lo)/chord for i in indices],
                'values':[values[i] for i in indices]}
    elements = []
    for element in topology:
        indices = element['indices']
        segments = list(zip(indices,indices[1:]+indices[:1]))
        # Body X forward, Z down: pressure force is minus the outward normal.
        fx = element['direction']*qdin*math.fsum((values[a]+values[b])*(outline[b][1]-outline[a][1])/2 for a,b in segments)
        fz = -element['direction']*qdin*math.fsum((values[a]+values[b])*(outline[b][0]-outline[a][0])/2 for a,b in segments)
        elements.append({**curve(indices), 'id':element['id'], 'name':element['name'], 'fx':fx, 'fz':fz,
                         'airfoil':{'x':[outline[i][0] for i in indices], 'ordinate':[outline[i][1] for i in indices]},
                         'surfaces':{name:curve(branch) for name,branch in element['surfaces'].items()}})
    result = {**curve(range(len(points))), 'elements':elements,
              'fx':math.fsum(e['fx'] for e in elements), 'fz':math.fsum(e['fz'] for e in elements)}
    if len(elements)==1:
        result['surfaces'] = elements[0]['surfaces']
    return result


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
    topology_memo, topology_counts = {}, {}
    result['topology_cache'] = topology_counts
    timings = {name: 0.0 for name in ('infout', 'inventory', 'input_read', 'geometry', 'pressure')}
    result['timings_seconds'] = timings

    def timed(name, function, *args, **kwargs):
        started = time.perf_counter()
        try:
            return function(*args, **kwargs)
        finally:
            timings[name] += time.perf_counter()-started

    def directory_entries(path):
        with os.scandir(path) as entries:
            return list(entries)

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
                info = timed('infout', parse_infout, Path(cfg['runs_directory']) / polar / 'infout')
            except (OSError, ValueError, KeyError, IndexError) as error:
                issue(cfg, polar, 'All components', 'all', f'infout unavailable: {error}')
                continue
            meta, cases = info['meta'], info['cases']
            components = sorted((Path(entry.path) for entry in timed('inventory', directory_entries, root)
                                 if not entry.is_symlink() and entry.is_dir(follow_symlinks=False)),
                                key=lambda p: p.name)
            for component in components:
                if progress:
                    progress(f"{cfg['label']} Â· {polar} Â· {component.name}")
                geometry, cps = [], {}
                outlines, topologies = {}, {}
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
                # Directory entries retain file metadata on Windows. Resolve the
                # parent once instead of repeatedly resolving every remote file.
                resolved_component = timed('inventory', component.resolve)
                files = sorted(timed('inventory', directory_entries, component), key=lambda entry: entry.name)
                for file_index, entry in enumerate(files, 1):
                    station_match = STATION_PATTERN.fullmatch(entry.name)
                    if not station_match:
                        continue
                    if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                        continue
                    path = Path(entry.path)
                    state = int(station_match.group(2))
                    kind = 'geometry' if station_match.group(1).lower() == 'section' else 'cp'
                    if kind == 'geometry' and state != 1:
                        continue
                    try:
                        source = fingerprint(path, stat=entry.stat(follow_symlinks=False),
                                             resolved_path=resolved_component / entry.name)
                        rows, source = timed('input_read', cached_parse, path, kind, cache_dir, force,
                                             result['counts'], source=source)
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
                    if progress and (file_index % 25 == 0 or file_index == len(files)):
                        progress(f"{cfg['label']} · {polar} · {component.name}: reading files {file_index}/{len(files)}")

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
                    if progress:
                        progress(f"{cfg['label']} · {polar} · {component.name}: pressure state {state}/{len(cases)}")
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
                            if g['y'] not in topologies:
                                try:
                                    topologies[g['y']] = timed('geometry', cached_topology, outline, cache_dir,
                                                              force, topology_memo, topology_counts)
                                except ValueError as error:
                                    topologies[g['y']] = str(error)
                            topology = topologies[g['y']]
                            if isinstance(topology, str):
                                raise ValueError(topology)
                            pressure = timed('pressure', pressure_section, points, outline, meta.get('p'), q,
                                             series['input_kind'], topology=topology)
                            cp['elements'] = pressure['elements']
                            if 'surfaces' in pressure:
                                cp['surfaces'] = pressure['surfaces']
                            span['element_count'] = len(pressure['elements'])
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
