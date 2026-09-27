"""Analytical pressure forces and end-to-end absolute-pressure input checks."""
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import jamal_dashboard_launcher_v25 as launcher
import jamal_distributions as dist

ROOT = Path(__file__).parent


class PressureTests(unittest.TestCase):
    def setUp(self):
        self.geometry = [[0,0],[.5,.1],[1,0],[.5,-.1],[0,0]]
        self.p, self.q = 100000., 2000.

    def section(self, values, geometry=None):
        geometry = geometry or self.geometry
        return dist.pressure_section([[r[0],self.p+self.q*v] for r,v in zip(geometry,values)],
                                     geometry,self.p,self.q)

    def test_uniform_absolute_pressure_gives_zero_force(self):
        for value in (0, 3, -2):
            section=self.section([value]*5)
            self.assertAlmostEqual(section['fx'],0)
            self.assertAlmostEqual(section['fz'],0)
            self.assertEqual(section['values'],[value]*5)

    def test_known_normal_force_and_reversed_contour(self):
        section=self.section([0,-1,0,1,0])
        self.assertAlmostEqual(section['fx'],0)
        self.assertAlmostEqual(section['fz'],-self.q)
        self.assertEqual(section['surfaces']['upper']['values'],[0,-1,0])
        self.assertEqual(section['surfaces']['lower']['values'],[0,1,0])
        reverse=self.section([0,1,0,-1,0],list(reversed(self.geometry)))
        self.assertEqual(section['surfaces'],reverse['surfaces'])
        self.assertAlmostEqual(reverse['fz'],section['fz'])
        # Pressure level cannot determine the surface: reversed loading is valid.
        reversed_load=self.section([0,1,0,-1,0])
        self.assertEqual(reversed_load['surfaces']['upper']['values'],[0,1,0])
        self.assertAlmostEqual(reversed_load['fz'],self.q)

    def test_pressure_gradient_force_from_enclosed_area(self):
        # Integral of p=p_inf+q*x on the diamond: body Fx=q*area, Fz=0.
        section=self.section([p[0] for p in self.geometry])
        self.assertAlmostEqual(section['fx'],self.q*.1)
        self.assertAlmostEqual(section['fz'],0)

    def test_malformed_or_unresolved_contours_do_not_invent_loads(self):
        points=[[x,self.p] for x,z in self.geometry]
        with self.assertRaisesRegex(ValueError,'point order'):
            dist.pressure_section(points[:-1],self.geometry,self.p,self.q)
        with self.assertRaisesRegex(ValueError,'p\\[Pa\\]'):
            dist.pressure_section(points,self.geometry,None,self.q)
        for q in (0,-1,float('nan')):
            with self.assertRaises(ValueError):
                dist.pressure_section(points,self.geometry,self.p,q)
        # A crossing contour remains invalid; closed non-crossing coves are now supported.
        bad=[[0,0],[.7,.1],[.4,-.2],[1,0],[.5,-.1],[0,0]]
        with self.assertRaisesRegex(ValueError,'intersects'):
            self.section([0]*6,bad)

    def test_pressure_loader_projection_ignores_force_file_and_matches_adf(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); component=root/'03-RESULTS/DISTCLCP/POLAR-001/WING'
            component.mkdir(parents=True)
            run=root/'02-RUNS/POLAR-001';run.mkdir(parents=True)
            (run/'infout').write_text('p[Pa]: 1D5 qdin[Pa]: 2E3\n')
            def curve(path,points):
                path.write_text('$ ABSCISSA ORDINATE\n'+'\n'.join(f'{x} {y}' for x,y in points)+'\n*END\n')
            curve(component/'section_state1_station0',self.geometry)
            curve(component/'cp_dist_state1_station0',[[g[0],self.p+self.q*v] for g,v in zip(self.geometry,[0,-1,0,1,0])])
            (component/'total_force_state1').write_text('this must never be parsed')
            info={'meta':{'p':self.p,'qdin':self.q,'bref':10,'mach':.2,'reynolds':1e6},
                  'cases':[{'case':'0001','alpha':30,'beta':0,'mach':.2,'reynolds':1e6}]}
            cfg=[{'label':'Wing','polars':[1],'base_directory':str(root),'runs_directory':str(root/'02-RUNS')}]
            with patch.object(dist,'parse_force',side_effect=AssertionError('force file read')):
                data=dist.read_distributions(cfg,[],lambda _:info,root/'cache')
            self.assertEqual(data['issues'],[])
            series=data['series'][0];span=series['span'][0]
            self.assertAlmostEqual(span['cl'],math.cos(math.radians(30)))
            self.assertAlmostEqual(span['lift'],self.q*math.cos(math.radians(30)))
            self.assertEqual(series['cp'][0]['values'],[0,-1,0,1,0])
            self.assertEqual(data['counts'],{'parsed':2,'cached':0})
            adf={'curves':[{'case_label':'Wing','polar':'POLAR-001','rows':[
                {'ALPHA':0,'BETA':0,'MACH':.2,'REYNOLDS':1e6,'CLS':.1},
                {'ALPHA':30,'BETA':0,'MACH':.2,'REYNOLDS':1e6,'CLS':.8}]}]}
            dist.attach_global_lift(data,adf);self.assertEqual(series['cl_global'],.8)
            adf['curves'][0]['rows'].append(adf['curves'][0]['rows'][-1].copy())
            dist.attach_global_lift(data,adf);self.assertIsNone(series['cl_global'])
            info['meta']['p'] += self.q
            changed=dist.read_distributions(cfg,[],lambda _:info,root/'cache')
            self.assertEqual(changed['counts'],{'parsed':0,'cached':2})
            self.assertEqual(changed['series'][0]['cp'][0]['values'],[-1,-2,-1,0,-1])
            self.assertAlmostEqual(changed['series'][0]['span'][0]['cl'],span['cl'])
            meta=launcher.ENGINE.parse_infout(run/'infout')['meta']
            self.assertEqual(meta['p'],self.p);self.assertEqual(meta['qdin'],self.q)
            info['meta'].pop('p')
            missing=dist.read_distributions(cfg,[],lambda _:info,root/'cache')
            self.assertEqual(missing['series'][0]['cp'],[])
            self.assertTrue(missing['issues'])

    def test_pressure_format_explicit_and_scale_validation(self):
        points=[[x,v] for (x,_),v in zip(self.geometry,[0,-1,0,1,0])]
        legacy=dist.pressure_section(points,self.geometry,None,self.q,'cp')
        self.assertEqual(legacy['values'],[0,-1,0,1,0])
        js=(ROOT/'distributions.js').read_text(encoding='utf-8').split('(() => {',1)[0]
        js += """
const assert=require('node:assert/strict');
const series=[{cp:[{values:[-2,0,1]}]}];
assert.deepEqual(distributionCpRange(series,'manual','-3','2').range,[2,-3]);
assert.deepEqual(distributionCpRange(series,'auto','','').range,[1.24,-2.24]);
for(const limits of [['1','1'],['2','-1'],['','2'],['NaN','2']]) {
  const scale=distributionCpRange(series,'manual',...limits);
  assert.ok(scale.error); assert.deepEqual(scale.range,[1.24,-2.24]);
}
"""
        completed=subprocess.run([shutil.which('node'),'-e',js],capture_output=True,text=True)
        self.assertEqual(completed.returncode,0,completed.stderr)


if __name__=='__main__':
    unittest.main()
