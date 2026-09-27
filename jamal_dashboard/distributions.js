/* Additive UI: existing aerodynamic calculations remain in the v25 engine. */
function distributionSpanReference(series) {
  const value = series.bref;
  return Number.isFinite(value) && value > 0 ? value : null;
}
function distributionCoordinate(series, y, mode) {
  const reference = distributionSpanReference(series);
  return mode === 'y' ? y : reference === null ? null : y / reference * (mode === 'eta' ? 2 : 1);
}
function distributionChordLoad(point) {
  return Number.isFinite(point.cl) && Number.isFinite(point.chord) && point.chord > 0 ? point.cl * point.chord : null;
}
function distributionCpRange(series, mode, minText, maxText) {
  let low=Infinity, high=-Infinity;
  series.forEach(s=>s.cp.forEach(p=>p.values.forEach(v=>{if(Number.isFinite(v)){low=Math.min(low,v);high=Math.max(high,v);}})));
  const padding=Number.isFinite(low)?Math.max(.05,(high-low)*.08):.05;
  const automatic=Number.isFinite(low)?[high+padding,low-padding]:[1,-1];
  if(mode!=='manual') return {range:automatic,error:''};
  const min=Number(minText),max=Number(maxText);
  if(String(minText).trim()==='' || String(maxText).trim()==='' || !Number.isFinite(min) || !Number.isFinite(max) || min>=max)
    return {range:automatic,error:'Enter finite limits with minimum < maximum. Automatic scale is shown.'};
  return {range:[max,min],error:''};
}
function distributionStation(series, station, mode='eta') {
  const value = distributionCoordinate(series, station.y, mode);
  const position = mode === 'y' ? `Y = ${station.y.toFixed(3)} m`
    : value === null ? `Y = ${station.y.toFixed(3)} m · BREF unavailable`
    : `${mode === 'eta' ? '2Y/BREF' : 'Y/BREF'} = ${value > 0 ? '+' : ''}${Number((100*value).toFixed(2))}%`;
  // eta and yb use the same selection identity; dimensional stations group by Y.
  const fraction = distributionCoordinate(series, station.y, 'yb');
  const dimensional = mode === 'y' || fraction === null;
  return {key:JSON.stringify([series.component, dimensional ? 'Y' : 'fraction',
    (dimensional ? station.y : fraction).toFixed(7)]), component:series.component,
    order:dimensional ? station.y : fraction, label:`${series.component} · ${position}`};
}
function distributionLoadsText(series, mode) {
  const field = value => value === null || value === undefined || (typeof value === 'number' && !Number.isFinite(value))
    ? 'NA' : String(value).replace(/[\t\r\n]/g,' ');
  const rows = ['# JAMAL spanwise loads; tab-separated; missing values = NA',
    '# Pressure-derived lift (no shear); normalization: infout BREF. cl.c = cl * local chord [m]. All stations of displayed series.',
    `# Selected coordinate: ${mode === 'eta' ? '2Y/BREF' : mode === 'yb' ? 'Y/BREF' : 'Y [m]'} (normalized coordinates are fractions)`,
    'configuration\tpolar\tcomponent\tstate\talpha_deg\tbeta_deg\tY_m\tBREF_m\tcoordinate\tchord_m\tcl\tcl.c_m'];
  series.filter(s=>s.interpolation).forEach(s=>rows.splice(rows.length-1,0,
    `# Target ${field(s.configuration)} / ${field(s.polar)} / ${field(s.component)}: ${JSON.stringify(s.interpolation)}`));
  series.forEach(s => s.span.forEach(p => rows.push([s.configuration,s.polar,s.component,s.state,s.alpha,s.beta,
    p.y,distributionSpanReference(s),distributionCoordinate(s,p.y,mode),p.chord,p.cl,distributionChordLoad(p)].map(field).join('\t'))));
  return rows.join('\r\n')+'\r\n';
}
(() => {
  const byId = id => document.getElementById(id);
  const data = distributionData.series || [];
  const overlays = new Set();
  let ready = false;
  const selectedStations = new Set();
  const storageKey = 'JAMAL_distributions_v3:' + JSON.stringify(distinctSources());
  const panels = new Map();
  let targetErrors = [];
  function distinctSources() {return [...new Set((distributionData.sources||[]).map(s => s.path.split(/DISTCLCP/i)[0]))].sort();}
  const key = s => JSON.stringify([s.configuration, s.polar, s.component, s.state]);
  const text = s => `${s.configuration} · ${s.polar} · ${s.component} · α=${Number(s.alpha?.toFixed(5))}° β=${s.beta}°`;
  const options = (id, values, label = x => x) => {
    const select = byId(id), old = select.value;
    select.replaceChildren(...values.map(value => new Option(label(value), String(value))));
    if (values.some(v => String(v) === old)) select.value = old;
  };
  const distinct = list => [...new Set(list)];
  const candidates = level => data.filter(s =>
    (level < 1 || s.configuration === byId('distConfig').value) &&
    (level < 2 || s.polar === byId('distPolar').value) &&
    (level < 3 || s.component === byId('distComponent').value));
  const selected = () => candidates(3).find(s => s.state === Number(byId('distState').value));
  const shown = () => {
    const chosen=data.filter(s => overlays.has(key(s)) || s === selected()), mode=byId('distTargetMode').value;
    targetErrors=[];
    if(mode==='state') return chosen;
    if(byId('distTargetValue').value.trim()==='') {targetErrors=['Enter a target value.'];return [];}
    const groupKey=s=>JSON.stringify([s.configuration,s.polar,s.component]);
    const groups=new Map(chosen.map(s=>[groupKey(s),s]));
    return [...groups].flatMap(([id,s])=>{
      const result=distributionAtTarget(data.filter(v=>groupKey(v)===id),mode,Number(byId('distTargetValue').value));
      if(result.error) targetErrors.push(`${s.configuration} · ${s.polar} · ${s.component}: ${result.error}`);
      (result.diagnostics||[]).forEach(message=>targetErrors.push(`${s.configuration} · ${s.polar}: ${message}`));
      return result.series?[result.series]:[];
    });
  };
  const station = (s,p) => distributionStation(s,p,byId('distCoordinate').value);
  const stationCatalog = () => {
    const entries = new Map();
    shown().forEach(s => s.cp.forEach(p => {const item=station(s,p);entries.set(item.key,item);}));
    return [...entries.values()].sort((a,b)=>a.component.localeCompare(b.component)||a.order-b.order);
  };
  function remember() {
    if(!ready) return;
    try {localStorage.setItem(storageKey,JSON.stringify({
      configuration:byId('distConfig').value,polar:byId('distPolar').value,component:byId('distComponent').value,
      state:byId('distState').value,coordinate:byId('distCoordinate').value,leadingEdge:byId('distLeadingEdge').value,
      overlays:[...overlays],stations:[...selectedStations],single:byId('distSingle').checked,
      targetMode:byId('distTargetMode').value,targetValue:byId('distTargetValue').value,
      cpScale:byId('distCpScale').value,cpMin:byId('distCpMin').value,cpMax:byId('distCpMax').value
    }));} catch (_) {}
  }
  function updateControls(level = 0) {
    if (level <= 0) options('distConfig', distinct(data.map(s => s.configuration)));
    if (level <= 1) options('distPolar', distinct(candidates(1).map(s => s.polar)));
    if (level <= 2) options('distComponent', distinct(candidates(2).map(s => s.component)));
    options('distState', candidates(3).map(s => s.state), state => {
      const s = candidates(3).find(s => s.state === state);
      return `α=${s.alpha}° · β=${s.beta}°`;
    });
    updateStations(true); draw();
  }
  function updateStations(autoSelect=false) {
    const catalog = stationCatalog();
    const selectedSource=selected();
    const current = byId('distTargetMode').value==='state'?selectedSource:shown().find(s=>selectedSource &&
      s.configuration===selectedSource.configuration && s.polar===selectedSource.polar && s.component===selectedSource.component);
    const currentKeys = current ? current.cp.map(p=>station(current,p).key) : [];
    if ((!ready && !selectedStations.size) || (autoSelect && !currentKeys.some(k=>selectedStations.has(k)))) {
      if(byId('distSingle').checked) selectedStations.clear();
      currentKeys.forEach((k,i)=>{if(!byId('distSingle').checked || i===0) selectedStations.add(k);});
    }
    byId('distStations').replaceChildren(...catalog.map(item => {
      const label = document.createElement('label'), checkbox = document.createElement('input');
      checkbox.type = 'checkbox'; checkbox.value = item.key; checkbox.checked = selectedStations.has(item.key);
      checkbox.addEventListener('change', () => {
        if (byId('distSingle').checked) selectedStations.clear();
        if (checkbox.checked) selectedStations.add(item.key); else selectedStations.delete(item.key);
        updateStations(); draw();
      });
      label.append(checkbox, document.createTextNode(` ${item.label}`));
      return label;
    }));
  }
  function draw() {
    if (!ready || !byId('section-distributions').classList.contains('active')) return;
    const series = shown(), mode = byId('distCoordinate').value, le = byId('distLeadingEdge').value;
    const span = [], chordSpan = [], groups = new Map();
    let missingBref = false;
    const angleText=value=>Number.isFinite(value)?String(Number(value.toFixed(4))):'unavailable';
    const safe = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    series.forEach((s, i) => {
      const style = traceStyle(s.configuration, s.polar);
      const name = safe(text(s)), shortName = safe(`${s.configuration} · ${s.polar.replace('POLAR-','P')} · ${s.component} · α=${angleText(s.alpha)}° β=${angleText(s.beta)}°`), bref = distributionSpanReference(s);
      const normalized = bref !== null;
      if (!normalized && mode !== 'y') missingBref = true;
      const x = y => mode === 'y' ? y : normalized ? y / bref * (mode === 'eta' ? 2 : 1) : null;
      span.push({x:s.span.map(p => x(p.y)), y:s.span.map(p => p.cl), mode:style.mode, name:shortName,
        line:{color:style.color,dash:style.dash},
        marker:{color:style.color,symbol:style.symbol,size:style.markerSize}, connectgaps:false,
        hovertemplate:`${name}<br>Span: %{x:.4f}<br>cl: %{y:.5f}<extra></extra>`});
      chordSpan.push({...span[span.length-1], y:s.span.map(distributionChordLoad),
        hovertemplate:`${name}<br>Span: %{x:.4f}<br>cl.c: %{y:.5f} m<extra></extra>`});
      s.cp.filter(p => selectedStations.has(station(s,p).key)).forEach(p => {
        const item = station(s,p);
        if(!groups.has(item.key)) groups.set(item.key,{...item,traces:[],airfoils:[]});
        const surfaces=p.surfaces?Object.entries(p.surfaces):[['Unclassified',p]];
        const legendName=safe(`${s.configuration} · ${s.polar.replace('POLAR-','P')} · α=${angleText(s.alpha)}° β=${angleText(s.beta)}°`), curveId=key(s);
        surfaces.forEach(([surface,branch],branchIndex)=>groups.get(item.key).traces.push({x:le === 'raw' ? branch.x : le === 'xmax' ? branch.xc.map(v => 1-v) : branch.xc,
          y:branch.values, mode:'lines', name:legendName,legendgroup:curveId,showlegend:branchIndex===0,
          line:{color:style.color,dash:style.dash},
          hoverlabel:{bgcolor:'rgba(0,0,0,0)',bordercolor:'rgba(0,0,0,0)',font:{color:style.color}},
          hovertemplate:`${surface}<br>${le === 'raw' ? 'X [m]' : 'x/c'}: %{x:.4f}<br>Cp: %{y:.5f}<extra></extra>`}));
        if(p.airfoil) {
          const group=groups.get(item.key), cpTrace=group.traces[group.traces.length-1];
          group.airfoils.push({x:p.airfoil.x.map(x=>le==='raw'?x:le==='xmax'?(p.xmax-x)/p.chord:(x-p.xmin)/p.chord),
            y:p.airfoil.ordinate.map(y=>le==='raw'?y:y/p.chord), yaxis:'y2',
            mode:'lines',name:cpTrace.name,line:{...cpTrace.line},showlegend:false,
            legendgroup:curveId,hoverlabel:cpTrace.hoverlabel,
            hovertemplate:`${le==='raw'?'X [m]':'x/c'}: %{x:.4f}<br>${le==='raw'?'y [m]':'y/c'}: %{y:.5f}<extra></extra>`});
        }

      });
    });
    const layout = (id,title,count) => {
      const columns = Math.max(1,Math.floor((byId(id).clientWidth-90)/280));
      const bottom = 90+Math.ceil(count/columns)*28;
      byId(id).style.height = `${360+bottom}px`;
      return {title,height:360+bottom,margin:{l:65,r:25,t:55,b:bottom},uirevision:'distributions',
        showlegend:true,legend:{orientation:'h',y:-.28,yanchor:'top',x:0,entrywidth:260}, font:{family:'Arial, Helvetica, sans-serif'}};
    };
    byId('distributionConditions').textContent=panelConditions(series.map(s=>({rows:[{MACH:s.mach,REYNOLDS:s.reynolds}]})));
    byId('cpConditions').textContent=byId('distributionConditions').textContent;
    ['distSpanPlot','distSpanChordPlot'].forEach(id=>installPlotActions(byId(id)));
    Plotly.react('distSpanPlot', span, mixedTypographyLayout({...layout('distSpanPlot','',span.length),
      xaxis:{title:mode==='eta'?'2Y/BREF':mode==='yb'?'Y/BREF':'Y [m]'},yaxis:{title:'cl'},uirevision:mode}), {responsive:true});
    Plotly.react('distSpanChordPlot', chordSpan, mixedTypographyLayout({...layout('distSpanChordPlot','',chordSpan.length),
      xaxis:{title:mode==='eta'?'2Y/BREF':mode==='yb'?'Y/BREF':'Y [m]'},yaxis:{title:'cl.c'},uirevision:mode}), {responsive:true});
    byId('distExport').disabled = !series.some(s=>s.span.length);
    // Reuse one Plotly surface per station; release removed panels and their listeners.
    for(const [key,panel] of panels) if(!groups.has(key)) {
      Plotly.purge(panel.plot);panel.card.remove();panels.delete(key);
    }
    const ordered = [...groups.values()].sort((a,b)=>a.component.localeCompare(b.component)||a.order-b.order);
    const curveCount=ordered.reduce((n,g)=>n+g.traces.filter(t=>t.showlegend!==false).length,0);
    const scale=distributionCpRange(series.map(s=>({...s,cp:s.cp.filter(p=>selectedStations.has(station(s,p).key))})),byId('distCpScale').value,byId('distCpMin').value,byId('distCpMax').value);
    const cpRange=scale.range;
    byId('distCpScaleStatus').textContent=scale.error;
    ordered.forEach(g=>{
      let panel=panels.get(g.key);
      if(!panel){
        const card=document.createElement('article'), heading=document.createElement('h4'), plot=document.createElement('div');
        card.className='dist-cp-panel';plot.className='plot';plot.id='distCpPlot_'+encodeURIComponent(g.key);card.append(heading,plot);
        panel={card,heading,plot};panels.set(g.key,panel);
      }
      panel.heading.textContent=g.label;
      byId('distCpGrid').append(panel.card);
      installPlotActions(panel.plot);
      panel.card.querySelector('.plot-actions button').setAttribute('aria-label','Expand '+g.label);
    });
    // Finalize every grid cell before Plotly measures any panel. Otherwise the
    // first airfoil's equal-scale constraint uses a temporary full-grid width.
    ordered.forEach(g=>{
      const panel=panels.get(g.key);
      const width=panel.plot.clientWidth, bottom=85+g.traces.filter(t=>t.showlegend!==false).length*22;
      let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
      g.airfoils.forEach(t=>{
        t.x.forEach(v=>{minX=Math.min(minX,v);maxX=Math.max(maxX,v);});
        t.y.forEach(v=>{minY=Math.min(minY,v);maxY=Math.max(maxY,v);});
      });
      // Give wide panels enough height for the airfoil at true proportions so
      // its aspect constraint never needs to expand the shared chord range.
      const chordRange=le==='raw'?maxX-minX:1;
      const foilHeight=g.airfoils.length?Math.max(66,Math.ceil((width-57)*(maxY-minY)/chordRange*1.25)):0;
      const plotHeight=g.airfoils.length?194+25+foilHeight:285;
      const height=plotHeight+15+bottom;
      panel.plot.style.height=`${height}px`;
      Plotly.react(panel.plot,[...g.traces,...g.airfoils],mixedTypographyLayout({width,height,margin:{l:45,r:12,t:15,b:bottom},
        xaxis:{title:le==='raw'?'X [m]':'x/c',range:le==='raw'?undefined:[0,1],autorange:le==='raw',anchor:g.airfoils.length?'y2':'y'},
        yaxis:{title:'Cp',range:cpRange,autorange:false,domain:g.airfoils.length?[(foilHeight+25)/plotHeight,1]:[0,1]},
        yaxis2:{title:le==='raw'?'y [m]':'y/c',domain:[0,g.airfoils.length?foilHeight/plotHeight:.23],anchor:'x',
          scaleanchor:'x',scaleratio:1,constrain:'range',autorange:true,nticks:3,zeroline:false},
        showlegend:true,legend:{orientation:'h',y:-.28,yanchor:'top',font:{size:10}},
        uirevision:JSON.stringify([le,g.key,cpRange,panel.plot.clientWidth])}),{responsive:true,displaylogo:false});
    });
    byId('distOverlays').textContent = overlays.size ? `Pinned overlays: ${data.filter(s => overlays.has(key(s))).map(text).join(' | ')}` : 'Current state shown. Add overlay to retain it while selecting another state or configuration.';
    if(byId('distTargetMode').value!=='state') byId('distOverlays').textContent=`Target comparison: ${series.map(text).join(' | ')}`;
    byId('distTargetStatus').textContent=[...series.filter(s=>s.interpolation).map(s=>
      `${s.configuration} · ${s.polar}: ${s.interpolated?'Interpolated from':'Recorded'} state${s.source_states.length>1?'s':''} ${s.source_states.join(' / ')}${s.interpolated?`, weight ${s.interpolation.weight.toFixed(4)}`:''}.`),...targetErrors].join(' | ');
    byId('distStatus').textContent = !data.length ? 'No distribution data found for the selected POLARs. Expected: 03-RESULTS/DISTCLCP/POLAR-XXX/<component>.' :
      `${series.length} state(s) · ${groups.size} station plot(s) · ${curveCount} Cp curve(s). ${missingBref ? 'Missing positive span reference: choose dimensional Y. ' : ''}${curveCount ? '' : 'Select a station to show Cp. '}${(distributionData.issues||[]).length} distribution integrity warning(s).`;
    const unavailableLoads=series.filter(s=>!s.span.some(p=>Number.isFinite(p.cl)));
    if(unavailableLoads.length) byId('distStatus').textContent+=` Loads unavailable: ${unavailableLoads.map(s=>`${s.polar} / ${s.component}`).join(', ')}. See distribution integrity for the reason.`;
    byId('distReference').textContent = (mode==='y' ? 'Station labels use dimensional Y [m]. ' :
      `Station percentage = ${mode==='eta'?'200':'100'} × Y / infout BREF. `)+
      distinct(series.map(s=>`${s.configuration} · ${s.polar}: BREF = ${distributionSpanReference(s) ?? 'unavailable'} m`)).join(' · ');
    remember();
  }
  function init() {
    updateControls();
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) || 'null');
      if(saved) {
        const restore = (id, value) => {if([...byId(id).options].some(o=>o.value===String(value))) byId(id).value=String(value);};
        restore('distConfig',saved.configuration); updateControls(1);
        restore('distPolar',saved.polar); updateControls(2);
        restore('distComponent',saved.component); updateControls(3);
        restore('distState',saved.state); restore('distCoordinate',saved.coordinate); restore('distLeadingEdge',saved.leadingEdge);
        (saved.overlays||[]).filter(k=>data.some(s=>key(s)===k)).forEach(k=>overlays.add(k));
        selectedStations.clear(); (saved.stations||[]).forEach(y=>selectedStations.add(y));
        byId('distSingle').checked=Boolean(saved.single);
        restore('distTargetMode',saved.targetMode); restore('distCpScale',saved.cpScale);
        [['distTargetValue',saved.targetValue],['distCpMin',saved.cpMin],['distCpMax',saved.cpMax]].forEach(([id,value])=>{if(value!==undefined)byId(id).value=value;});
      }
    } catch (_) {}
    ready = true; updateStations();
    function targetControls() {
      const enabled=byId('distTargetMode').value!=='state';
      byId('distTargetValue').disabled=!enabled;byId('distState').disabled=enabled;
    }
    function scaleControls() {['distCpMin','distCpMax'].forEach(id=>byId(id).disabled=byId('distCpScale').value!=='manual');}
    targetControls();scaleControls();
    ['distTargetMode','distTargetValue'].forEach(id=>byId(id).addEventListener('change',()=>{targetControls();updateStations(true);draw();}));
    ['distCpScale','distCpMin','distCpMax'].forEach(id=>byId(id).addEventListener('change',()=>{scaleControls();draw();}));
    let gridWidth = byId('distCpGrid').clientWidth, resizeFrame;
    const gridObserver = new ResizeObserver(entries => {
      const width = entries[0].contentRect.width;
      if (width <= 0 || Math.abs(width-gridWidth) < 1) return;
      gridWidth = width;
      cancelAnimationFrame(resizeFrame);
      resizeFrame = requestAnimationFrame(draw);
    });
    gridObserver.observe(byId('distCpGrid'));
    byId('distIntegrity').textContent = [
      ...(distributionData.issues||[]).map(i => `${i.configuration} · ${i.polar} · ${i.details}`),
      '\nSources (size and modification timestamp retained in dashboard.json):',
      ...(distributionData.sources||[]).map(s => s.path)
    ].join('\n');
    ['distConfig','distPolar','distComponent'].forEach((id,i) => byId(id).addEventListener('change', () => updateControls(i+1)));
    byId('distState').addEventListener('change', () => {updateStations(); draw();});
    let previousMode = byId('distCoordinate').value;
    byId('distCoordinate').addEventListener('change', () => {
      const mode = byId('distCoordinate').value, retained = new Set();
      shown().forEach(s=>s.cp.forEach(p=>{
        if(selectedStations.has(distributionStation(s,p,previousMode).key)) retained.add(distributionStation(s,p,mode).key);
      }));
      selectedStations.clear(); retained.forEach(k=>selectedStations.add(k));
      previousMode=mode; updateStations(); draw();
    });
    byId('distLeadingEdge').addEventListener('change', draw);
    byId('distExport').onclick = () => {
      const series=shown(), blob=new Blob([distributionLoadsText(series,byId('distCoordinate').value)],{type:'text/plain;charset=utf-8'});
      const url=URL.createObjectURL(blob), link=document.createElement('a');
      link.href=url;link.download='JAMAL_spanwise_loads.txt';document.body.append(link);link.click();link.remove();
      setTimeout(()=>URL.revokeObjectURL(url),10000);
      byId('distExportStatus').textContent=`Download requested: ${series.reduce((n,s)=>n+s.span.length,0)} stations from ${series.length} displayed series.`;
    };
    byId('distAdd').onclick = () => {if(selected()) overlays.add(key(selected())); updateStations(); draw();};
    byId('distClear').onclick = () => {overlays.clear(); updateStations(); draw();};
    function pick(n) {
      selectedStations.clear();
      [...byId('distStations').querySelectorAll('input')].forEach((el,i) => {
        if (n && i%n===0 && (!byId('distSingle').checked || !selectedStations.size)) selectedStations.add(el.value);
      });
      updateStations(); draw();
    }
    byId('distAll').onclick = () => pick(1);
    byId('distNone').onclick = () => pick(0);
    byId('distEvery').onclick = () => pick(Math.max(1, Math.floor(Number(byId('distNth').value)||1)));
    byId('distSingle').onchange = () => {if(byId('distSingle').checked && selectedStations.size>1) {
      const first = selectedStations.values().next().value; selectedStations.clear(); selectedStations.add(first); updateStations(); draw();
    }};
  }
  const originalShow = showSection;
  showSection = function(section, button) {
    originalShow(section, button);
    byId('analysisToolbar').style.display = section === 'distributions' ? 'none' : '';
    byId('advancedPanel').style.display = section === 'distributions' ? 'none' : '';
    if(section === 'distributions') {if(!ready) init(); draw();}
  };
})();
