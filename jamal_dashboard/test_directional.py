"""Directional-margin checks execute the actual generated JavaScript."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import jamal_dashboard_launcher_v25 as launcher

ROOT = Path(__file__).parent
FIXTURE = ROOT/'JAMAL_SYNTHETIC_CFD'
engine = launcher.ENGINE


class DirectionalTests(unittest.TestCase):
    def test_signed_derivative_duplicates_missing_data_and_reference_shift(self):
        html = engine.make_html([], [], {}, {'curves': [], 'static_margin': []}, {'curves': []}, {}, [])
        js = "const assert=require('node:assert/strict');\n"
        for start, end in [('bodyToStabilityVector', 'currentMomentReferenceMode'),
                           ('derivativeNonuniform', 'currentStaticMarginRows')]:
            js += html[html.index('function '+start+'('):html.index('function '+end+'(')]
        start = html.index('function directionalStaticMargin(')
        js += html[start:html.index('drawSmPlots=function()', start)]
        data = engine.read_polar_file(FIXTURE/'03-RESULTS/ADF/POLAR-003.adf')
        self.assertEqual(engine.detect_sweep_variable(data), 'BETA')
        js += '\nconst fixture='+json.dumps(data.to_dict(orient='records'))+';\n'
        js += r'''
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-8,`${a} != ${b}`);
const curve={case_label:'Synthetic',polar:'POLAR-003',curve_label:'Synthetic POLAR-003',sweep_var:'BETA',rows:fixture};
const result=directionalStaticMargin([curve]);
assert.equal(result.skipped.length,0);assert.equal(result.rows.length,7);
result.rows.forEach(r=>close(r.DIRECTIONAL_STATIC_MARGIN_PERCENT,15));
// Three-point nonuniform derivative, including endpoints, for a quadratic.
const nonlinear={...curve,rows:[-.4,-.15,0,.1,.6].map(x=>({ALPHA:3,BETA:-x,CYS:x,CNS25:2*x*x+3*x}))};
directionalStaticMargin([nonlinear]).rows.forEach(r=>close(r.DIRECTIONAL_STATIC_MARGIN_PERCENT,-100*(4*r.CYS+3)));
// Repeated coordinates average all samples, not repeated pairwise half averages.
const duplicates={...curve,rows:[{ALPHA:3,BETA:-1,CYS:-1,CNS25:-2},
  ...[2,4,6].map(y=>({ALPHA:3,BETA:0,CYS:0,CNS25:y})),{ALPHA:3,BETA:1,CYS:1,CNS25:10},
  {ALPHA:3,BETA:2,CYS:null,CNS25:999},{ALPHA:3,BETA:3,CYS:2,CNS25:null}]};
const dup=directionalStaticMargin([duplicates]);assert.equal(dup.rows.length,3);
dup.rows.forEach(r=>close(r.DIRECTIONAL_STATIC_MARGIN_PERCENT,-600));
for(const invalid of [{...curve,sweep_var:'ALPHA'},
 {...curve,rows:fixture.slice(0,2)},
 {...curve,rows:fixture.map((r,i)=>({...r,ALPHA:i}))},
 {...curve,rows:fixture.map(r=>({...r,CYS:0}))},
 {...curve,rows:fixture.map(r=>({...r,CNS25:null}))}]) {
 const bad=directionalStaticMargin([invalid]);assert.equal(bad.rows.length,0);assert.equal(bad.skipped.length,1);
}
let inputs={mode:'absolute',xAbs:3,yAbs:0,zAbs:.1};
function currentMomentInputs(){return inputs;}
const meta={xref:3,yref:0,zref:.1,cref:1.5555555556,bref:10};
let moved={...curve,rows:fixture.map(r=>shiftedRow(r,meta))};
directionalStaticMargin([moved]).rows.forEach(r=>close(r.DIRECTIONAL_STATIC_MARGIN_PERCENT,15));
inputs.xAbs=4;
moved={...curve,rows:fixture.map(r=>shiftedRow(r,meta))};
directionalStaticMargin([moved]).rows.forEach(r=>close(r.DIRECTIONAL_STATIC_MARGIN_PERCENT,15-10*Math.cos(3*Math.PI/180)));
// Changing the display reference never edits the input ADF rows.
fixture.forEach(r=>close(r.CNS25,-.15*r.CYS));
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'directional.js'
            path.write_text(js, encoding='utf-8')
            result = subprocess.run([shutil.which('node'), str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_beta_only_generation_without_optional_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for relative in ['03-RESULTS/ADF/POLAR-003.adf', '02-RUNS/POLAR-003/infout']:
                target = base/relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(FIXTURE/relative, target)
            payload = {'configurations': [{'label': 'Beta test', 'base_directory': str(base), 'polars': [3]}]}
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                launcher._run_generation_job('beta-only', payload)
            job = launcher.job_snapshot('beta-only')
            self.assertEqual(job['status'], 'complete', job.get('error'))
            report = json.loads((base/'03-RESULTS/DASHBOARD/dashboard.json').read_text(encoding='utf-8'))
            self.assertEqual(report['adf']['curves'][0]['sweep_var'], 'BETA')
            self.assertEqual(len(report['adf']['curves'][0]['rows']), 7)
            self.assertFalse(report['distributions']['series'])
            self.assertFalse(report['drag_rise']['curves'])
            self.assertEqual(report['summaries'][0]['meta']['bref'], 10)


if __name__ == '__main__':
    unittest.main()
