"""Pure JavaScript target-distribution checks, independent of Plotly/the DOM."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).parent


class DistributionInterpolationTests(unittest.TestCase):
    def run_javascript(self, checks):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Install Node.js for target-distribution checks')
        script = r"""
const assert=require('node:assert/strict');
const {distributionAtTarget}=require(MODULE_PATH);
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-9, `${a} != ${b}`);
function state(alpha,cl=alpha/10,number=alpha+1,grid=[0,.5,1]) {
  const upper={xc:[...grid],x:grid.map(x=>2+2*x),values:grid.map(x=>-alpha-x)};
  const lower={xc:[...grid],x:grid.map(x=>2+2*x),values:grid.map(x=>alpha+2*x)};
  const geometry={y:1,xmin:2,xmax:4,chord:2};
  return {configuration:'Wing',polar:'POLAR-001',component:'WING',state:number,
    alpha,beta:0,mach:.2,reynolds:1e6,qdin:1000,p:101325,bref:10,cl_global:cl,
    span:[{...geometry,cl:2*alpha*Math.cos(alpha*Math.PI/180),lift:4000*alpha*Math.cos(alpha*Math.PI/180),fx:0,fz:-4000*alpha}],
    cp:[{...geometry,x:upper.x.slice().reverse().concat(lower.x),
      xc:upper.xc.slice().reverse().concat(lower.xc),values:upper.values.slice().reverse().concat(lower.values),
      surfaces:{upper,lower},airfoil:{x:[4,2,4],ordinate:[0,.1,0]}}]};
}
const clone=x=>JSON.parse(JSON.stringify(x));
function succeeds(states,mode,target) {
  const result=distributionAtTarget(states,mode,target);assert.equal(result.error,null);
  assert.ok(result.series);return result.series;
}
function fails(states,mode,target,pattern) {
  const result=distributionAtTarget(states,mode,target);assert.equal(result.series,null);
  assert.match(result.error,pattern);
}
""".replace('MODULE_PATH', json.dumps(str(ROOT / 'distribution_interpolation.js')))
        result = subprocess.run([node, '-e', script + checks], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_alpha_and_cl_interpolation_separate_surface_grids_and_preserve_inputs(self):
        self.run_javascript(r"""
const a=state(0,0,8,[1,.5,0]),b=state(10,1,2,[0,.25,.75,1]);
const before=JSON.stringify([a,b]);
for(const mode of ['alpha','cl']) {
  const s=succeeds([b,a],mode,mode==='alpha'?2.5:.25);
  near(s.alpha,2.5);near(s.cl_global,.25);
  near(s.span[0].cl,5*Math.cos(2.5*Math.PI/180));near(s.span[0].lift,10000*Math.cos(2.5*Math.PI/180));
  assert.ok(Math.abs(s.span[0].lift-(a.span[0].lift*.75+b.span[0].lift*.25))>1);
  assert.deepEqual(s.source_states,[8,2]);assert.equal(s.interpolated,true);
  assert.deepEqual(s.cp[0].surfaces.upper.xc,[0,.25,.5,.75,1]);
  s.cp[0].surfaces.upper.xc.forEach((x,i)=>near(s.cp[0].surfaces.upper.values[i],-2.5-x));
  s.cp[0].surfaces.lower.xc.forEach((x,i)=>near(s.cp[0].surfaces.lower.values[i],2.5+2*x));
  assert.deepEqual(s.cp[0].xc,[1,.75,.5,.25,0,0,.25,.5,.75,1]);
  near(s.interpolation.weight,.25);assert.equal(s.cp[0].x[1],3.5);
}
assert.equal(JSON.stringify([a,b]),before);
a.span[0].fx=200;b.span[0].fx=600;
const rotated=succeeds([a,b],'alpha',2.5),angle=2.5*Math.PI/180;
near(rotated.span[0].fx,300);near(rotated.span[0].fz,-10000);
near(rotated.span[0].lift,300*Math.sin(angle)+10000*Math.cos(angle));
near(rotated.span[0].cl,rotated.span[0].lift/2000);
const dense=succeeds([state(0,0,1,Array.from({length:2049},(_,i)=>i/2048)),
  state(10,1,2,Array.from({length:1537},(_,i)=>i/1536))],'alpha',2.5);
