// Presentation layer: scientific transformations and interpolation stay in the engine.
const panelTypography = mixedTypographyLayout;
mixedTypographyLayout = function(layout) {
  const out = panelTypography(layout);
  Object.keys(out).filter(key => /^[xy]axis\d*$/.test(key)).forEach(key => {
    const axis = {...out[key]};
    if (axis.title) {
      const title = typeof axis.title === 'string' ? {text:axis.title} : {...axis.title};
      if (!String(title.text || '').startsWith('<b>')) {
        title.text = `<b>${title.text || ''}</b>`;
        title.font = {...title.font, size:Number(title.font?.size || 14)*1.1};
      }
      axis.title = title;
    }
    out[key] = axis;
  });
  return out;
};

function panelConditions(curves) {
  return conditionText(curves).split(' · ').reverse().join(' · ');
}
function panelGrid(rootId, specifications) {
  const root=document.getElementById(rootId);
  root.querySelectorAll('.plot').forEach(plot=>Plotly.purge(plot));
  root.replaceChildren();
  specifications.forEach(spec=>{
    const card=document.createElement('div');card.className='card';
    const heading=document.createElement('h3');heading.textContent=spec.label;card.append(heading);
    const plot=document.createElement('div');plot.id=spec.id;plot.className='plot';card.append(plot);root.append(card);
  });
}
function setupAnalysisPanels() {
  const convergence=document.getElementById('section-convergence');
  const old=convergence.querySelector('.analysis-plot-grid');
  old.innerHTML='<div class="card"><label for="convergenceAbscissa">Plot against:</label> <select id="convergenceAbscissa"><option>ALPHA</option><option>BETA</option></select><select id="residualEquationSelect" hidden><option value="ALL">All</option></select></div><div id="residualGrid" class="coefficient-row"></div><div class="coefficient-row"><div class="card"><div id="cpmaxPlot" class="plot"></div></div></div>';
  old.classList.remove('analysis-plot-grid');
  const axis=document.getElementById('convergenceAbscissa');
  axis.value=adfData.curves.length&&adfData.curves.every(c=>c.sweep_var==='BETA')?'BETA':'ALPHA';
  axis.onchange=()=>{drawResidualEquationsPlot(getFilteredRows());drawCpmaxPlot(getFilteredRows());saveLastState();};
  document.getElementById('comparisonMetricButtons').hidden=true;
  document.getElementById('comparisonPlot').outerHTML='<div class="workspace-context" id="deltaConditions"></div><div class="coefficient-row" id="deltaForces"></div><div class="workspace-context" id="deltaMomentReference"></div><div class="coefficient-row" id="deltaMoments"></div><details id="deltaExtras" class="workspace-details"><summary>Additional plots · ΔL/D and ΔLongitudinal static margin</summary><div class="coefficient-row" id="deltaAdditional"></div></details>';
  panelGrid('deltaForces',['CL','CD','CY'].map(c=>({id:'delta'+c+'Plot',label:'Δ'+c})));
  panelGrid('deltaMoments',['CM','CR','CN'].map(c=>({id:'delta'+c+'Plot',label:'Δ'+c})));
  panelGrid('deltaAdditional',['LD','SM'].map(c=>({id:'delta'+c+'Plot',label:c==='LD'?'ΔL/D':'ΔStatic margin'})));
  document.getElementById('deltaExtras').ontoggle=()=>{
    if(document.getElementById('deltaExtras').open) ['LD','SM'].forEach(c=>Plotly.Plots.resize('delta'+c+'Plot'));
  };
  document.getElementById('dragRisePlots').className='coefficient-row';
  const dragConditions=document.createElement('div');dragConditions.id='dragConditions';dragConditions.className='workspace-context';
  document.getElementById('dragRisePlots').before(dragConditions);
  const sm=document.createElement('div');sm.id='staticConditions';sm.className='workspace-context';
  document.querySelector('#section-static-margin .analysis-plot-grid').before(sm);
  document.getElementById('staticMarginMode').onchange=()=>{drawSmPlots();saveLastState();};
}

