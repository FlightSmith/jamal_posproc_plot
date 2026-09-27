"""Build a standalone synthetic CFD project from sparse screenshot readings.

This is a reconstruction with invented flow/sweep data, not a solver result.
No production dashboard calculations or original fixtures are modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parent
DEFAULT = ROOT/'JAMAL_SYNTHETIC_MULTIELEMENT_SCREENSHOTS'
P = 101325.0
Q = .2*P  # User-selected reference, 20265 Pa.
XMIN, XMAX = 1.4742, 2.0347
CHORD = XMAX-XMIN
STATIONS = [-1., -.5, 0., .5, 1.]
BREF, SREF = 2., 2.*CHORD
RHO, MU = 1.225, 1.7894e-5
VELOCITY = math.sqrt(2*Q/RHO)
MACH = math.sqrt(2*Q/(1.4*P))
REYNOLDS = RHO*VELOCITY*CHORD/MU
POLARS = [(1,[0,2,4,6,-2]),(2,[0,1,3,5,-2]),(3,[0,2,4,6,-2])]

# Excel row, X [m], section ordinate [m], absolute pressure [Pa].
# Sparse, rounded readings from the supplied images. '-' means pressure was
# not transcribed at that geometry anchor; it is interpolated from other rows.
MAIN_ANCHORS = '''
9 1.4791 .010859 102040
28 1.5086 .026544 100110
38 1.5373 .033436 100040
48 1.6136 .040633 100230
53 1.6431 .041073 100320
68 1.8009 .031274 100810
98 1.8968 .021326 101080
110 1.9022 .020635 -
115 1.9022 .019135 -
134 1.8852 .020040 101110
161 1.8852 -.020040 101130
180 1.9022 -.019135 101040
181 1.9022 -.019435 101020
182 1.9022 -.019735 101030
183 1.9022 -.020035 100990
184 1.9022 -.020335 100730
185 1.9022 -.020635 100800
186 1.9019 -.020674 101070
219 1.8594 -.025913 100960
228 1.8045 -.031826 100810
235 1.7439 -.037018 100640
240 1.6943 -.039906 100490
245 1.6452 -.041069 100330
250 1.5957 -.039886 100170
255 1.5504 -.035514 100060
257 1.5395 -.033820 100040
261 1.5249 -.030821 100120
265 1.5109 -.027225 100090
270 1.5005 -.023615 100320
275 1.4916 -.019589 100650
280 1.4866 -.016892 100810
282 1.4847 -.015633 100960
285 1.4815 -.013171 101460
286 1.4802 -.011992 101740
287 1.4791 -.010858 102020
288 1.4782 -.0097764 102290
289 1.4774 -.0087485 102550
290 1.4767 -.0077765 102800
291 1.4762 -.0068604 103040
292 1.4757 -.0060010 103260
293 1.4754 -.0051980 103450
294 1.4751 -.0044509 103630
295 1.4748 -.0037583 103770
296 1.4746 -.0031195 103890
297 1.4745 -.0025302 103990
298 1.4744 -.0019903 104060
299 1.4743 -.0014964 104110
300 1.4743 -.00099828 104150
301 1.4742 -.00049896 104170
302 1.4742 4.3027e-13 104180
303 1.4742 .00049899 104170
304 1.4743 .00099828 104150
305 1.4743 .0014964 104110
306 1.4744 .0019904 104060
307 1.4745 .0025302 103990
308 1.4746 .0031198 103900
309 1.4748 .0037586 103780
310 1.4750 .0044511 103640
311 1.4754 .0051980 103470
312 1.4757 .0060006 103280
313 1.4762 .0068598 103060
314 1.4767 .0077760 102830
315 1.4774 .0087484 102570
316 1.4782 .0097772 102310
317 1.4791 .010859 102040
'''
FLAP_ANCHORS = '''
318 2.0347 .00016610 101860
319 2.0347 .00016610 101860
320 2.0347 -.00016610 101860
322 2.0347 -.00083050 101800
346 2.0057 -.0053121 101630
354 1.9722 -.010775 101370
363 1.9397 -.015622 101190
393 1.9163 -.018801 100920
394 1.9161 -.018828 100930
409 1.9113 -.018201 101450
418 1.9061 -.015985 101070
435 1.9023 -.012883 101110
470 1.8972 -8.8038e-8 101120
493 1.9001 .0099516 101100
523 1.9072 .016584 101070
529 1.9113 .018200 101510
542 1.9157 .018828 101020
544 1.9161 .018826 100950
578 1.9750 .010327 101400
600 2.0303 .0014884 101840
609 2.0347 .00083050 101800
610 2.0347 .00049830 101780
611 2.0347 .00016610 101860
'''


def anchors(text):
    return [[int(row),float(x),float(z),None if p=='-' else float(p)]
            for row,x,z,p in (line.split() for line in text.strip().splitlines())]


def interpolate(known, column, queries):
    """Shape-preserving cubic Hermite interpolation on row number (never X)."""
    pairs = [(r[0],r[column]) for r in known if r[column] is not None]
    xs,ys = zip(*pairs)
    h = [b-a for a,b in zip(xs,xs[1:])]
    slopes = [(b-a)/step for a,b,step in zip(ys,ys[1:],h)]
    d = [0.]*len(xs)
    for i in range(1,len(xs)-1):
        if slopes[i-1]*slopes[i]>0:
            w1,w2 = 2*h[i]+h[i-1],h[i]+2*h[i-1]
            d[i] = (w1+w2)/(w1/slopes[i-1]+w2/slopes[i])
    for index,step,next_step,slope,next_slope in [
            (0,h[0],h[1],slopes[0],slopes[1]),
            (-1,h[-1],h[-2],slopes[-1],slopes[-2])]:
        candidate = ((2*step+next_step)*slope-step*next_slope)/(step+next_step)
        d[index] = 0 if candidate*slope<=0 else math.copysign(min(abs(candidate),3*abs(slope)),slope)
    result, i = [], 0
    for query in queries:
        while i<len(h)-1 and query>xs[i+1]:
            i += 1
        t = (query-xs[i])/h[i]
        result.append((2*t**3-3*t*t+1)*ys[i]+(t**3-2*t*t+t)*h[i]*d[i]
                      +(-2*t**3+3*t*t)*ys[i+1]+(t**3-t*t)*h[i]*d[i+1])
    return result


def contours():
    result = []
    for text in [MAIN_ANCHORS,FLAP_ANCHORS]:
        known = anchors(text)
        rows = range(known[0][0],known[-1][0]+1)
        result.append(list(zip(*(interpolate(known,column,rows) for column in [1,2,3]))))
    return result


def polygon_properties(contour):
    ox,oz = contour[0][:2]
    points = [(x-ox,z-oz) for x,z,*_ in contour]
    terms = [(x0*z1-x1*z0,x0+x1,z0+z1)
             for (x0,z0),(x1,z1) in zip(points,points[1:]+points[:1])]
    twice = math.fsum(t[0] for t in terms)
    return abs(twice)/2,ox+math.fsum(c*x for c,x,z in terms)/(3*twice),oz+math.fsum(c*z for c,x,z in terms)/(3*twice),math.copysign(1,twice)


def reference_force(contour, cp):
    """Independent two-point Gauss integration, including exact pressure moment.

    The production code is not imported. Element boundaries are known here.
    Physical body coordinates are (-X, Y, -ordinate), reference at body origin.
    """
    area,cx,cz,orientation = polygon_properties(contour)
    fx,fz,my = [],[],[]
    for i,a in enumerate(contour):
        j=(i+1)%len(contour)
        b=contour[j]
        dx,dz=b[0]-a[0],b[1]-a[1]
        for t in [.5-.5/math.sqrt(3),.5+.5/math.sqrt(3)]:
            pressure=Q*((1-t)*cp[i]+t*cp[j])
            x,z=a[0]+t*dx,a[1]+t*dz
            dfx,dfz=.5*orientation*pressure*dz,-.5*orientation*pressure*dx
            fx.append(dfx);fz.append(dfz);my.append(-z*dfx+x*dfz)
    return {'fx':math.fsum(fx),'fz':math.fsum(fz),'my':math.fsum(my),
            'area':area,'centroid_x':cx,'centroid_z':cz}


def pressure_values(contour, number, element, alpha, y):
    span = 1-.25*y*y
    if number==3:
        dx,dz = -.35/CHORD, -(1+1.6*alpha)/CHORD
        cp = [span*(dx*(x-XMIN)+dz*z+(.4 if element==0 else -.2)) for x,z,_ in contour]
        return cp,span*dx,span*dz
    slope = -1.5*alpha if number==1 or element==0 else -5*alpha-3
    return [span*((p-P)/Q+slope*z/CHORD) for x,z,p in contour],None,None


def curve(path, values, kind):
    path.parent.mkdir(parents=True,exist_ok=True)
    header = ['*KEYWORD','*DEFINE_CURVE_TITLE',f'SYNTHETIC screenshot reconstruction {kind}',
              '$ LCID SIDR SFA SFO OFFA OFFO DATTYP','26 0 1.0 1.0 0.0 0.0 0',
              '$ Not a CFD solver result; screenshot anchors plus interpolated rows.',
              '$ X in metres; ordinate in metres or absolute pressure in Pa.',
              '$ ABSCISSA ORDINATE']
    path.write_text('\n'.join(header)+'\n'+'\n'.join(f'{x:.16g} {value:.16g}' for x,value in values)+'\n*END\n',encoding='utf-8')


def write_json(path, data):
    path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def build(base=DEFAULT):
    base=Path(base).resolve()
    marker=base/'SYNTHETIC_FIXTURE.txt'
    if base.exists() and not marker.exists():
        raise ValueError(f'Refusing to overwrite an existing unmarked folder: {base}')
    base.mkdir(parents=True,exist_ok=True)
    marker.write_text('Screenshot-inspired synthetic validation fixture, generator version 1.\n',encoding='utf-8')
    geometry=contours()
    expected={'p':P,'qdin':Q,'chord':CHORD,'bref':BREF,'sref':SREF,'stations':STATIONS,
              'point_counts':[309,294],'mach':MACH,'reynolds':REYNOLDS,'polars':[]}
    for number,alphas in POLARS:
        polar=f'POLAR-{number:03d}'
        component=base/'03-RESULTS/DISTCLCP'/polar/'WING'
        run=base/'02-RUNS'/polar
        run.mkdir(parents=True,exist_ok=True)
        for y in STATIONS:
            curve(component/f'section_state1_station{y:.3f}',[(x,z) for c in geometry for x,z,p in c],'geometry')
        entry={'number':number,'alphas':alphas,'states':[]}
        adf=[]
        for state,alpha in enumerate(alphas,1):
            record={'state':state,'alpha':alpha,'sections':[]}
            for y in STATIONS:
                elements, pressures = [],[]
                for index,contour in enumerate(geometry):
                    cp,dx,dz=pressure_values(contour,number,index,alpha,y)
                    reference=reference_force(contour,cp)
                    if number==3:
                        # Divergence-theorem oracle independent of segment pressure quadrature.
                        reference.update(cp_dx=dx,cp_dz=dz)
                        reference['fx']=Q*dx*reference['area']
                        reference['fz']=Q*dz*reference['area']
                        reference['my']=Q*reference['area']*(dz*reference['centroid_x']-dx*reference['centroid_z'])
                    elements.append(reference)
                    pressures.extend((point[0],P+Q*value) for point,value in zip(contour,cp))
                curve(component/f'cp_dist_state{state}_station{y:.3f}',pressures,'absolute pressure')
                fx,fz,my=(sum(e[k] for e in elements) for k in ['fx','fz','my'])
                angle=math.radians(alpha)
                lift=fx*math.sin(angle)-fz*math.cos(angle)
                record['sections'].append({'y':y,'fx':fx,'fz':fz,'my':my,'lift':lift,
                                           'cl':lift/(Q*CHORD),'elements':elements})
            def span_integral(key):
                return math.fsum((a[key]+b[key])*(b['y']-a['y'])/2
                                 for a,b in zip(record['sections'],record['sections'][1:]))
            fx,fz,my=(span_integral(k)/(Q*SREF) for k in ['fx','fz','my'])
            ca,sa=math.cos(math.radians(alpha)),math.sin(math.radians(alpha))
            cds,cls,cms=-(fx*ca+fz*sa),fx*sa-fz*ca,my/CHORD
            record.update(CLS=cls,CDS=cds,CMS25=cms)
            entry['states'].append(record)
            adf.append([MACH,REYNOLDS,alpha,0,-fx,0,-fz,0,cms,0,cds,0,cls,0,cms,0,cds,0,cls,0,cms,0])
        expected['polars'].append(entry)
        adfpath=base/'03-RESULTS/ADF'/f'{polar}.adf'
        adfpath.parent.mkdir(parents=True,exist_ok=True)
        adfpath.write_text('# SYNTHETIC pressure-only forces integrated across the five stations; no solver history.\n'
                          'MACH REYNOLDS ALPHA BETA CDB CYB CLB CRB25 CMB25 CNB25 CDS CYS CLS CRS25 CMS25 CNS25 CDW CYW CLW CRW25 CMW25 CNW25\n'
                          +'\n'.join(' '.join(f'{value:.15g}' for value in row) for row in adf)+'\n',encoding='utf-8')
        (run/'infout').write_text(
            f'JAMAL SYNTHETIC SCREENSHOT VALIDATION\nPOLAR: {number:03d}\nAIRCRAFT: SYNTHETIC_MULTI_ELEMENT\n'
            'CONFIGURATION: SCREENSHOT_RECONSTRUCTION\nDIMENSION_REF: SYNTHETIC\nNUMERIC_SET: SYNTHETIC\n'
            f'SREF[m2]: {SREF:.15g} CREF[m]: {CHORD:.15g} BREF[m]: {BREF}\n'
            'XREF[m]: 0 YREF[m]: 0 ZREF[m]: 0\n'
            f'p[Pa]: {P} qdin[Pa]: {Q} rho[kg/m3]: {RHO} V[m/s]: {VELOCITY:.15g}\n'
            f'Mach: {MACH:.15g} ptot[Pa]: {P*(1+.2*MACH*MACH)**3.5:.15g}\nReynolds: {REYNOLDS:.15E}\n'
            'FLP1: 0\n[CASES]\nCASE MACH REYNOLDS ALPHA BETA NAME ITERS\n'
            +'\n'.join(f'{i:04d} {MACH:.15g} {REYNOLDS:.15E} {a} 0 SYNTHETIC_{i:04d} 0' for i,a in enumerate(alphas,1))
            +'\nGrid_files: -\n',encoding='utf-8')
    write_json(base/'expected_values.json',expected)
    write_json(base/'screenshot_anchors.json',{'columns':['excel_row','x_m','ordinate_m','pressure_Pa_or_null'],
               'main':anchors(MAIN_ANCHORS),'flap':anchors(FLAP_ANCHORS),
               'note':'Sparse rounded visual readings, not exact CFD data. Other rows are interpolated.'})
    write_json(base/'jamal_dashboard_setup.json',{'version':'v25','configurations':[
        {'label':'Screenshot synthetic','base_directory':str(base),'polars':[1,2,3],
         'distribution_input':'pressure','drag_rise_dirs':[]}]})
    # Negative/zero-load reference is outside the discovered POLAR data tree.
    uniform=base/'validation_cases/uniform_pressure'
    curve(uniform/'section_state1_station0.000',[(x,z) for c in geometry for x,z,p in c],'geometry')
    curve(uniform/'cp_dist_state1_station0.000',[(x,P+Q*level) for c,level in zip(geometry,[.7,-.4]) for x,z,p in c],'absolute pressure')
    write_json(uniform/'expected.json',{'p':P,'qdin':Q,'fx':0,'fz':0,'element_cp':[.7,-.4]})
    (base/'README.md').write_text(readme(),encoding='utf-8')
    hashes={str(p.relative_to(base)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(base.rglob('*')) if p.is_file() and 'DASHBOARD' not in p.parts
            and p.name not in ['SHA256SUMS.json','validation_results.json']}
    write_json(base/'SHA256SUMS.json',hashes)
    return base,expected


def readme():
    return f'''# Screenshot-inspired multi-element synthetic CFD project

This is synthetic validation data, reconstructed from sparse rounded readings
in the supplied Excel photographs. It is not the original export or a CFD solution.

## Open in JAMAL

1. Select this folder as the base directory (it contains 02-RUNS and 03-RESULTS),
   or Load setup from jamal_dashboard_setup.json on the generating computer.
2. Select POLAR-001, POLAR-002 and POLAR-003; use Absolute pressure [Pa].
3. Generate the dashboard and open Distributions. Add overlays and compare at
   ALPHA=3 degrees or global CL=0.3. Centre station Y=0 resembles the screenshots.
4. If this folder is moved, update its path in the setup or select it manually.

## What follows the screenshots

Every paired curve has 603 samples in one block, data on lines 9–611:
main element lines 9–317 (309 points), flap lines 318–611 (294 points).
The main starts at (1.4791, 0.010859) and closes there. Its forward X is1.4742;
aft X is1.9022. The cove wall has X=1.8852, ordinate +0.020040 to -0.020040.
The flap starts/closes at (2.0347, 0.00016610), repeats its first sample,
and reaches forward X=1.8972. Thus the element X ranges overlap.
Repeated X at the nose/TE and the vertical wall are intentional.

screenshot_anchors.json contains the sparse readings. Geometry and baseline
pressure between anchors use shape-preserving cubic interpolation in row number,
not X. Small differences and intermediate rows are invented. Centre-station
POLAR-001/state1 reproduces the transcribed pressure anchors, including the
near-LE maximum and flap feature near X=1.9113. Other states are imposed loads.

## Invented flow and load sweeps

User-selected p={P:g} Pa and qdin=0.2*p={Q:g} Pa; BETA=0 throughout.
MACH={MACH:.9g}, constant Reynolds={REYNOLDS:.9g}; BREF=2 m,
CREF=overall section chord={CHORD:.7g} m; SREF=BREF*CREF={SREF:.7g} m2.
Five stations Y=-1,-0.5,0,0.5,1 m have identical geometry. Loading is multiplied
by 1-0.25*Y^2. Pressure references and all sweep conditions are synthetic.

- POLAR-001: screenshot-like baseline plus Cp increment -1.5*ALPHA*ordinate/chord.
  ALPHAs in file/state order: 0,2,4,6,-2 degrees.
- POLAR-002: the same geometry and baseline, with a stronger flap increment
  (-5*ALPHA-3)*ordinate/chord; main increment as POLAR-001.
  ALPHAs: 0,1,3,5,-2. This supplies a different ALPHA at common CL.
- POLAR-003: analytical Cp = -0.35*(X-Xmin)/chord
  -(1+1.6*ALPHA)*ordinate/chord + constant; constants0.4 main and-0.2 flap,
  before the same span factor. ALPHAs: 0,2,4,6,-2.
- validation_cases/uniform_pressure: different constant Cp on each element,
  so each element and combined Fx/Fz must be zero. Not loaded as a dashboard polar.

State1 is intentionally not the lowest ALPHA, testing original infout order.
Combined cl and x/c use the common all-element chord, as selected by the user.
ADF force/moment data are derived from these pressures, not copied from another
case. Global loads use piecewise-linear trapezoidal integration between stations.
Physical body coordinates are(-X,Y,-ordinate); moments refer to the body origin
(infout XREF=YREF=ZREF=0). No shear, viscous drag or solver convergence is invented.
Missing solver-history/mesh quality warnings are therefore expected; distribution
integrity should have zero warnings. These are not aero performance predictions.

## Independent checks

expected_values.json gives per-element and combined forces, sectional lift/cl,
and global CLS/CDS/CMS for every state/station. Screenshot-like reference forces
use separate two-point Gauss integration. Analytical forces use polygon area:
Fx=qdin*area*dCp/dX and Fz=qdin*area*dCp/dordinate. A constant pressure offset
cancels on each closed element. Forces project using the requested ALPHA.

From the repository root run:

    python -B jamal_dashboard/validate_screenshot_fixture.py

Regenerate from the source generator:

    python -B jamal_dashboard/generate_screenshot_fixture.py --report --zip

The generator only overwrites a folder bearing its SYNTHETIC_FIXTURE.txt marker.
Original fixtures and source JPEGs are never edited. SHA256SUMS.json records the
generated input/reference files; dashboard outputs are excluded.
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=DEFAULT)
    parser.add_argument('--report',action='store_true')
    parser.add_argument('--zip',action='store_true')
    args=parser.parse_args()
    base,_=build(args.output)
    if args.report:
        import jamal_dashboard_launcher_v25 as launcher
        payload=json.loads((base/'jamal_dashboard_setup.json').read_text())
        launcher._run_generation_job('screenshot-fixture',payload)
        result=launcher.job_snapshot('screenshot-fixture')
        if result['status']!='complete':
            raise RuntimeError(result)
        print(result['result']['report_path'])
    if args.zip:
        target=base.parent/(base.name+'.zip')
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(base.rglob('*')):
                if path.is_file() and '.jamal_cache' not in path.parts:
                    archive.write(path,base.name+'/'+path.relative_to(base).as_posix())
        with zipfile.ZipFile(target) as archive:
            assert archive.testzip() is None
        print(target)
    print(base)


if __name__=='__main__':
    main()
