/* Target-condition interpolation is independent of the dashboard and Plotly.
 * CL means the whole-configuration Stability-axis CLS from the matched ADF row.
 * Cp surface branches must already be identified by the distribution parser.
 */
function distributionAtTarget(seriesList, mode, target) {
  const stationTolerance = 1e-6, numericTolerance = 1e-9;
  const fail = error => ({series:null,error});
  const finite = Number.isFinite;
  const close = (a,b,absolute=numericTolerance,relative=1e-8) =>
    finite(a) && finite(b) && Math.abs(a-b) <= absolute+relative*Math.max(Math.abs(a),Math.abs(b));
  const copy = value => Array.isArray(value) ? value.map(copy)
    : value && typeof value==='object' ? Object.fromEntries(Object.entries(value).map(([key,item])=>[key,copy(item)])) : value;
  const label = s => `state ${s.state} (ALPHA=${s.alpha}°)`;
  const blend = (a,b,t) => finite(a) && finite(b) ? a+(b-a)*t : null;
  const diagnostics = [];
  if (mode !== 'alpha' && mode !== 'cl') return fail('Select ALPHA or CL for the target condition.');
  if (!finite(target)) return fail(`Enter a finite ${mode === 'cl' ? 'CL' : 'ALPHA'} target.`);
  if (!Array.isArray(seriesList) || !seriesList.length) return fail('No distribution states are available for this selection.');
  if (seriesList.some(s => !s || !finite(s.alpha))) return fail('Every distribution state needs a finite infout ALPHA.');
  const states = [...seriesList].sort((a,b) => a.alpha-b.alpha);
  const first = states[0];
  // Explicit legacy Cp values are already nondimensional; a consistently
  // absent reference pressure is valid only for that declared input format.
  const legacyWithoutPressure=states.every(s=>s.input_kind==='cp' && (s.p===null || s.p===undefined));
  for (const s of states) {
    if (['configuration','polar','component'].some(k => s[k] !== first[k])) {
      return fail('Target interpolation requires one configuration, POLAR and component at a time.');
    }
    if (!finite(s.beta) || !close(s.beta,first.beta)) return fail('Target interpolation requires constant BETA across the ALPHA sweep.');
    for (const key of ['mach','reynolds','qdin','p']) {
      if(key==='p' && legacyWithoutPressure) continue;
      if (!finite(s[key]) || !close(s[key],first[key],numericTolerance,1e-6)) {
        return fail(`Target interpolation requires known, constant ${key === 'qdin' ? 'dynamic pressure qdin' : key === 'p' ? 'reference pressure p' : key.toUpperCase()} across the ALPHA sweep.`);
      }
    }
    if (s.qdin <= 0) return fail('Target interpolation requires positive dynamic pressure qdin.');
  }
  for (let i=1;i<states.length;i++) if (close(states[i-1].alpha,states[i].alpha)) {
    return fail(`Duplicate ALPHA=${states[i].alpha}° in ${label(states[i-1])} and ${label(states[i])}; the sweep is ambiguous.`);
  }

  let alpha = target;
  if (mode === 'cl') {
    const invalid = states.find(s => !finite(s.cl_global));
    if (invalid) return fail(`CL target unavailable: ${label(invalid)} has no unique, finite ADF CLS at its ALPHA/BETA.`);
    const roots = [];
    const addRoot = value => {if (!roots.some(root => close(root,value))) roots.push(value);};
    states.forEach(s => {if(close(s.cl_global,target)) addRoot(s.alpha);});
    for(let i=1;i<states.length;i++) {
      const a=states[i-1], b=states[i];
      if(close(a.cl_global,b.cl_global)) {
        if(close(target,a.cl_global)) return fail(`CL=${target} is constant between ALPHA=${a.alpha}° and ${b.alpha}°; the target ALPHA is ambiguous.`);
        continue;
      }
      if(target > Math.min(a.cl_global,b.cl_global) && target < Math.max(a.cl_global,b.cl_global)) {
        addRoot(a.alpha+(b.alpha-a.alpha)*(target-a.cl_global)/(b.cl_global-a.cl_global));
      }
    }
    if(roots.length > 1) return fail(`CL=${target} has multiple ALPHA solutions (${roots.map(v=>Number(v.toPrecision(8))).join(', ')}°); the nonmonotonic/stall branch is ambiguous. Choose ALPHA instead.`);
    if(!roots.length) return fail(`CL=${target} is outside the available CL sweep; extrapolation is disabled.`);
    alpha=roots[0];
  }
  const exact = states.find(s => close(s.alpha,alpha));
  let left=exact, right=exact;
  if(!exact) {
    if(alpha < states[0].alpha || alpha > states[states.length-1].alpha) {
      return fail(`ALPHA=${alpha}° is outside the available sweep (${states[0].alpha}° to ${states[states.length-1].alpha}°); extrapolation is disabled.`);
    }
    const rightIndex=states.findIndex(s=>s.alpha>alpha);
    if(rightIndex <= 0) return fail('The target has no pair of bounding ALPHA states.');
    left=states[rightIndex-1];right=states[rightIndex];
  }
  if(!Array.isArray(left.cp) || !left.cp.length || !Array.isArray(right.cp) || !right.cp.length) {
    return fail(`Cp station data is missing at ${!left.cp?.length ? label(left) : label(right)}; the target distribution cannot be reconstructed.`);
  }
  const weight=exact ? 0 : (alpha-left.alpha)/(right.alpha-left.alpha);
  const sourceStates=exact ? [left.state] : [left.state,right.state];
  const provenance={mode,target,alpha,weight,source_states:sourceStates,
    source_alphas:exact ? [left.alpha] : [left.alpha,right.alpha],
    cl_definition:'ADF CLS (Stability axes)'};
  if(exact) {
    const result=copy(exact);
    result.interpolated=false;result.source_states=sourceStates;result.interpolation=provenance;
    result.cp.forEach(p=>{
      const classified=Array.isArray(p.elements) && p.elements.length
        ? p.elements.every(element=>element.surfaces?.upper && element.surfaces?.lower)
        : p.surfaces?.upper && p.surfaces?.lower;
      if(!classified) {
        diagnostics.push(`Recorded Cp at Y=${p.y} m has no identified upper/lower surfaces; the original curve is shown without surface classification.`);
      }
    });
    if((result.span||[]).some(p=>!finite(p.cl)||!finite(p.lift))) {
      diagnostics.push('Some recorded sectional loads are unavailable; the original Cp and load availability are preserved.');
    }
    if(diagnostics.length) result.interpolation.diagnostics=diagnostics;
    return {series:result,error:null,diagnostics};
  }

  function matchStations(a,b,kind) {
    if(!Array.isArray(a) || !Array.isArray(b)) throw new Error(`${kind} station data is missing in a bounding state.`);
    if(a.length !== b.length) throw new Error(`${kind} station sets differ between ${label(left)} and ${label(right)} (${a.length} versus ${b.length}); missing stations cannot be interpolated.`);
    if(a.some(p=>!finite(p.y)) || b.some(p=>!finite(p.y))) throw new Error(`${kind} station coordinates must be finite.`);
    const paired=[],used=new Set();
    for(const p of [...a].sort((p,q)=>p.y-q.y)) {
      const matches=b.map((q,i)=>({q,i})).filter(({q})=>Math.abs(p.y-q.y)<=stationTolerance);
      if(matches.length !== 1 || used.has(matches[0].i) || a.filter(q=>Math.abs(p.y-q.y)<=stationTolerance).length !== 1) {
        throw new Error(`${kind} station Y=${p.y} m has no unique match within ${stationTolerance} m between bounding states.`);
      }
      used.add(matches[0].i);paired.push([p,matches[0].q]);
    }
    return paired;
  }
  function sameGeometry(a,b,kind) {
    for(const k of ['xmin','xmax','chord']) if(!close(a[k],b[k],stationTolerance) || (k==='chord' && a[k]<=0)) {
      throw new Error(`${kind} station Y=${a.y} m changes ${k} between bounding states; changing section geometry cannot be interpolated.`);
    }
    if(!close(a.xmax-a.xmin,a.chord,stationTolerance) || !close(b.xmax-b.xmin,b.chord,stationTolerance)) {
      throw new Error(`${kind} station Y=${a.y} m has inconsistent chord geometry.`);
    }
    if(kind==='Cp') {
      if(Boolean(a.airfoil)!==Boolean(b.airfoil)) throw new Error(`Section outline is missing at Y=${a.y} m in one bounding state.`);
      if(a.airfoil) for(const k of ['x','ordinate']) {
        const aa=a.airfoil[k],bb=b.airfoil[k];
        if(!Array.isArray(aa) || !Array.isArray(bb) || aa.length!==bb.length || aa.some((v,i)=>!close(v,bb[i],stationTolerance))) {
          throw new Error(`Section outline changes at Y=${a.y} m; changing section geometry cannot be interpolated.`);
        }
      }
    }
  }
  function curve(surface,station,side) {
    if(!surface || !Array.isArray(surface.xc) || !Array.isArray(surface.values) || surface.xc.length!==surface.values.length || surface.xc.length<2) {
      throw new Error(`Cp station Y=${station.y} m needs an identified ${side} surface in both bounding states.`);
    }
    const points=surface.xc.map((x,i)=>({x,y:surface.values[i]}));
    if(points.some(p=>!finite(p.x)||!finite(p.y))) throw new Error(`Cp station Y=${station.y} m contains invalid ${side} surface values.`);
    points.sort((a,b)=>a.x-b.x);
    const unique=[];
    for(const p of points) {
      const previous=unique[unique.length-1];
      if(previous && close(p.x,previous.x)) {
        if(!close(p.y,previous.y)) throw new Error(`Cp station Y=${station.y} m has different ${side} Cp values at the same x/c; a single surface cannot be interpolated.`);
      } else unique.push(p);
    }
    if(unique.length<2) throw new Error(`Cp station Y=${station.y} m needs two distinct ${side} x/c samples.`);
    return unique;
  }
  function sample(points,x) {
    // Find the first sample at/above x, including the first tolerance-close
    // sample below it. Preserve the original exact-match preference without
    // scanning a dense pressure grid for every target coordinate.
    let low=0,high=points.length;
    while(low<high) {
      const middle=Math.floor((low+high)/2),point=points[middle];
      if(point.x<x && !close(point.x,x)) low=middle+1;
      else high=middle;
    }
    const i=low;
    if(i<points.length && close(points[i].x,x)) return points[i].y;
    if(i<=0 || i>=points.length) throw new Error('Cp interpolation attempted to leave the common surface domain.');
    return blend(points[i-1].y,points[i].y,(x-points[i-1].x)/(points[i].x-points[i-1].x));
  }
  function surfaceAtTarget(a,b,side) {
    const aa=curve(a.surfaces?.[side],a,side),bb=curve(b.surfaces?.[side],b,side);
    const low=Math.max(aa[0].x,bb[0].x),high=Math.min(aa[aa.length-1].x,bb[bb.length-1].x);
    if(high-low<=numericTolerance) throw new Error(`Cp station Y=${a.y} m has no overlapping ${side} x/c interval.`);
    if(!close(aa[0].x,bb[0].x) || !close(aa[aa.length-1].x,bb[bb.length-1].x)) {
      diagnostics.push(`Cp station Y=${a.y} m ${side} surface uses the common x/c interval ${Number(low.toPrecision(6))}–${Number(high.toPrecision(6))}; no extrapolation.`);
    }
    const candidates=[low,high,...aa.map(p=>p.x),...bb.map(p=>p.x)].filter(x=>x>=low&&x<=high).sort((x,y)=>x-y);
    const xc=candidates.filter((x,i)=>i===0||!close(x,candidates[i-1]));
    return {x:xc.map(x=>a.xmin+x*a.chord),xc,values:xc.map(x=>blend(sample(aa,x),sample(bb,x),weight))};
  }
  function blendForces(result,a,b) {
    for(const key of ['fx','fy','fz','normal_force','axial_force']) {
      if(key in a || key in b) result[key]=blend(a[key],b[key],weight);
    }
    return result;
  }
  function orderedCurveAtTarget(a,b,station,description) {
    // New parser records retain the matched section-file point order. X is not
    // a unique coordinate on a cove or vertical segment, so never sort/deduplicate.
    if(!a || !b || !Array.isArray(a.values) || !Array.isArray(b.values) ||
       !a.values.length || a.values.length!==b.values.length ||
       a.values.some(v=>!finite(v)) || b.values.some(v=>!finite(v))) {
      throw new Error(`Cp station Y=${station.y} m has invalid or unmatched ${description} pressure samples.`);
    }
    for(const key of ['x','xc']) {
      if(!Array.isArray(a[key]) || !Array.isArray(b[key]) ||
         a[key].length!==a.values.length || b[key].length!==b.values.length ||
         a[key].some((v,i)=>!close(v,b[key][i],key==='x' ? stationTolerance : numericTolerance))) {
        throw new Error(`Cp station Y=${station.y} m changes the ordered ${description} ${key} samples between bounding states.`);
      }
    }
    for(const curve of [a,b]) if(curve.x.some((x,i)=>!close(x,station.xmin+curve.xc[i]*station.chord,stationTolerance))) {
      throw new Error(`Cp station Y=${station.y} m has inconsistent ${description} x/c coordinates.`);
    }
    return {...copy(a),values:a.values.map((value,i)=>blend(value,b.values[i],weight))};
  }
  function elementsAtTarget(a,b) {
    if(!Array.isArray(a.elements) || !Array.isArray(b.elements) || !a.elements.length || a.elements.length!==b.elements.length) {
      throw new Error(`Cp station Y=${a.y} m changes or is missing its element set between bounding states.`);
    }
    const ids=new Set();
    const elements=a.elements.map((element,index)=>{
      const other=b.elements[index],description=`element ${index+1}`;
      if(!element || !other || typeof element.id!=='string' || !element.id || ids.has(element.id) || element.id!==other.id) {
        throw new Error(`Cp station Y=${a.y} m changes or duplicates its ordered element identities between bounding states.`);
      }
      ids.add(element.id);
      const result=orderedCurveAtTarget(element,other,a,description);
      for(const key of ['x','ordinate']) {
        const aa=element.airfoil?.[key],bb=other.airfoil?.[key];
        if(!Array.isArray(aa) || !Array.isArray(bb) || aa.length!==element.values.length || bb.length!==other.values.length ||
           aa.some((value,i)=>!close(value,bb[i],stationTolerance)) ||
           (key==='x' && aa.some((value,i)=>!close(value,element.x[i],stationTolerance)))) {
          throw new Error(`Cp station Y=${a.y} m changes or is missing the ordered ${description} section outline.`);
        }
      }
      const sides=Object.keys(element.surfaces||{}).sort(),otherSides=Object.keys(other.surfaces||{}).sort();
      if(!sides.includes('upper') || !sides.includes('lower') || sides.length!==otherSides.length || sides.some((side,i)=>side!==otherSides[i])) {
        throw new Error(`Cp station Y=${a.y} m changes or is missing the ${description} upper/lower surface branches.`);
      }
      result.surfaces=Object.fromEntries(sides.map(side=>[side,orderedCurveAtTarget(element.surfaces[side],other.surfaces[side],a,`${description} ${side} surface`)]));
      return blendForces(result,element,other);
    });
    const result=orderedCurveAtTarget(a,b,a,'section');
    result.elements=elements;
    // A top-level surface pair remains available to older single-element users.
    if(elements.length===1) result.surfaces=copy(elements[0].surfaces);
    else delete result.surfaces;
    return blendForces(result,a,b);
  }
  try {
    if(!close(left.bref,right.bref,stationTolerance)) throw new Error('BREF is missing or changes between the bounding states.');
    const cpPairs=matchStations(left.cp,right.cp,'Cp');
    const cp=cpPairs.map(([a,b])=>{
      sameGeometry(a,b,'Cp');
      if('elements' in a || 'elements' in b) return elementsAtTarget(a,b);
      const upper=surfaceAtTarget(a,b,'upper'),lower=surfaceAtTarget(a,b,'lower');
      // Keep legacy arrays connected in contour order; plots should use surfaces
      // directly so upper/lower hover labels cannot change the curve styling.
      const result={...copy(a),surfaces:{upper,lower}};
      for(const k of ['x','xc','values']) result[k]=[...upper[k]].reverse().concat(lower[k]);
      return blendForces(result,a,b);
    });
    const spanPairs=matchStations(left.span||[],right.span||[],'Load');
    if(spanPairs.length) {
      matchStations(left.span,left.cp,'Load/Cp');matchStations(right.span,right.cp,'Load/Cp');
    } else diagnostics.push('No spanwise load stations are available for the bounding states.');
    const span=spanPairs.map(([a,b])=>{
      sameGeometry(a,b,'Load');
      const result=blendForces(copy(a),a,b);
      // Pressure/forces interpolate linearly at fixed geometry. Lift must use
      // the requested ALPHA, not an average of differently rotated endpoint loads.
      const angle=alpha*Math.PI/180;
      const liftAvailable=Math.abs(left.beta)<=numericTolerance &&
        [a.cl,a.lift,b.cl,b.lift,result.fx,result.fz].every(finite);
      result.lift=liftAvailable ? result.fx*Math.sin(angle)-result.fz*Math.cos(angle) : null;
      result.cl=finite(result.lift) ? result.lift/(left.qdin*result.chord) : null;
      if(!finite(result.cl)||!finite(result.lift)) diagnostics.push(Math.abs(left.beta)>numericTolerance
        ? `Loads at Y=${a.y} m are unavailable for nonzero BETA without three-dimensional section geometry.`
        : `Loads at Y=${a.y} m are unavailable in one or both bounding states.`);
      return result;
    });
    const result={...copy(left),state:`${mode}=${target}`,case:null,alpha,cp,span,
      cl_global:mode==='cl' ? target : blend(left.cl_global,right.cl_global,weight),
      interpolated:true,source_states:sourceStates,interpolation:provenance};
    if(diagnostics.length) result.interpolation.diagnostics=diagnostics;
    return {series:result,error:null,diagnostics};
  } catch(error) {return fail(error.message);}
}

if(typeof module !== 'undefined' && module.exports) module.exports={distributionAtTarget};