function availableResiduals(data) {
  const all=[...new Set(data.flatMap(r=>r.residual_columns||residualCols))];
  return [...residualCols.filter(c=>all.includes(c)),...all.filter(c=>!residualCols.includes(c))];
}
drawResidualEquationsPlot = function(data) {
  const equations=availableResiduals(data), xKey=document.getElementById('convergenceAbscissa').value.toLowerCase();
  const specs=(equations.length?equations:residualCols).map((eq,i)=>({id:'residualEquationPlot_'+i,label:eq}));
  const root=document.getElementById('residualGrid');
  if(root.dataset.equations!==JSON.stringify(specs)) {panelGrid('residualGrid',specs);root.dataset.equations=JSON.stringify(specs);}
  const groups=groupedByLabelPolar(data);
  specs.forEach(spec=>{
    const traces=Object.entries(groups).map(([name,rows])=>{
      const g=rows.filter(r=>Number.isFinite(r[xKey])).slice().sort((a,b)=>a[xKey]-b[xKey]);
      const st=traceStyle(rows[0].case_label,rows[0].polar);
      return {x:g.map(r=>r[xKey]),y:g.map(r=>r[spec.label+'_final']),mode:st.mode,name,connectgaps:false,
        line:{color:st.color,dash:st.dash},marker:{color:st.color,symbol:st.symbol},
        hovertemplate:`${xKey.toUpperCase()}: %{x:.3f}<br>${spec.label}: %{y:.3e}<extra>%{fullData.name}</extra>`};
    });
    Plotly.newPlot(spec.id,traces,{xaxis:{title:xKey.toUpperCase()+' [deg]'},yaxis:{...sciAxis(spec.label),dtick:1},
      legend:{orientation:'h',y:-.25},margin:{l:70,r:15,t:15,b:100}},{responsive:true});
  });
};
drawCpmaxPlot = function(data) {
  const xKey=document.getElementById('convergenceAbscissa').value.toLowerCase(),traces=[];
  Object.entries(groupedByLabelPolar(data)).forEach(([name,rows])=>{
    const g=rows.filter(r=>Number.isFinite(r[xKey])).slice().sort((a,b)=>a[xKey]-b[xKey]);
    const st=traceStyle(rows[0].case_label,rows[0].polar);
    [['cpmax_final','cp-max','y'],['tstep_ave_final','tstep-ave','y2']].forEach(([key,label,yaxis])=>traces.push({
      x:g.map(r=>r[xKey]),y:g.map(r=>r[key]),yaxis,name:name+' · '+label,mode:'lines+markers',
      line:{color:st.color,dash:yaxis==='y2'?'dash':st.dash},connectgaps:false}));
  });
  Plotly.newPlot('cpmaxPlot',traces,{title:'cp-max and average time step',xaxis:{title:xKey.toUpperCase()+' [deg]'},
    yaxis:{title:'cp-max'},yaxis2:{title:'tstep-ave',overlaying:'y',side:'right'},legend:{orientation:'h',y:-.25},
    margin:{l:65,r:65,t:45,b:110}},{responsive:true});
};
const previousSelectedHistory=drawSelectedHistory;
drawSelectedHistory=function(){
  previousSelectedHistory();
  const key=document.getElementById('caseHistoryFilter').value;
  const hist=historyData[key]||[];
  if(!hist.length)return;
  const row=convRows.find(r=>r.case_key===key),eqs=row?.residual_columns||residualCols;
  Plotly.newPlot('selectedResidualHistory',eqs.map(eq=>({x:hist.map(r=>r.iter),y:hist.map(r=>r[eq]==null?null:Math.abs(r[eq])),mode:'lines',name:eq})),
    {title:'Residual history',xaxis:{title:'Iteration'},yaxis:sciAxis('Residual'),margin:{l:70,r:25,t:50,b:95},legend:{orientation:'h',y:-.2}},{responsive:true});
};

drawComparisonPlot = function() {
  const pairs=getComparisonPairs(),smMap={};
  currentStaticMarginRows().forEach(r=>{const k=`${r.case_label}|${r.polar}`;(smMap[k]??=[]).push(r);});
  const all=[];
  ['CL','CD','CY','CM','CR','CN','LD','SM'].forEach(metric=>{
    const traces=[];let xTitle=document.getElementById('deltaAbscissa').value,yTitle='Δ'+metric;
    pairs.forEach((pair,i)=>{
      const transform=c=>!c||currentMomentReferenceMode()==='original'?c:{...c,rows:c.rows.map(r=>shiftedRow(r,summaryFor(c.case_label,c.polar)?.meta))};
      const ref=transform(curveFromKey(pair.reference)),cmp=transform(curveFromKey(pair.comparison));
      if(!ref||!cmp)return;
      if(metric==='CL')all.push(ref,cmp);
      const result=selectedComparisonSeries(ref,cmp,metric,smMap,document.getElementById('deltaAxis').value,document.getElementById('deltaAbscissa').value);
      xTitle=result.xAxisTitle;yTitle=result.yLabel;
      traces.push({x:result.xs,y:result.ys,mode:'lines+markers',name:`${cmp.curve_label} − ${ref.curve_label}`,
        line:{color:CONFIG_COLORS[i%CONFIG_COLORS.length],dash:POLAR_DASHES[i%POLAR_DASHES.length]}});
    });
    Plotly.newPlot('delta'+metric+'Plot',traces,{xaxis:{title:xTitle},yaxis:{title:yTitle,zeroline:true},
      annotations:traces.some(t=>t.x.length)?[]:[{text:'No overlapping comparison data',xref:'paper',yref:'paper',x:.5,y:.5,showarrow:false}],
      legend:{orientation:'h',y:-.25},margin:{l:70,r:20,t:15,b:110}},{responsive:true});
  });
  const uniqueCurves=[...new Map(all.map(c=>[`${c.case_label}|${c.polar}`,c])).values()];
  document.getElementById('deltaConditions').textContent=[panelConditions(uniqueCurves),fixedAngleText(uniqueCurves)].filter(Boolean).join(' · ');
  document.getElementById('deltaMomentReference').textContent=referenceTitle();
};

