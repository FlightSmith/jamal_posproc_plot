"""Launcher command-line defaults and actual browser setup persistence."""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest
from unittest.mock import Mock, patch

import jamal_dashboard_launcher_v25 as launcher


class LauncherStartupTests(unittest.TestCase):
    def test_no_arguments_use_launching_directory_without_inspecting_data(self):
        cwd = Path.cwd() / 'CFD project with spaces'
        with patch.object(Path, 'stat', side_effect=AssertionError('No data scan at argument parsing')):
            configs = launcher.parse_startup_configurations([], cwd)
        self.assertEqual(configs, [{'label': 'Baseline', 'base_directory': str(cwd)}])

    def test_named_pairs_and_single_path_keep_spaces_and_resolve_relative_paths(self):
        cwd = Path.cwd()
        configs = launcher.parse_startup_configurations(['baseline', 'first base', 'config_2', '../second base'], cwd)
        self.assertEqual(configs, [
            {'label': 'baseline', 'base_directory': os.path.abspath(cwd / 'first base')},
            {'label': 'config_2', 'base_directory': os.path.abspath(cwd / '../second base')}])
        self.assertEqual(launcher.parse_startup_configurations(['first base'], cwd),
                         [{'label': 'Baseline', 'base_directory': str(cwd / 'first base')}])
        self.assertEqual(launcher.parse_startup_configurations(['~/CFD'])[0]['base_directory'],
                         str(Path.home() / 'CFD'))

    def test_invalid_pairs_labels_and_configuration_limit(self):
        cases = [(['one', '/one', 'two'], 'LABEL PATH pairs'),
                 (['Base', '/one', 'base', '/two'], 'Duplicate configuration label'),
                 (['', '/one'], 'non-empty'), (['bad|label', '/one'], "cannot contain"),
                 (['base', '  '], 'base directory is empty'),
                 ([word for n in range(6) for word in (f'Config_{n}', f'/base{n}')], 'maximum of 5')]
        for arguments, message in cases:
            with self.subTest(arguments=arguments), self.assertRaisesRegex(ValueError, message):
                launcher.parse_startup_configurations(arguments)

    def test_main_accepts_options_and_pairs_without_tk_or_data_scanning(self):
        server = Mock()
        with patch.dict(launcher.STATE), patch('sys.argv', ['launcher.py', 'baseline', 'first base', '--no-browser',
                                                          '--host', '0.0.0.0', '--port', '9000', 'second', 'second base']), \
                patch.object(launcher, 'find_free_port', return_value=9000) as port, \
                patch.object(launcher, 'ThreadingHTTPServer', return_value=server) as server_type, \
                patch.object(launcher, 'choose_directory', side_effect=AssertionError('Tk must not be needed')), \
                patch.object(launcher, 'scan_base_directory', side_effect=AssertionError('No startup data scan')), \
                patch.object(launcher.webbrowser, 'open') as browser, contextlib.redirect_stdout(io.StringIO()):
            old_token = launcher.STATE['startup_token']
            launcher.main()
            port.assert_called_once_with('0.0.0.0', 9000)
            server_type.assert_called_once_with(('0.0.0.0', 9000), launcher.JamalRequestHandler)
            server.serve_forever.assert_called_once()
            server.server_close.assert_called_once()
            browser.assert_not_called()
            self.assertNotEqual(launcher.STATE['startup_token'], old_token)
            self.assertEqual([cfg['label'] for cfg in launcher.STATE['startup_setup']['configurations']], ['baseline', 'second'])

    def test_state_and_scan_endpoints_expose_startup_and_forward_drag_choice(self):
        handler = launcher.JamalRequestHandler.__new__(launcher.JamalRequestHandler)
        handler._json = Mock()
        handler.path = '/api/state'
        setup = {'configurations': [{'label': 'Wing', 'base_directory': '/CFD wing'}]}
        with patch.dict(launcher.STATE, startup_token='process-1', startup_setup=setup, jobs={}):
            handler.do_GET()
        response = handler._json.call_args.args[0]
        self.assertEqual(response['startup_setup'], setup)
        self.assertEqual(response['startup_token'], 'process-1')
        handler.path = '/api/scan'
        handler._read_json = lambda: {'base_directory': '/CFD wing', 'load_drag_rise': False}
        with patch.object(launcher, 'scan_base_directory', return_value={}) as scan:
            handler.do_POST()
        scan.assert_called_once_with('/CFD wing', load_drag_rise=False)

    def run_javascript(self, checks):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is required for launcher JavaScript checks')
        script = re.search(r'<script>([\s\S]*?)</script>', launcher.INDEX_HTML).group(1)
        script = script.replace("window.addEventListener('beforeunload',persistDraft);", '')
        script = script.rsplit('initializeLauncher();', 1)[0]
        harness = r'''
const assert=require('node:assert/strict');
const elements=new Map();
const document={
  getElementById(id){
    if(!elements.has(id)){
      const element={value:'',textContent:'',checked:true,style:{},options:[]};
      let html='';
      Object.defineProperty(element,'innerHTML',{get:()=>html,set:value=>{
        html=value;
        if(id.startsWith('polars-')) elements.set(`selected-${id.slice(7)}`,[...value.matchAll(/<input[^>]+>/g)]
          .filter(match=>/\schecked(?:\s|>)/.test(match[0])).map(match=>Number(match[0].match(/value="(\d+)"/)[1])));
        if(id.startsWith('drag-')) element.options=[...value.matchAll(/<option value="([^"]+)">/g)].map(match=>({value:match[1],selected:false}));
      }});
      Object.defineProperty(element,'selectedOptions',{get:()=>element.options.filter(option=>option.selected)});
      elements.set(id,element);
    }
    return elements.get(id);
  },
  querySelectorAll(selector){const id=selector.match(/polar-check-(\d+)/)?.[1];return (elements.get(`selected-${id}`)||[1]).map(value=>({value:String(value)}));}
};
const storage=new Map();
const localStorage={setItem:(key,value)=>storage.set(key,value),getItem:key=>storage.get(key)};
const alert=message=>{throw new Error(message);};
'''
        # DOM rendering alone is stubbed. Setup selection, storage, flags, state
        # fetching, scan requests, and generation payload use real app functions.
        render_stub = r'''
addConfiguration=async function(data={}){
  const id=nextId++;
  configs.set(id,{scan:null,dragScanned:false,dragSelections:data.drag_rise_dirs||[]});
  document.getElementById(`label-${id}`).value=data.label||'Baseline';
  document.getElementById(`path-${id}`).value=data.base_directory||'';
  document.getElementById(`dist-input-${id}`).value=data.distribution_input||'pressure';
  elements.set(`selected-${id}`,data.polars||[1]);
  updateLoadingControls();
  persistDraft();
};
'''
        result = subprocess.run([node, '-e', harness + script + render_stub + checks], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_browser_startup_overrides_old_draft_and_refresh_retains_edits(self):
        self.run_javascript(r'''
(async()=>{
  const startup={configurations:[{label:'CLI baseline',base_directory:'/data/CFD one',polars:[1,2]}]};
  let state={startup_token:'server-new',startup_setup:startup};
  global.fetch=async()=>({ok:true,json:async()=>state});
  storage.set('JAMAL_v25_source_setup',JSON.stringify({startup_token:'old-server',configurations:[{label:'Stale',base_directory:'/old'}]}));
  await initializeLauncher();
  assert.equal(serializeSetup().configurations[0].label,'CLI baseline');
  assert.equal(serializeSetup().configurations[0].base_directory,'/data/CFD one');
  assert.equal(restoreDraft().startup_token,'server-new');
  document.getElementById('label-1').value='Edited label';
  document.getElementById('loadConvergence').checked=false;
  persistDraft();
  await initializeLauncher();
  assert.equal(serializeSetup().configurations[0].label,'Edited label');
  assert.equal(serializeSetup().load_convergence,false);
  state={...state,startup_token:'another-new-server'};
  await initializeLauncher();
  assert.equal(serializeSetup().configurations[0].label,'CLI baseline');
  assert.equal(serializeSetup().load_convergence,true);
})().catch(error=>{console.error(error);process.exitCode=1;});
''')

    def test_browser_flags_setup_roundtrip_defaults_and_generation_request(self):
        self.assertNotIn('id="outputDirectory"', launcher.INDEX_HTML)
        self.assertNotIn('browseOutputDirectory', launcher.INDEX_HTML)
        self.run_javascript(r'''
(async()=>{
  startupToken='test-server';
  await applySetup({output_directory:'/obsolete/output',load_distributions:false,load_convergence:false,load_drag_rise:false,
    configurations:[{label:'Wing',base_directory:'/CFD inputs',polars:[1,2],drag_rise_dirs:['Case one'],distribution_input:'cp'}]});
  const saved=serializeSetup();
  assert.equal(saved.load_distributions,false);
  assert.equal(saved.load_convergence,false);
  assert.equal(saved.load_drag_rise,false);
  assert.equal('output_directory' in saved,false);
  assert.deepEqual(saved.configurations[0].drag_rise_dirs,['Case one']);
  assert.equal(document.getElementById('dist-input-1').disabled,true);
  assert.equal(document.getElementById('drag-1').disabled,true);
  assert.equal(restoreDraft().load_drag_rise,false);
  assert.match(document.getElementById('outputPaths').textContent,/CFD inputs\/03-RESULTS\/DASHBOARD/);
  const requests=[];
  global.fetch=async(url,options)=>{requests.push([url,JSON.parse(options.body)]);return {ok:true,json:async()=>({job_id:'job-1'})};};
  pollGenerationJob=async()=>{};
  await generateDashboard();
  assert.equal(requests[0][0],'/api/generate');
  for(const key of ['load_distributions','load_convergence','load_drag_rise']) assert.equal(requests[0][1][key],false);
  await applySetup({configurations:saved.configurations});
  assert.equal(serializeSetup().load_distributions,true);
  assert.equal(serializeSetup().load_convergence,true);
  assert.equal(serializeSetup().load_drag_rise,true);
  await applySetup(saved);
  assert.equal(serializeSetup().load_drag_rise,false);
  assert.deepEqual(serializeSetup().configurations[0].drag_rise_dirs,['Case one']);
})().catch(error=>{console.error(error);process.exitCode=1;});
''')

    def test_browser_skip_drag_scan_and_reload_folders_when_enabled(self):
        self.run_javascript(r'''
(async()=>{
  startupToken='test-server';
  await applySetup({load_drag_rise:false,configurations:[{label:'Wing',base_directory:'/CFD',polars:[1,2],drag_rise_dirs:['Saved case']}]});
  const requests=[];
  global.fetch=async(url,options)=>{
    const body=JSON.parse(options.body);requests.push([url,body]);
    return {ok:true,json:async()=>({base_directory:'/CFD',adf_directory:'/CFD/03-RESULTS/ADF',runs_directory:'/CFD/02-RUNS',
      drag_rise_root:'/CFD/03-RESULTS/DRAG-RISE',polars:[{name:'POLAR-001',number:1},{name:'POLAR-002',number:2}],drag_rise_directories:body.load_drag_rise?['Saved case']:[]})};
  };
  await scanDirectory(1,[1,2],selectedDrag(1));
  assert.equal(requests[0][1].load_drag_rise,false);
  assert.deepEqual(serializeSetup().configurations[0].drag_rise_dirs,['Saved case']);
  assert.equal(document.getElementById('drag-1').disabled,true);
  document.getElementById('loadDragRise').checked=true;
  await loadingOptionsChanged();
  assert.equal(requests.length,2);
  assert.equal(requests[1][1].load_drag_rise,true);
  assert.equal(configs.get(1).dragScanned,true);
  assert.equal(document.getElementById('drag-1').disabled,false);
  assert.deepEqual(serializeSetup().configurations[0].drag_rise_dirs,['Saved case']);
})().catch(error=>{console.error(error);process.exitCode=1;});
''')

    def test_browser_enabling_drag_during_initial_scan_keeps_saved_choices(self):
        self.run_javascript(r'''
(async()=>{
  startupToken='test-server';
  await applySetup({load_drag_rise:false,configurations:[{label:'Wing',base_directory:'/CFD',polars:[2],drag_rise_dirs:['Saved case']}]});
  const requests=[];
  global.fetch=(url,options)=>new Promise(resolve=>requests.push({body:JSON.parse(options.body),resolve}));
  const reply=(index,polars,folders)=>requests[index].resolve({ok:true,json:async()=>({base_directory:'/CFD',
    adf_directory:'/CFD/03-RESULTS/ADF',runs_directory:'/CFD/02-RUNS',drag_rise_root:'/CFD/03-RESULTS/DRAG-RISE',
    polars:polars.map(number=>({number,name:`POLAR-${number}`})),drag_rise_directories:folders})});
  const initial=scanDirectory(1,[2],['Saved case']);
  assert.equal(requests.length,1);
  assert.equal(configs.get(1).scan,null);
  document.getElementById('loadDragRise').checked=true;
  const enabled=loadingOptionsChanged();
  assert.equal(requests.length,2);
  assert.equal(requests[1].body.load_drag_rise,true);
  assert.deepEqual(restoreDraft().configurations[0].polars,[2]);
  reply(1,[1,2],['Saved case','Other case']);
  await enabled;
  assert.deepEqual(selectedPolars(1),[2]);
  assert.deepEqual(selectedDrag(1),['Saved case']);
  assert.equal(configs.get(1).dragScanned,true);
  const currentStatus=document.getElementById('status').textContent;
  reply(0,[1],[]);
  await initial;
  assert.deepEqual(configs.get(1).scan.polars.map(p=>p.number),[1,2]);
  assert.equal(configs.get(1).dragScanned,true);
  assert.deepEqual(selectedPolars(1),[2]);
  assert.deepEqual(selectedDrag(1),['Saved case']);
  assert.equal(document.getElementById('status').textContent,currentStatus);
  assert.equal(configs.get(1).pendingScan,null);
})().catch(error=>{console.error(error);process.exitCode=1;});
''')

    def test_browser_repeated_toggles_ignore_out_of_order_results_and_errors(self):
        self.run_javascript(r'''
(async()=>{
  startupToken='test-server';
  await applySetup({configurations:[{label:'Wing',base_directory:'/CFD',drag_rise_dirs:['Saved case']}]});
  const requests=[];
  global.fetch=(url,options)=>new Promise(resolve=>requests.push({body:JSON.parse(options.body),resolve}));
  const initial=scanDirectory(1,null,['Saved case']);
  document.getElementById('loadDragRise').checked=false;
  const disabled=loadingOptionsChanged();
  document.getElementById('loadDragRise').checked=true;
  const enabled=loadingOptionsChanged();
  assert.deepEqual(requests.map(request=>request.body.load_drag_rise),[true,false,true]);
  const newest=configs.get(1).pendingScan;
  requests[0].resolve({ok:false,json:async()=>({error:'Obsolete failure'})});
  await initial;
  assert.equal(configs.get(1).pendingScan,newest);
  assert.doesNotMatch(document.getElementById('status').textContent,/Obsolete failure/);
  requests[2].resolve({ok:true,json:async()=>({base_directory:'/CFD',adf_directory:'/CFD/03-RESULTS/ADF',
    runs_directory:'/CFD/02-RUNS',drag_rise_root:'/CFD/03-RESULTS/DRAG-RISE',
    polars:[1,2,3].map(number=>({number,name:`POLAR-${number}`})),drag_rise_directories:['Saved case']})});
  await enabled;
  assert.deepEqual(selectedPolars(1),[1,2,3]);
  assert.deepEqual(selectedDrag(1),['Saved case']);
  requests[1].resolve({ok:true,json:async()=>({base_directory:'/CFD',adf_directory:'/CFD/03-RESULTS/ADF',
    runs_directory:'/CFD/02-RUNS',drag_rise_root:'/CFD/03-RESULTS/DRAG-RISE',polars:[{number:1,name:'POLAR-1'}],drag_rise_directories:[]})});
  await disabled;
  assert.equal(configs.get(1).dragScanned,true);
  assert.deepEqual(selectedPolars(1),[1,2,3]);
  assert.deepEqual(selectedDrag(1),['Saved case']);
  assert.equal(configs.get(1).pendingScan,null);
})().catch(error=>{console.error(error);process.exitCode=1;});
''')


if __name__ == '__main__':
    unittest.main()