assert.equal(dense.cp[0].surfaces.upper.xc.length,3073);
dense.cp[0].surfaces.upper.xc.forEach((x,i)=>near(dense.cp[0].surfaces.upper.values[i],-2.5-x));
dense.cp[0].surfaces.lower.xc.forEach((x,i)=>near(dense.cp[0].surfaces.lower.values[i],2.5+2*x));
""")

    def test_exact_targets_endpoints_single_state_and_no_extrapolation(self):
        self.run_javascript(r"""
const a=state(0),b=state(10);
for(const mode of ['alpha','cl']) for(const original of [a,b]) {
  const s=succeeds([b,a],mode,mode==='alpha'?original.alpha:original.cl_global);
  assert.equal(s.interpolated,false);assert.equal(s.state,original.state);
  assert.deepEqual(s.cp,original.cp);assert.notEqual(s.cp,original.cp);
  assert.deepEqual(s.source_states,[original.state]);
}
succeeds([a],'alpha',0);succeeds([a],'cl',0);
fails([a],'alpha',1,/outside/);fails([a,b],'alpha',-1,/extrapolation/);
fails([a,b],'alpha',11,/extrapolation/);fails([a,b],'cl',1.1,/extrapolation/);
fails([a,b],'alpha',NaN,/finite/);fails([a,b],'cl',null,/finite/);
fails([],'cl',.5,/No distribution/);fails([a,b],'beta',0,/ALPHA or CL/);
""")

    def test_ambiguous_cl_stall_plateau_duplicates_and_invalid_adf(self):
        self.run_javascript(r"""
fails([state(0,0),state(10,1),state(15,.5)],'cl',.75,/multiple ALPHA/);
fails([state(0,0),state(10,1),state(15,.5)],'cl',.5,/multiple ALPHA/);
fails([state(0,0),state(5,.5),state(10,.5)],'cl',.5,/constant.*ambiguous/);
fails([state(0,0),state(0,1)],'alpha',0,/Duplicate ALPHA/);
fails([state(0,0),state(10,null)],'cl',.5,/no unique, finite ADF CLS/);
near(succeeds([state(0,0),state(10,1),state(15,.5)],'cl',1).alpha,10);
near(succeeds([state(0,0),state(10,1),state(15,.5)],'cl',.25).alpha,2.5);
near(succeeds([state(0,1),state(10,0)],'cl',.25).alpha,7.5);
""")

    def test_variable_flow_beta_group_and_reference_rejected(self):
        self.run_javascript(r"""
const a=state(0),b=state(10);
for(const key of ['beta','mach','reynolds','qdin','p']) {
  const changed=clone(b);changed[key]+=Math.max(1,Math.abs(changed[key])*.01);
  fails([a,changed],'alpha',5,/constant/);
  changed[key]=null;fails([a,changed],'alpha',5,/constant/);
}
for(const key of ['configuration','polar','component']) {
  const changed=clone(b);changed[key]='other';fails([a,changed],'alpha',5,/one configuration/);
}
const changed=clone(b);changed.bref=11;fails([a,changed],'alpha',5,/BREF/);
const negative=[clone(a),clone(b)];negative.forEach(s=>s.qdin=-1);
fails(negative,'alpha',5,/positive/);
""")

    def test_missing_or_duplicate_stations_and_changed_geometry_are_explicit(self):
        self.run_javascript(r"""
const a=state(0),b=state(10);
let c=clone(b);c.cp=[];fails([a,c],'alpha',5,/Cp station data is missing/);
c=clone(b);c.cp.push({...clone(c.cp[0]),y:2});fails([a,c],'alpha',5,/sets differ/);
c=clone(b);c.cp[0].y=2;fails([a,c],'alpha',5,/no unique match/);
c=clone(b);c.cp[0].y+=.5e-6;succeeds([a,c],'alpha',5);
c=clone(b);c.span=[];fails([a,c],'alpha',5,/Load station sets differ/);
for(const key of ['xmin','xmax','chord']) {
 c=clone(b);c.cp[0][key]+=.1;fails([a,c],'alpha',5,/changes/);
}
c=clone(b);c.cp[0].airfoil.ordinate[1]+=.1;fails([a,c],'alpha',5,/outline changes/);
const duplicate=[clone(a),clone(b)];duplicate.forEach(s=>s.cp.push(clone(s.cp[0])));
fails(duplicate,'alpha',5,/no unique match/);
""")

    def test_common_domain_diagnostics_and_branch_validation(self):
        self.run_javascript(r"""
