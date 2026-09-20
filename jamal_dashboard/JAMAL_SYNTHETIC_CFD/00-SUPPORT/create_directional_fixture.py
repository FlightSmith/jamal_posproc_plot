"""Reproduce POLAR-003: a beta sweep with analytical directional margin.

Run with Python 3. Existing differing files are never overwritten.
This adds ADF/infout only; solver histories and distributions are optional.
"""
from pathlib import Path
import json
import math


def build(base):
    alpha = 3.0
    betas = [-8.0, -5.0, -2.0, 0.0, 1.0, 4.0, 8.0]
    mach, reynolds = .2, 7.0518518519e6
    ca, sa = math.cos(math.radians(alpha)), math.sin(math.radians(alpha))
    columns = 'MACH REYNOLDS ALPHA BETA CDB CYB CLB CRB25 CMB25 CNB25 CDS CYS CLS CRS25 CMS25 CNS25 CDW CYW CLW CRW25 CMW25 CNW25'.split()
    lines = ['# SYNTHETIC beta sweep; analytical CYS=-0.8*beta(rad), CNS=+0.12*beta(rad).',
             '# Requested -100*dCNS/dCYS = +15 percent BREF at the source reference.', ' '.join(columns)]
    for beta in betas:
        b = math.radians(beta)
        cb, sb = math.cos(b), math.sin(b)
        cy, cn, cr = -.8*b, .12*b, -.06*b
        cl = .26625+.08875*alpha
        cd, cm = .02+.04*cl**2+.06*b**2, -.02-.1*cl
        values = [mach, reynolds, alpha, beta,
                  ca*cd-sa*cl, cy, sa*cd+ca*cl, ca*cr-sa*cn, cm, sa*cr+ca*cn,
                  cd, cy, cl, cr, cm, cn,
                  cb*cd-sb*cy, sb*cd+cb*cy, cl, cb*cr+sb*cm, -sb*cr+cb*cm, cn]
        lines.append(' '.join(f'{v:.12E}' for v in values))
    original = (base/'02-RUNS/POLAR-001/infout').read_text(encoding='utf-8')
    prefix = original.split('=====================================[CASES]')[0]
    prefix = prefix.replace('POLAR: 001', 'POLAR: 003').replace('SYNTHETIC_WING', 'SYNTHETIC_BETA_SWEEP')
    cases = ['=====================================[CASES]======================================',
             'CASE       MACH   REYNOLDS      ALPHA       BETA  NAME                       ITERS']
    for i, beta in enumerate(betas, 1):
        cases.append(f'{i:04d} {mach:.3f} {reynolds:.10E} {alpha:.2f} {beta:.2f} SYNTHETIC-BETA-{i:02d} 0')
    expected = {'polar': 'POLAR-003', 'alpha': alpha, 'betas': betas,
                'dCYS_dBeta_rad': -.8, 'dCNS_dBeta_rad': .12,
                'directional_static_margin_percent_bref': 15.0,
                'axis': 'Stability', 'reference': 'Original infout reference',
                'note': 'Signed -100*dCN/dCY; no extra BREF division.'}
    files = {base/'03-RESULTS/ADF/POLAR-003.adf': '\n'.join(lines)+'\n',
             base/'02-RUNS/POLAR-003/infout': prefix+'\n'.join(cases)+'\n',
             base/'expected_directional_values.json': json.dumps(expected, indent=2)+'\n'}
    for path, content in files.items():
        if path.exists() and path.read_text(encoding='utf-8') != content:
            raise FileExistsError(f'Refusing to overwrite changed fixture: {path}')
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode('utf-8'))


if __name__ == '__main__':
    build(Path(__file__).resolve().parents[1])
