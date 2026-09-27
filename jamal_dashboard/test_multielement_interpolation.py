"""Ordered-contour interpolation checks for overlapping, recessed elements."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).parent


class MultiElementInterpolationTests(unittest.TestCase):
    def run_javascript(self, checks):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Install Node.js for target-distribution checks')
        script = r"""
const assert=require('node:assert/strict');
const {distributionAtTarget}=require(MODULE_PATH);
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-9, `${a} != ${b}`);
const clone=x=>JSON.parse(JSON.stringify(x));
const main=[[.3,.1],[.8,.08],[1,.03],[.9,.03],[.9,-.03],[1,-.03],[.6,-.1],[0,0],[.3,.1]];
// Overlapping X domains and a repeated full coordinate at the aft contour start.
const aft=[[1.4,0],[1.4,0],[1.15,-.04],[.95,0],[1.15,.04],[1.4,0]];
const geometry={y:1,xmin:0,xmax:1.4,chord:1.4};
function element(points,id,alpha,sides) {
  const x=points.map(p=>p[0]),z=points.map(p=>p[1]);
  const curve=indices=>({x:indices.map(i=>x[i]),xc:indices.map(i=>x[i]/1.4),
    values:indices.map(i=>2*alpha+(1+alpha)*x[i]+3*z[i])});
  const result={id,name:id,...curve(points.map((_,i)=>i)),airfoil:{x,ordinate:z},
    surfaces:Object.fromEntries(Object.entries(sides).map(([name,indices])=>[name,curve(indices)]))};
  const area=Math.abs(points.slice(1).reduce((sum,p,i)=>sum+points[i][0]*p[1]-p[0]*points[i][1],0))/2;
  result.fx=1000*(1+alpha)*area;result.fz=3000*area;
  return result;
}
function state(alpha) {
  const elements=[element(main,'element-1',alpha,{upper:[7,8,1,2],lower:[7,6,5],'trailing edge / cove':[2,3,4,5]}),
    element(aft,'element-2',alpha,{upper:[3,4,5],lower:[3,2,1,0]})];
  const cp={...geometry,elements,airfoil:{x:elements.flatMap(e=>e.airfoil.x),ordinate:elements.flatMap(e=>e.airfoil.ordinate)}};
  for(const key of ['x','xc','values']) cp[key]=elements.flatMap(e=>e[key]);
  const fx=elements.reduce((sum,e)=>sum+e.fx,0),fz=elements.reduce((sum,e)=>sum+e.fz,0);
  const lift=fx*Math.sin(alpha*Math.PI/180)-fz*Math.cos(alpha*Math.PI/180);
  return {configuration:'Wing',polar:'POLAR-001',component:'WING',state:alpha+1,
    alpha,beta:0,mach:.2,reynolds:1e6,qdin:1000,p:101325,bref:10,cl_global:alpha/10,
    span:[{...geometry,fx,fz,lift,cl:lift/1400}],cp:[cp]};
}
function succeeds(states,mode,target) {
  const result=distributionAtTarget(states,mode,target);assert.equal(result.error,null);
  assert.ok(result.series);return result.series;
}
function fails(states,pattern) {
  const result=distributionAtTarget(states,'alpha',5);assert.equal(result.series,null);
  assert.match(result.error,pattern);
}
""".replace('MODULE_PATH', json.dumps(str(ROOT / 'distribution_interpolation.js')))
        result = subprocess.run([node, '-e', script + checks], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_ordered_pressure_interpolation_preserves_cove_duplicate_x_and_elements(self):
        self.run_javascript(r"""
