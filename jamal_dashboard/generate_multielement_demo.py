"""Create an isolated wing/flap example; never modify the original CFD fixtures.

Run with Python from any directory. Output is in DASHBOARD/multielement_demo.
The geometry illustrates the screenshot topology; it is not a transcription.
"""
from pathlib import Path
import math
import shutil

import jamal_dashboard_launcher_v25 as launcher
import jamal_distributions as distributions


ROOT = Path(__file__).resolve().parent
MAIN = [(0,0),(.25,.1),(.8,.08),(1,.05),(.9,.05),(.9,-.05),
        (1,-.05),(.8,-.08),(.25,-.1),(0,0)]
FLAP = [(1.4,0),(1.15,-.03),(.95,0),(1.15,.03),(1.4,0)]


def sampled(contour, start=0):
    points = [(a[0]+(b[0]-a[0])*i/24,a[1]+(b[1]-a[1])*i/24)
              for a,b in zip(contour,contour[1:]) for i in range(24)]
    points = points[start:]+points[:start]
    return points+points[:1]


def curve(path, rows):
    path.write_text('*KEYWORD\n*DEFINE_CURVE_TITLE\nSynthetic multi-element example\n'
                    '$ ABSCISSA ORDINATE\n'+'\n'.join(f'{x:.16g} {y:.16g}' for x,y in rows)
                    +'\n*END\n',encoding='utf-8')


def build():
    base = ROOT/'DASHBOARD/multielement_demo/CFD'
    if not base.exists():
        shutil.copytree(ROOT/'JAMAL_SYNTHETIC_CFD',base,
                        ignore=shutil.ignore_patterns('DASHBOARD','__pycache__','VTAIL',
                                                     'multi-element_airfoil_cp','*.zip','total_force_state*'))
    for number in (1,2):
        info = launcher.ENGINE.parse_infout(base/f'02-RUNS/POLAR-{number:03d}/infout')
        component = base/f'03-RESULTS/DISTCLCP/POLAR-{number:03d}/WING'
        original = ROOT/f'JAMAL_SYNTHETIC_CFD/03-RESULTS/DISTCLCP/POLAR-{number:03d}/WING'
        main = sampled(MAIN,19)  # Arbitrary upper-surface starting point.
        flap = sampled(FLAP)
        flap.insert(0,flap[0])  # Consecutive duplicate, as in the Excel sample.
        angle = math.radians(-12 if number==2 else 0)
        flap = [(.95+(x-.95)*math.cos(angle)-z*math.sin(angle),
                 (x-.95)*math.sin(angle)+z*math.cos(angle)) for x,z in flap]
        template = main+flap
        width = max(x for x,z in template)-min(x for x,z in template)
        for source in original.glob('section_state1_station*'):
            original_points = distributions.parse_curve(source)
            xmin,xmax = min(p[0] for p in original_points),max(p[0] for p in original_points)
            c = xmax-xmin
            points = [(xmin+c*x/width,c*z/width) for x,z in template]
            curve(component/source.name,points)
            y = float(source.name.split('station')[1])
            for state,case in enumerate(info['cases'],1):
                loading = (.5+.09*case['alpha'])*(1-.5*(2*y/info['meta']['bref'])**2)
                values = [(x,info['meta']['p']+info['meta']['qdin']*(.15*(x-xmin)/c-10*loading*z/c))
                          for x,z in points]
                curve(component/source.name.replace('section_state1',f'cp_dist_state{state}'),values)
    (base/'MULTIELEMENT_DEMO.txt').write_text(
        'Synthetic geometry and pressure, inspired by the screenshot topology.\n'
        'POLAR-001 has an aligned flap; POLAR-002 has a 12-degree deflected flap.\n'
        'Global ADF polars are copied from the original fixture for target-CL UI\n'
        'demonstration; they are not a span integral of this invented pressure field.\n'
        'Pressure Cp is linear in X and ordinate, with ALPHA-dependent loading.\n',encoding='utf-8')
    payload = {'configurations':[{'label':'Multi-element demo','base_directory':str(base),
                                 'polars':[1,2],'drag_rise_dirs':['BASELINE'],
                                 'distribution_input':'pressure'}]}
    launcher._run_generation_job('multielement-demo',payload)
    job = launcher.job_snapshot('multielement-demo')
    if job['status']!='complete':
        raise RuntimeError(job)
    print(job['result']['report_path'])


if __name__=='__main__':
    build()
