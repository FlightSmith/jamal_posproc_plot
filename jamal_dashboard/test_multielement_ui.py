"""Verify the traces actually passed to Plotly for separate section elements."""
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).parent


class MultiElementUITests(unittest.TestCase):
    def run_javascript(self, checks):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Install Node.js for distribution UI checks')
        helpers = (ROOT / 'distributions.js').read_text(encoding='utf-8').split('(() => {', 1)[0]
        script = r"""
const assert=require('node:assert/strict');
const branch=(x,values)=>({x,xc:x.map(v=>(v-2)/2),values});
const main={id:'element-1',name:'Element 1',
  surfaces:{upper:branch([2,3,3.1],[0,-1,-.4]),lower:branch([2,3,3.1],[0,.6,.3]),
    'trailing edge / cove':branch([3.1,3,3,3.1],[-.4,-.2,.1,.3])},
  airfoil:{x:[2,3,3.1,3,3,3.1,3,2],ordinate:[0,.1,.04,.04,-.04,-.04,-.1,0]}};
const flap={id:'element-2',name:'Element 2',
  surfaces:{upper:branch([3,3.5,4],[0,-.7,0]),lower:branch([3,3.5,4],[0,.4,0])},
  airfoil:{x:[4,3.5,3,3.5,4],ordinate:[0,.06,0,-.06,0]}};
const point={xmin:2,xmax:4,chord:2,elements:[main,flap],
  // Legacy concatenations must never create a connector when elements exist.
  x:[2,3,3.1,3,4],xc:[0,.5,.55,.5,1],values:[0,-1,-.4,0,0],
  airfoil:{x:[2,3,3.1,3,4],ordinate:[0,.1,0,0,0]}};
const style={color:'#123456',dash:'dot',mode:'lines+markers',symbol:'circle'};
"""
        result = subprocess.run([node, '-e', helpers + script + checks], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_element_separation_repeated_x_hover_and_shared_source_style(self):
        self.run_javascript(r"""
const before=JSON.stringify(point);
const {traces,airfoils}=distributionCpTraces(point,'xmin',style,'Polar A','source-a');
assert.equal(traces.length,5);assert.equal(airfoils.length,2);
assert.equal(traces.filter(t=>t.showlegend).length,1);
for(const t of [...traces,...airfoils]) {
  assert.deepEqual(t.line,{color:'#123456',dash:'dot'});
  assert.equal(t.legendgroup,'source-a');assert.equal(t.name,'Polar A');
  assert.equal(t.mode,'lines');
}
assert.deepEqual(traces[2].x,[.55,.5,.5,.55]);
assert.deepEqual(traces[2].y,[-.4,-.2,.1,.3]);
assert.match(traces[2].hovertemplate,/Element 1<br>trailing edge \/ cove/);
assert.match(traces[3].hovertemplate,/Element 2<br>upper/);
assert.match(airfoils[1].hovertemplate,/Element 2<br>x\/c/);
assert.deepEqual(airfoils.map(t=>t.x.length),[8,5]);
assert.equal(airfoils.every(t=>t.showlegend===false && t.yaxis==='y2'),true);
assert.equal(JSON.stringify(point),before);
""")

    def test_common_chord_coordinates_keep_element_overlap_and_geometry_scale(self):
        self.run_javascript(r"""
const normal=distributionCpTraces(point,'xmin',style,'P','P');
assert.deepEqual(normal.traces[3].x,[.5,.75,1]);
assert.deepEqual(normal.airfoils[1].x,[1,.75,.5,.75,1]);
assert.deepEqual(normal.airfoils[1].y,[0,.03,0,-.03,0]);
const reverse=distributionCpTraces(point,'xmax',style,'P','P');
assert.deepEqual(reverse.traces[3].x,[.5,.25,0]);
assert.deepEqual(reverse.airfoils[1].x,[0,.25,.5,.25,0]);
assert.deepEqual(reverse.airfoils[1].y,normal.airfoils[1].y);
const raw=distributionCpTraces(point,'raw',style,'P','P');
assert.deepEqual(raw.traces[3].x,[3,3.5,4]);
assert.deepEqual(raw.airfoils[1].x,flap.airfoil.x);
assert.deepEqual(raw.airfoils[1].y,flap.airfoil.ordinate);
assert.match(raw.traces[3].hovertemplate,/X \[m\]/);
""")

    def test_legacy_station_and_html_in_element_labels(self):
        self.run_javascript(r"""
const legacy={...point};delete legacy.elements;
const unsplit=distributionCpTraces(legacy,'xmin',style,'P','P');
assert.equal(unsplit.traces.length,1);assert.equal(unsplit.airfoils.length,1);
assert.match(unsplit.traces[0].hovertemplate,/^Unclassified<br>/);
legacy.surfaces=flap.surfaces;
const split=distributionCpTraces(legacy,'raw',style,'P','P');
assert.equal(split.traces.length,2);assert.equal(split.traces[0].showlegend,true);
assert.equal(split.traces[1].showlegend,false);
point.elements[1].name='<flap & tail>';
assert.match(distributionCpTraces(point,'xmin',style,'P','P').traces[3].hovertemplate,
  /^&lt;flap &amp; tail&gt;<br>upper/);
""")


if __name__ == '__main__':
    unittest.main()