const a=state(0),b=state(10),before=JSON.stringify([a,b]);
for(const mode of ['alpha','cl']) {
  const result=succeeds([b,a],mode,mode==='alpha'?2.5:.25),expected=state(2.5);
  assert.equal(result.cp[0].elements.length,2);assert.equal('surfaces' in result.cp[0],false);
  assert.deepEqual(result.cp[0].x,a.cp[0].x);
  result.cp[0].values.forEach((v,i)=>near(v,expected.cp[0].values[i]));
  result.cp[0].elements.forEach((e,index)=>{
    const want=expected.cp[0].elements[index];
    assert.equal(e.id,want.id);assert.deepEqual(e.x,want.x);assert.deepEqual(e.airfoil,want.airfoil);
    e.values.forEach((v,i)=>near(v,want.values[i]));near(e.fx,want.fx);near(e.fz,want.fz);
    for(const side of Object.keys(want.surfaces)) {
      assert.deepEqual(e.surfaces[side].xc,want.surfaces[side].xc);
      e.surfaces[side].values.forEach((v,i)=>near(v,want.surfaces[side].values[i]));
    }
  });
  const cove=result.cp[0].elements[0].surfaces['trailing edge / cove'];
  assert.deepEqual(cove.x,[1,.9,.9,1]);assert.notEqual(cove.values[1],cove.values[2]);
  assert.deepEqual(result.cp[0].elements[1].x.slice(0,2),[1.4,1.4]);
  near(result.span[0].fx,expected.span[0].fx);near(result.span[0].fz,expected.span[0].fz);
  near(result.span[0].lift,expected.span[0].lift);near(result.span[0].cl,expected.span[0].cl);
  near(result.interpolation.weight,.25);assert.deepEqual(result.interpolation.source_states,[1,11]);
}
assert.equal(JSON.stringify([a,b]),before);
""")

    def test_exact_targets_classify_element_surfaces_and_deep_copy(self):
        self.run_javascript(r"""
const a=state(0),b=state(10);
for(const mode of ['alpha','cl']) {
  const result=succeeds([a,b],mode,0);
  assert.deepEqual(result.cp,a.cp);assert.notEqual(result.cp[0].elements,a.cp[0].elements);
  assert.equal(result.interpolated,false);assert.equal(result.interpolation.diagnostics,undefined);
}
delete a.cp[0].elements[1].surfaces.lower;
assert.ok(succeeds([a,b],'alpha',0).interpolation.diagnostics.some(x=>x.includes('without surface classification')));
""")

    def test_element_identity_geometry_and_branch_correspondence_are_required(self):
        self.run_javascript(r"""
const a=state(0),b=state(10);
let c=clone(b);c.cp[0].elements.pop();fails([a,c],/element set/);
c=clone(b);delete c.cp[0].elements;fails([a,c],/element set/);
c=clone(b);c.cp[0].elements.reverse();fails([a,c],/element identities/);
c=clone(b);c.cp[0].elements[1].id='element-1';fails([a,c],/element identities/);
c=clone(b);c.cp[0].elements[0].airfoil.ordinate[3]+=.01;fails([a,c],/section outline/);
c=clone(b);c.cp[0].elements[0].surfaces.upper.x.reverse();fails([a,c],/ordered.*samples/);
c=clone(b);delete c.cp[0].elements[0].surfaces['trailing edge / cove'];fails([a,c],/surface branches/);
c=clone(b);delete c.cp[0].elements[0].surfaces.lower;fails([a,c],/surface branches/);
c=clone(b);c.cp[0].elements[0].values.pop();fails([a,c],/pressure samples/);
c=clone(b);c.cp[0].elements[0].surfaces.upper.values[0]=null;fails([a,c],/pressure samples/);
c=clone(b);c.cp[0].elements[0].xc[0]+=.01;fails([a,c],/ordered.*samples/);
const inconsistent=[clone(a),clone(b)];inconsistent.forEach(s=>s.cp[0].elements[0].xc[0]+=.01);
fails(inconsistent,/inconsistent.*x\/c/);
""")

    def test_new_single_element_records_keep_top_level_surfaces_and_missing_loads(self):
        self.run_javascript(r"""
const a=state(0),b=state(10);
for(const s of [a,b]) {
  const e=s.cp[0].elements[0];s.cp[0].elements=[e];s.cp[0].surfaces=clone(e.surfaces);
  for(const key of ['x','xc','values']) s.cp[0][key]=[...e[key]];
  s.cp[0].airfoil=clone(e.airfoil);
}
const result=succeeds([a,b],'alpha',5);
assert.deepEqual(result.cp[0].surfaces,result.cp[0].elements[0].surfaces);
assert.notEqual(result.cp[0].surfaces,a.cp[0].surfaces);
b.span[0].fz=null;b.span[0].cl=null;b.span[0].lift=null;
const missing=succeeds([a,b],'alpha',5);
assert.equal(missing.span[0].lift,null);assert.equal(missing.span[0].cl,null);
assert.ok(missing.cp[0].elements[0].values.every(Number.isFinite));
""")


if __name__ == '__main__':
    unittest.main()