drawDragRisePlots=function(){
  const curves=filteredDragRiseCurves(),axis=document.getElementById('dragRiseAxis').value,groups=new Map();
  curves.forEach(c=>{const key=Number.isFinite(c.cls_value)?c.cls_value:c.file_name;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(c);});
  const keys=[...groups.keys()].sort((a,b)=>typeof a==='number'&&typeof b==='number'?a-b:String(a).localeCompare(String(b)));
  const specs=keys.map((key,i)=>({id:'dragRisePlot_'+i,label:`Target CL = ${key}`}));
  panelGrid('dragRisePlots',specs);
  document.getElementById('dragConditions').textContent=panelConditions(curves);
  document.getElementById('dragRiseHeading').textContent=`Drag rise: ΔCD${axis} vs Mach`;
  document.getElementById('dragRiseNote').textContent='Groups use the source filename CL target. Each configuration is referenced to its own lowest-Mach drag; these increments can include effects other than wave drag.';
  if(!keys.length)document.getElementById('dragRiseNote').textContent='No drag-rise files selected or available.';
  specs.forEach((spec,i)=>{
    const group=groups.get(keys[i]),traces=group.map((c,j)=>{
      const rows=c.rows.slice().sort((a,b)=>a.MACH-b.MACH);
      return {x:rows.map(r=>r.MACH),y:dragRiseValues(rows,axis),connectgaps:false,mode:'lines+markers',
        name:`${c.case_label} · ${c.drag_rise_dir}`,line:{color:CONFIG_COLORS[j%CONFIG_COLORS.length]},
        hovertemplate:`Mach: %{x:.4f}<br>ΔCD${axis}: %{y:.6f}<extra>%{fullData.name}</extra>`};
    });
    const heading=document.getElementById(spec.id).parentElement.querySelector('h3');
    heading.textContent=`Target CL = ${keys[i]} · ${dragRiseLiftLabel(group,axis)}`;
    Plotly.newPlot(spec.id,traces,{xaxis:{title:'Mach'},yaxis:{title:'ΔCD'+axis},legend:{orientation:'h',y:-.25},margin:{l:70,r:20,t:15,b:110}},{responsive:true});
  });
};
// CNS is already normalized by SREF*BREF and CYS by SREF. The negative derivative
// is a span fraction; multiply by 100 only (no second BREF division).
function directionalStaticMargin(curves) {
  const rows=[], skipped=[];
  curves.forEach(c=>{
    const skip=reason=>skipped.push(`${c.curve_label}: ${reason}`);
    if(c.sweep_var!=='BETA') {skip('requires a beta sweep');return;}
    const source=c.rows||[], alpha=source.map(r=>r.ALPHA);
    if(!alpha.length||!alpha.every(Number.isFinite)||Math.max(...alpha)-Math.min(...alpha)>1e-8) {
      skip('requires constant alpha');return;
    }
    const valid=source.filter(r=>['CYS','CNS25','BETA'].every(k=>Number.isFinite(r[k]))).slice().sort((a,b)=>a.CYS-b.CYS);
    const buckets=[];
    valid.forEach(r=>{
      let bucket=buckets[buckets.length-1];
      if(!bucket||Math.abs(bucket[0].CYS-r.CYS)>=1e-12) buckets.push(bucket=[]);
      bucket.push(r);
    });
    const reduced=buckets.map(bucket=>{
      const r={...bucket[0]};
      ['CYS','CNS25','BETA'].forEach(k=>r[k]=bucket.reduce((sum,p)=>sum+p[k],0)/bucket.length);
      return r;
    });
    if(reduced.length<3) {skip('requires at least three distinct finite CY values');return;}
    const derivative=derivativeNonuniform(reduced.map(r=>r.CYS),reduced.map(r=>r.CNS25));
    reduced.forEach((r,i)=>{
      if(!Number.isFinite(derivative[i]))return;
      rows.push({...r,case_label:c.case_label,polar:c.polar,curve_label:c.curve_label,sweep_var:c.sweep_var,
        DIRECTIONAL_STATIC_MARGIN:-derivative[i],DIRECTIONAL_STATIC_MARGIN_PERCENT:-100*derivative[i]});
    });
  });
  return {rows,skipped};
}
drawSmPlots=function(){
  const directional=document.getElementById('staticMarginMode').value==='directional';
  const curves=currentAdfCurves(), result=directional?directionalStaticMargin(curves):null;
  const rows=directional?result.rows:filteredSmRows().filter(r=>r.sweep_var==='ALPHA');
  const coefficient=directional?'CYS':'CLS', sweep=directional?'BETA':'ALPHA';
  const key=directional?'DIRECTIONAL_STATIC_MARGIN_PERCENT':'STATIC_MARGIN_PERCENT';
  const name=directional?'Directional':'Longitudinal', unit=directional?'BREF':'CREF';
  const shown=new Set(rows.map(r=>`${r.case_label}|${r.polar}`));
  const shownCurves=curves.filter(c=>shown.has(`${c.case_label}|${c.polar}`));
  document.getElementById('staticConditions').textContent=[panelConditions(shownCurves),fixedAngleText(shownCurves),referenceTitle()].filter(Boolean).join(' · ');
  document.getElementById('staticMarginDefinition').textContent=directional
    ? 'Directional: −100 × dCNS/dCYS [% BREF], from beta sweeps at constant alpha in Stability axes. The negative derivative defines the margin.'
    : 'Longitudinal: −100 × dCMS/dCLS [% CREF], from alpha sweeps in Stability axes.';
  document.getElementById('staticMarginStatus').textContent=directional?result.skipped.join(' · '):'';
  const groups=new Map();rows.forEach(r=>{const k=`${r.case_label}|${r.polar}`;if(!groups.has(k))groups.set(k,[]);groups.get(k).push(r);});
  [['smClPlot','smClHeading',coefficient],['smSweepPlot','smSweepHeading',sweep]].forEach(([id,heading,xKey])=>{
    const traces=[...groups.values()].map(g=>{
      const sorted=g.slice().sort((a,b)=>a[xKey]-b[xKey]), first=g[0],st=traceStyle(first.case_label,first.polar);
      return {x:sorted.map(r=>r[xKey]),y:sorted.map(r=>r[key]),mode:st.mode,name:first.curve_label.replace('POLAR-','P'),
        line:{color:st.color,dash:st.dash},marker:{color:st.color,symbol:st.symbol,size:st.markerSize},
        customdata:sorted.map(r=>({case_label:r.case_label,polar:r.polar,alpha:r.ALPHA,beta:r.BETA})),
        hovertemplate:`${xKey}: %{x:.5f}<br>SM: %{y:.3f}% ${unit}<extra>%{fullData.name}</extra>`};
    });
    document.getElementById(heading).textContent=`${name} static margin vs ${xKey}`;
    const yaxis={title:`${name} static margin [% ${unit}]`};
    if(!directional&&staticMarginYlim!==null&&!filterStaticMargin)yaxis.range=staticMarginYlim;
    Plotly.newPlot(id,traces,{xaxis:{title:xKey+(xKey===sweep?' [deg]':'')},yaxis,showlegend:true,
      margin:{l:75,r:25,t:15,b:105},legend:{orientation:'h',y:-.25},
      shapes:[{type:'line',xref:'paper',x0:0,x1:1,y0:0,y1:0,line:{dash:'dash'}}],
      annotations:traces.length?[]:[{text:`No valid ${sweep.toLowerCase()} sweep available`,xref:'paper',yref:'paper',x:.5,y:.5,showarrow:false}]},{responsive:true});
    bindPlotInteractions(id);
  });
};
populateExportPlots=function(){
  const select=document.getElementById('exportPlotSelect'),old=select.value;
  const plots=Array.from(document.querySelectorAll('.dashboard-section .plot[id]')).filter(p=>!p.closest('#distCpGrid')&&!p.closest('[hidden]'));
  select.replaceChildren(...plots.map(p=>{const option=document.createElement('option');option.value=p.id;option.textContent=p.id;return option;}));
  if(plots.some(p=>p.id===old))select.value=old;
};
const refreshBeforePanels=refreshAll;
refreshAll=function(){refreshBeforePanels();populateExportPlots();};
const stateBeforePanels=collectState,applyBeforePanels=applyState;
collectState=function(){return {...stateBeforePanels(),convergenceAbscissa:document.getElementById('convergenceAbscissa').value,staticMarginMode:document.getElementById('staticMarginMode').value};};
applyState=function(s){
  if(['ALPHA','BETA'].includes(s?.convergenceAbscissa))document.getElementById('convergenceAbscissa').value=s.convergenceAbscissa;
  document.getElementById('staticMarginMode').value=s?.staticMarginMode==='directional'?'directional':'longitudinal';
  return applyBeforePanels(s);
};
setupAnalysisPanels();
