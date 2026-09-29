"""Generation diagnostics and local output separation from CFD input folders."""
import contextlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

import jamal_dashboard_launcher_v25 as launcher
from test_baseline import make_fixture


class GenerationPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='jamal_output_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.base = self.root / 'CFD inputs'
        self.payload = make_fixture(self.base)
        self.default_output = self.base / '03-RESULTS' / 'DASHBOARD'
        self.local_output = self.root / 'Local reports'

    def test_default_output_is_preserved_for_existing_setups(self):
        for field in ({}, {'output_directory': ''}, {'output_directory': '  '}):
            normalized = launcher._normalize_configurations({**self.payload, **field})
            self.assertEqual(launcher.output_directory(normalized), self.default_output)
            self.assertEqual(launcher.output_report_path(normalized), self.default_output / 'dashboard.html')

    def test_explicit_output_is_absolute_and_shared_by_configurations(self):
        payload = {**self.payload, 'output_directory': str(self.local_output)}
        payload['configurations'] = [self.payload['configurations'][0],
                                     {**self.payload['configurations'][0], 'label': 'Second'}]
        normalized = launcher._normalize_configurations(payload)
        self.assertEqual(launcher.output_directory(normalized), self.local_output)
        self.assertEqual([cfg['output_directory'] for cfg in normalized], [str(self.local_output)] * 2)
        with self.assertRaisesRegex(ValueError, 'absolute path'):
            launcher._normalize_configurations({**self.payload, 'output_directory': 'relative/reports'})

    def test_generation_writes_only_local_output_and_records_phase_timings(self):
        before = {path.relative_to(self.base): path.read_bytes()
                  for path in self.base.rglob('*') if path.is_file()}
        payload = {**self.payload, 'output_directory': str(self.local_output)}
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            launcher._run_generation_job('local-output-timings', payload)
        job = launcher.job_snapshot('local-output-timings')
        self.assertEqual(job['status'], 'complete', job.get('error'))
        result = job['result']
        self.assertEqual(Path(result['report_path']), self.local_output / 'dashboard.html')
        self.assertTrue(Path(result['json_path']).is_file())
        self.assertFalse(self.default_output.exists())
        self.assertEqual(before, {path.relative_to(self.base): path.read_bytes()
                                  for path in self.base.rglob('*') if path.is_file()})
        cache = self.local_output / '.jamal_cache'
        self.assertEqual(result['cache_directory'], str(cache))
        self.assertEqual(job['output_directory'], str(self.local_output))
        timings = result['timings_seconds']
        self.assertEqual(set(timings), {'scanning', 'polars', 'drag_rise', 'distributions',
                                       'derived', 'json', 'html', 'validation', 'publish'})
        self.assertTrue(all(value >= 0 for value in timings.values()))
        self.assertLessEqual(sum(timings.values()), result['elapsed_seconds'])
        self.assertEqual(job['timings_seconds'], timings)
        manifest = json.loads((cache / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['timings_seconds'], timings)
        self.assertEqual(manifest['cache_directory'], str(cache))
        self.assertIn('Timing · distributions:', job['log'])
        self.assertIn(str(cache), job['log'])

    def test_clear_cache_confined_to_selected_output(self):
        local_cache = self.local_output / '.jamal_cache'
        source_cache = self.default_output / '.jamal_cache'
        for directory in (local_cache, source_cache):
            directory.mkdir(parents=True)
            (directory / 'cache_entry').write_text('cache')
        report = self.local_output / 'dashboard.html'
        report.write_text('keep report')
        unrelated = self.local_output / 'other_data'
        unrelated.write_text('keep other data')
        result = launcher.clear_cache({**self.payload, 'output_directory': str(self.local_output)})
        self.assertEqual(result['cache_directory'], str(local_cache))
        self.assertFalse(local_cache.exists())
        self.assertEqual((source_cache / 'cache_entry').read_text(), 'cache')
        self.assertEqual(report.read_text(), 'keep report')
        self.assertEqual(unrelated.read_text(), 'keep other data')

    def test_launcher_setup_and_draft_round_trip_output_directory(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is required for launcher JavaScript checks')
        script = re.search(r'<script>([\s\S]*?)</script>', launcher.INDEX_HTML).group(1)
        # Evaluate the actual launcher functions without starting its page/network lifecycle.
        functions = script.split("window.addEventListener('beforeunload'", 1)[0]
        harness = r'''
const assert=require('assert');
const elements=new Map();
const document={
  getElementById(id){if(!elements.has(id)) elements.set(id,{value:'',textContent:'',innerHTML:''});return elements.get(id);},
  querySelectorAll(){return [{value:'1'}];}
};
const storage=new Map();
const localStorage={setItem:(key,value)=>storage.set(key,value),getItem:key=>storage.get(key)};
'''
        checks = r'''
// Rendering and folder scanning are external to the setup persistence contract.
addConfiguration=function(data){
  const id=nextId++;configs.set(id,{scan:null});
  document.getElementById(`label-${id}`).value=data.label||'Baseline';
  document.getElementById(`path-${id}`).value=data.base_directory||'';
  document.getElementById(`dist-input-${id}`).value=data.distribution_input||'pressure';
};
(async()=>{
  const output=String.raw`C:\Local Reports\Project`;
  const payload={output_directory:output,configurations:[{label:'Wing',base_directory:String.raw`Z:\CFD`,polars:[1]}]};
  await applySetup(payload);
  assert.equal(serializeSetup().output_directory,output);
  assert.equal(restoreDraft().output_directory,output);
  assert(document.getElementById('outputPaths').textContent.includes(output));
  document.getElementById('outputDirectory').value=String.raw`C:\Other output`;
  persistDraft();
  const saved=restoreDraft();
  document.getElementById('outputDirectory').value='discard this';
  await applySetup(saved);
  assert.equal(serializeSetup().output_directory,saved.output_directory);
  await applySetup({configurations:payload.configurations});
  assert.equal(serializeSetup().output_directory,'');
  assert.equal(restoreDraft().output_directory,'');
  assert(document.getElementById('outputPaths').textContent.includes('03-RESULTS/DASHBOARD'));
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
        result = subprocess.run([node, '-e', harness + functions + checks], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