const a=state(0),b=state(10,1,2,[.1,.4,.9]);
const s=succeeds([a,b],'alpha',5);
assert.deepEqual(s.cp[0].surfaces.upper.xc,[.1,.4,.5,.9]);
assert.ok(s.interpolation.diagnostics.some(x=>x.includes('common x/c')));
let c=state(10);delete c.cp[0].surfaces;fails([a,c],'alpha',5,/identified upper surface/);
c=state(10);c.cp[0].surfaces.lower.values[0]=null;fails([a,c],'alpha',5,/invalid lower/);
c=state(10);c.cp[0].surfaces.upper={xc:[0,.5,.5,1],values:[0,1,2,3]};
fails([a,c],'alpha',5,/same x\/c/);
c=state(10,1,2,[2,3]);fails([a,c],'alpha',5,/no overlapping/);
const noLoads=[clone(a),state(10)];noLoads.forEach(s=>s.span=[]);
assert.ok(succeeds(noLoads,'alpha',5).interpolation.diagnostics.some(x=>x.includes('No spanwise')));
const missingForce=[clone(a),state(10)];missingForce[1].span[0].fz=null;
const unavailable=succeeds(missingForce,'alpha',5);
assert.equal(unavailable.span[0].lift,null);assert.equal(unavailable.span[0].cl,null);
assert.ok(unavailable.interpolation.diagnostics.some(x=>x.includes('Loads at')));
""")

    def test_nonzero_beta_and_missing_endpoint_loads_remain_unavailable(self):
        self.run_javascript(r"""
const a=state(0),b=state(10);
for(const s of [a,b]) {s.beta=3;s.span[0].cl=null;s.span[0].lift=null;}
const result=succeeds([a,b],'alpha',5);
assert.equal(result.beta,3);assert.equal(result.span[0].fx,0);assert.equal(result.span[0].fz,-20000);
assert.equal(result.span[0].cl,null);assert.equal(result.span[0].lift,null);
assert.ok(result.cp[0].surfaces.upper.values.every(Number.isFinite));
assert.ok(result.interpolation.diagnostics.some(x=>x.includes('nonzero BETA')));
const exact=succeeds([a,b],'alpha',0);assert.equal(exact.span[0].cl,null);assert.equal(exact.span[0].lift,null);
for(const key of ['cl','lift']) {
  const left=state(0),right=state(10);right.span[0][key]=null;
  const missing=succeeds([left,right],'alpha',5);
  assert.equal(missing.span[0].cl,null);assert.equal(missing.span[0].lift,null);
}
""")

    def test_only_explicit_legacy_cp_allows_consistently_absent_reference_pressure(self):
        self.run_javascript(r"""
const a=state(0),b=state(10);
for(const s of [a,b]) {s.input_kind='cp';s.p=null;}
near(succeeds([a,b],'alpha',5).alpha,5);near(succeeds([a,b],'cl',.5).alpha,5);
delete b.p;succeeds([a,b],'alpha',5);succeeds([a],'alpha',0);
b.p=101325;fails([a,b],'alpha',5,/reference pressure p/);
b.p=null;b.input_kind='pressure';fails([a,b],'alpha',5,/reference pressure p/);
a.input_kind='pressure';fails([a,b],'alpha',5,/reference pressure p/);
delete a.input_kind;delete b.input_kind;fails([a,b],'alpha',5,/reference pressure p/);
""")

    def test_exact_unclassified_cp_preserved_with_explicit_diagnostics(self):
        self.run_javascript(r"""
const a=state(0),b=state(10);
delete a.cp[0].surfaces;a.span[0].cl=null;a.span[0].lift=null;
const direct=distributionAtTarget([a,b],'alpha',0),result=direct.series;
assert.equal(direct.error,null);assert.deepEqual(result.cp,a.cp);
assert.equal(result.span[0].cl,null);assert.equal(result.span[0].lift,null);
assert.ok(direct.diagnostics.some(x=>x.includes('without surface classification')));
assert.ok(direct.diagnostics.some(x=>x.includes('recorded sectional loads are unavailable')));
assert.deepEqual(result.interpolation.diagnostics,direct.diagnostics);
fails([a,b],'alpha',5,/identified upper surface/);
""")


if __name__ == '__main__':
    unittest.main()
