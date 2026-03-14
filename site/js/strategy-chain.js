/* ═══════════════════════════════════════════════════════════════════════════════
 * strategy-chain.js — Chain builder UI logic + evaluator STUB
 *                     for the Strategy Designer page
 * ═══════════════════════════════════════════════════════════════════════════════ */

/* ═══════════════════════════════════════════════════════════════════════════════
 * Chain Builder UI Functions
 * ═══════════════════════════════════════════════════════════════════════════════ */

function renderChainBuilder() {
  const container = document.getElementById('step-list');
  if (!container) return;
  container.innerHTML = '';

  if (sApp.steps.length === 0) {
    // Empty state is handled by the "Add Step" button below
    return;
  }

  for (let i = 0; i < sApp.steps.length; i++) {
    const step = sApp.steps[i];
    const card = renderStepCard(step, i);
    container.appendChild(card);
  }
}

function addStep() {
  // Smart defaults: first available primitive with its defaults
  const firstPrim = S_PRIMITIVES[0];
  const newStep = {
    step: sApp.steps.length + 1,
    primitive: firstPrim.key,
    label: firstPrim.label,
    direction_match: 'same',
    constraints: { ...firstPrim.defaults },
    timing: sApp.steps.length === 0 ? { mode: 'chain_start' } : { mode: 'after_previous', window: 'same_kill_zone' },
    _advancedExpanded: false,
  };
  sApp.steps.push(newStep);
  renderChainBuilder();
  evaluateChain();
}

function removeStep(index) {
  sApp.steps.splice(index, 1);
  // Re-number steps
  sApp.steps.forEach((s, i) => { s.step = i + 1; });
  // Fix timing for first step if needed
  if (sApp.steps.length > 0 && sApp.steps[0].timing.mode !== 'chain_start') {
    sApp.steps[0].timing = { mode: 'chain_start' };
  }
  renderChainBuilder();
  evaluateChain();
}

function updateStepPrimitive(index, primitiveKey) {
  const prim = S_PRIMITIVES.find(p => p.key === primitiveKey);
  if (!prim) return;
  sApp.steps[index].primitive = primitiveKey;
  sApp.steps[index].label = prim.label;
  sApp.steps[index].constraints = { ...prim.defaults };
  renderChainBuilder();
  evaluateChain();
}

function updateStepTiming(index, timingWindow) {
  sApp.steps[index].timing = { mode: 'after_previous', window: timingWindow };
  evaluateChain();
}

function toggleStepAdvanced(index) {
  sApp.steps[index]._advancedExpanded = !sApp.steps[index]._advancedExpanded;
  renderChainBuilder();
}

function renderStepCard(step, index) {
  const card = document.createElement('div');
  card.className = 'step-card';

  // Header: step number, primitive dropdown, remove button
  const header = document.createElement('div');
  header.className = 'step-header';

  const stepNum = document.createElement('div');
  stepNum.className = 'step-number';
  stepNum.textContent = step.step.toString();

  const select = document.createElement('select');
  select.className = 'step-primitive-select';
  for (const p of S_PRIMITIVES) {
    const opt = document.createElement('option');
    opt.value = p.key;
    opt.textContent = p.label;
    if (p.key === step.primitive) opt.selected = true;
    select.appendChild(opt);
  }
  select.addEventListener('change', () => {
    updateStepPrimitive(index, select.value);
  });

  const removeBtn = document.createElement('button');
  removeBtn.className = 'step-remove-btn';
  removeBtn.textContent = '✕';
  removeBtn.addEventListener('click', () => {
    removeStep(index);
  });

  header.appendChild(stepNum);
  header.appendChild(select);
  header.appendChild(removeBtn);
  card.appendChild(header);

  // Smart defaults display
  const defaults = document.createElement('div');
  defaults.className = 'step-defaults';
  defaults.textContent = formatStepDefaults(step.constraints);
  card.appendChild(defaults);

  // Timing selector (not for first step)
  if (step.timing.mode !== 'chain_start') {
    const timingDiv = document.createElement('div');
    timingDiv.className = 'step-timing';

    const timingLabel = document.createElement('span');
    timingLabel.className = 'step-timing-label';
    timingLabel.textContent = 'Timing:';

    const timingSelect = document.createElement('select');
    timingSelect.className = 'step-timing-select';
    for (const opt of S_TIMING_OPTIONS) {
      const optEl = document.createElement('option');
      optEl.value = opt.value;
      optEl.textContent = opt.label;
      if (step.timing.window === opt.value) optEl.selected = true;
      timingSelect.appendChild(optEl);
    }
    timingSelect.addEventListener('change', () => {
      updateStepTiming(index, timingSelect.value);
    });

    timingDiv.appendChild(timingLabel);
    timingDiv.appendChild(timingSelect);
    card.appendChild(timingDiv);
  }

  // Advanced toggle
  const advToggle = document.createElement('button');
  advToggle.className = 'step-advanced-toggle';
  advToggle.textContent = step._advancedExpanded ? 'Advanced ▾' : 'Advanced ▸';
  advToggle.addEventListener('click', () => {
    toggleStepAdvanced(index);
  });
  card.appendChild(advToggle);

  // Advanced body (expandable)
  const advBody = document.createElement('div');
  advBody.className = 'step-advanced-body' + (step._advancedExpanded ? ' expanded' : '');
  advBody.innerHTML = '<em style="font-size:11px;color:var(--faint);">Advanced constraints coming in Phase 2</em>';
  card.appendChild(advBody);

  return card;
}

function formatStepDefaults(constraints) {
  if (!constraints || Object.keys(constraints).length === 0) {
    return 'No default constraints';
  }
  const parts = [];
  for (const [key, val] of Object.entries(constraints)) {
    if (Array.isArray(val)) {
      parts.push(`${key}: [${val.join(', ')}]`);
    } else if (typeof val === 'object') {
      parts.push(`${key}: ${JSON.stringify(val)}`);
    } else {
      parts.push(`${key}: ${val}`);
    }
  }
  return parts.join(', ');
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Gates Rendering
 * ═══════════════════════════════════════════════════════════════════════════════ */

function renderGates() {
  const container = document.getElementById('gates-container');
  if (!container) return;

  container.innerHTML = '';

  // Kill zone checkboxes
  const kzRow = document.createElement('div');
  kzRow.className = 'gate-row';

  const kzLabel = document.createElement('span');
  kzLabel.className = 'gate-label';
  kzLabel.textContent = 'Kill Zone:';

  const kzCheckboxes = document.createElement('div');
  kzCheckboxes.className = 'gate-checkboxes';

  const kzOptions = ['lokz', 'nyokz'];
  for (const opt of kzOptions) {
    const item = document.createElement('div');
    item.className = 'gate-checkbox-item';

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.id = `gate-kz-${opt}`;
    checkbox.checked = sApp.gates.kill_zone.includes(opt);
    checkbox.addEventListener('change', () => {
      if (checkbox.checked) {
        if (!sApp.gates.kill_zone.includes(opt)) {
          sApp.gates.kill_zone.push(opt);
        }
      } else {
        sApp.gates.kill_zone = sApp.gates.kill_zone.filter(x => x !== opt);
      }
      evaluateChain();
    });

    const label = document.createElement('label');
    label.htmlFor = `gate-kz-${opt}`;
    label.textContent = opt.toUpperCase();

    item.appendChild(checkbox);
    item.appendChild(label);
    kzCheckboxes.appendChild(item);
  }

  kzRow.appendChild(kzLabel);
  kzRow.appendChild(kzCheckboxes);
  container.appendChild(kzRow);

  // Asia range tier checkboxes
  const asiaRow = document.createElement('div');
  asiaRow.className = 'gate-row';

  const asiaLabel = document.createElement('span');
  asiaLabel.className = 'gate-label';
  asiaLabel.textContent = 'Asia Range:';

  const asiaCheckboxes = document.createElement('div');
  asiaCheckboxes.className = 'gate-checkboxes';

  const asiaOptions = ['tight', 'mid', 'wide'];
  for (const opt of asiaOptions) {
    const item = document.createElement('div');
    item.className = 'gate-checkbox-item';

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.id = `gate-asia-${opt}`;
    checkbox.checked = sApp.gates.asia_range_tier.includes(opt);
    checkbox.addEventListener('change', () => {
      if (checkbox.checked) {
        if (!sApp.gates.asia_range_tier.includes(opt)) {
          sApp.gates.asia_range_tier.push(opt);
        }
      } else {
        sApp.gates.asia_range_tier = sApp.gates.asia_range_tier.filter(x => x !== opt);
      }
      evaluateChain();
    });

    const label = document.createElement('label');
    label.htmlFor = `gate-asia-${opt}`;
    label.textContent = opt.charAt(0).toUpperCase() + opt.slice(1);

    item.appendChild(checkbox);
    item.appendChild(label);
    asiaCheckboxes.appendChild(item);
  }

  asiaRow.appendChild(asiaLabel);
  asiaRow.appendChild(asiaCheckboxes);
  container.appendChild(asiaRow);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Get Chain Definition (for evaluation or save)
 * ═══════════════════════════════════════════════════════════════════════════════ */

function getChainDefinition() {
  return {
    schema_version: '1.0',
    name: sApp.templateName || 'Untitled Strategy',
    direction: sApp.direction,
    description: '',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    steps: sApp.steps.map(s => ({
      step: s.step,
      primitive: s.primitive,
      label: s.label,
      direction_match: s.direction_match,
      constraints: s.constraints,
      timing: s.timing,
    })),
    gates: sApp.gates,
  };
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Chain Evaluator — Detection Index Builder
 * ═══════════════════════════════════════════════════════════════════════════════ */

function buildDetectionIndex(detectionData, tf) {
  // Pre-index all detections for fast lookup during chain evaluation.
  // Input: sApp.detectionData (enriched format), current TF
  // Output: Object structured as:
  //   index[forex_day][primitive_key] = sorted array of detection objects
  //
  // Also builds a kill_zone sub-index:
  //   kzIndex[forex_day][kill_zone][primitive_key] = sorted array
  //
  // Detections come from detectionData.detections_by_primitive[primName][tf]
  // or detectionData.detections_by_primitive[primName]['global'] for global primitives
  //
  // Each detection in the enriched format has:
  //   { id, time, direction, type, price, properties, tags, upstream_refs }
  //
  // IMPORTANT: properties.forex_day is the day key. tags.kill_zone is the kill zone.
  // tags.session is the session. Some primitives store kill_zone in properties.kill_zone.
  
  const index = {};
  const kzIndex = {};
  
  for (const [primName, byTf] of Object.entries(detectionData.detections_by_primitive)) {
    const dets = byTf[tf] || byTf['global'] || [];
    for (const det of dets) {
      const fd = det.properties?.forex_day || extractDayFromTime(det.time);
      if (!fd) continue;
      
      // Day-level index
      if (!index[fd]) index[fd] = {};
      if (!index[fd][primName]) index[fd][primName] = [];
      index[fd][primName].push(det);
      
      // Kill zone sub-index
      const kz = det.tags?.kill_zone || det.properties?.kill_zone || null;
      if (kz && kz !== 'NONE') {
        if (!kzIndex[fd]) kzIndex[fd] = {};
        if (!kzIndex[fd][kz]) kzIndex[fd][kz] = {};
        if (!kzIndex[fd][kz][primName]) kzIndex[fd][kz][primName] = [];
        kzIndex[fd][kz][primName].push(det);
      }
    }
  }
  
  return { index, kzIndex };
}

function extractDayFromTime(timeStr) {
  if (!timeStr) return null;
  return timeStr.substring(0, 10);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Chain Evaluator — Direction Matching
 * ═══════════════════════════════════════════════════════════════════════════════ */

function matchesDirection(det, stepDirectionMatch, strategyDirection) {
  // stepDirectionMatch is "same" or "opposing"
  // strategyDirection is "bullish" or "bearish"
  const targetDir = stepDirectionMatch === 'same' ? strategyDirection : 
    (strategyDirection === 'bullish' ? 'bearish' : 'bullish');
  
  // Map detection directions: "high" maps to "bullish", "low" maps to "bearish"
  const detDir = det.direction === 'high' ? 'bullish' : 
                 det.direction === 'low' ? 'bearish' : 
                 det.direction;
  
  // "neutral" detections match any direction (e.g., asia_range, session_liquidity)
  if (detDir === 'neutral') return true;
  
  return detDir === targetDir;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Chain Evaluator — Constraint Matching
 * ═══════════════════════════════════════════════════════════════════════════════ */

function matchesConstraints(det, constraints, chainContext) {
  // Check each constraint against detection properties.
  // Returns { passed: true/false, failReason: string|null }
  
  for (const [key, expected] of Object.entries(constraints)) {
    // Special spatial constraint: in_ote_zone
    if (key === 'in_ote_zone' && expected === true) {
      const oteZone = chainContext?.oteZone;
      if (!oteZone) return { passed: false, failReason: 'No OTE zone in chain context' };
      const detPrice = det.price;
      const zoneTop = det.properties?.top || det.properties?.zone_body?.top || detPrice;
      const zoneBottom = det.properties?.bottom || det.properties?.zone_body?.bottom || detPrice;
      // Check if detection zone overlaps with OTE zone
      const inZone = zoneBottom <= oteZone.high && zoneTop >= oteZone.low;
      if (!inZone) return { passed: false, failReason: `Price zone [${zoneBottom?.toFixed(5)}-${zoneTop?.toFixed(5)}] outside OTE [${oteZone.low?.toFixed(5)}-${oteZone.high?.toFixed(5)}]` };
      continue;
    }
    
    // qualified_sweep
    if (key === 'qualified_sweep') {
      const actual = det.properties?.qualified_sweep;
      if (expected && !actual) return { passed: false, failReason: 'Not a qualified sweep' };
      continue;
    }
    
    // break_type (MSS)
    if (key === 'break_type') {
      const actual = det.properties?.break_type;
      if (actual !== expected) return { passed: false, failReason: `break_type: ${actual} (expected ${expected})` };
      continue;
    }
    
    // displacement_grade_min (MSS)
    if (key === 'displacement_grade_min') {
      const gradeOrder = { 'WEAK': 1, 'VALID': 2, 'STRONG': 3 };
      const actual = det.properties?.displacement?.quality_grade || det.properties?.quality_grade;
      const actualRank = gradeOrder[actual] || 0;
      const expectedRank = gradeOrder[expected] || 0;
      if (actualRank < expectedRank) return { passed: false, failReason: `displacement grade: ${actual} (min ${expected})` };
      continue;
    }
    
    // quality_grade_min (Displacement)
    if (key === 'quality_grade_min') {
      const gradeOrder = { 'WEAK': 1, 'VALID': 2, 'STRONG': 3 };
      const actual = det.properties?.quality_grade;
      const actualRank = gradeOrder[actual] || 0;
      const expectedRank = gradeOrder[expected] || 0;
      if (actualRank < expectedRank) return { passed: false, failReason: `quality grade: ${actual} (min ${expected})` };
      continue;
    }
    
    // fib_range (OTE) — check if dealing range fib levels overlap
    if (key === 'fib_range' && Array.isArray(expected)) {
      // OTE detections carry fib_levels in properties
      // This step just checks the OTE zone exists — the actual fib range
      // is used for display/spatial constraint with other steps
      continue;
    }
    
    // state (FVG, OB)
    if (key === 'state') {
      // FVG: check ce_touched_bar, boundary_closed_bar
      // If ACTIVE is required, neither should be set
      if (expected === 'ACTIVE') {
        if (det.properties?.boundary_closed_bar != null) {
          return { passed: false, failReason: 'state: BOUNDARY_CLOSED (expected ACTIVE)' };
        }
      }
      continue;
    }
    
    // tier (Asia Range)
    if (key === 'tier' && Array.isArray(expected)) {
      const classifications = det.properties?.classifications;
      if (classifications) {
        // Check against the 20-pip threshold (locked value)
        const rangeClass = classifications['20'] || 'WIDE';
        const tier = rangeClass === 'TIGHT' ? 'tight' : rangeClass === 'WIDE' ? 'wide' : 'mid';
        // Also check range_pips directly
        const rangePips = det.properties?.range_pips;
        let detTier = 'wide';
        if (rangePips < 10) detTier = 'tight';
        else if (rangePips <= 20) detTier = 'mid';
        if (!expected.includes(detTier)) {
          return { passed: false, failReason: `Asia range: ${detTier} (${rangePips?.toFixed(1)} pips) — expected [${expected.join(', ')}]` };
        }
      }
      continue;
    }
    
    // classification (Session Liquidity)
    if (key === 'classification') {
      const detType = det.type;
      if (expected === 'CONSOLIDATION_BOX') {
        const eff = det.properties?.efficiency;
        if (eff != null && eff > 0.60) {
          return { passed: false, failReason: `Not consolidation (efficiency ${eff?.toFixed(2)} > 0.60)` };
        }
      }
      continue;
    }
    
    // status (HTF EQH/EQL)
    if (key === 'status') {
      // HTF pools don't carry explicit status in slim output, accept all
      continue;
    }
    
    // min_touches (HTF EQH/EQL)
    if (key === 'min_touches') {
      // Accept all — the detector already filters by min_touches
      continue;
    }
    
    // window (Kill Zone)
    if (key === 'window' && Array.isArray(expected)) {
      const session = det.tags?.session || det.properties?.session;
      if (!expected.includes(session)) {
        return { passed: false, failReason: `session: ${session} (expected [${expected.join(', ')}])` };
      }
      continue;
    }
    
    // zone_type (OB)
    if (key === 'zone_type') continue; // Always body in locked config
    
    // source filter (Sweep) — array of allowed sources
    if (key === 'source' && Array.isArray(expected)) {
      const actual = det.properties?.source;
      if (!expected.includes(actual)) return { passed: false, failReason: `source: ${actual} (expected [${expected.join(', ')}])` };
      continue;
    }
  }
  
  return { passed: true, failReason: null };
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Chain Evaluator — Timing Window Check
 * ═══════════════════════════════════════════════════════════════════════════════ */

function matchesTiming(detA, detB, timingWindow) {
  // Check if detB is within the timing window of detA.
  // detB must be at or after detA in time.
  
  const timeA = sToTS(detA.time);
  const timeB = sToTS(detB.time);
  
  if (timeB < timeA) return false; // Must be sequential
  
  if (timingWindow === 'same_bar') {
    return timeA === timeB;
  }
  
  if (timingWindow === 'same_kill_zone') {
    const kzA = detA.tags?.kill_zone || detA.properties?.kill_zone;
    const kzB = detB.tags?.kill_zone || detB.properties?.kill_zone;
    if (!kzA || kzA === 'NONE' || !kzB || kzB === 'NONE') return false;
    return kzA === kzB;
  }
  
  if (timingWindow === 'same_session') {
    const sA = detA.tags?.session || detA.properties?.session;
    const sB = detB.tags?.session || detB.properties?.session;
    return sA === sB && sA != null;
  }
  
  if (timingWindow === 'same_day') {
    const dA = detA.properties?.forex_day || extractDayFromTime(detA.time);
    const dB = detB.properties?.forex_day || extractDayFromTime(detB.time);
    return dA === dB;
  }
  
  if (timingWindow && timingWindow.startsWith('within_bars_')) {
    const maxBars = parseInt(timingWindow.split('_')[2]);
    const barA = detA.properties?.bar_index;
    const barB = detB.properties?.bar_index;
    if (barA == null || barB == null) {
      // Fall back to time-based approximation
      const tfSecondsMap = { '5m': 300, '15m': 900, '1H': 3600, '4H': 14400 };
      const tfSeconds = tfSecondsMap[sApp.tf] || 300;
      return (timeB - timeA) <= maxBars * tfSeconds;
    }
    return (barB - barA) >= 0 && (barB - barA) <= maxBars;
  }
  
  return true; // Unknown timing, allow
}

function sToTS(s) {
  if (!s) return null;
  let clean = s.replace(/[+-]\d{2}:\d{2}$/, '');
  clean = clean.includes('T') ? clean : clean.replace(' ', 'T');
  const noZ = clean.endsWith('Z') ? clean.slice(0, -1) : clean;
  return Math.floor(new Date(noZ + 'Z').getTime() / 1000);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Chain Evaluator — Chain Context Builder
 * ═══════════════════════════════════════════════════════════════════════════════ */

function buildChainContext(matchedSteps) {
  // Build accumulated context from matched steps so far.
  // Later steps can reference earlier results.
  
  const ctx = {};
  
  for (const ms of matchedSteps) {
    const det = ms.detection;
    const prim = ms.primitive;
    
    // MSS: establishes dealing range for OTE
    if (prim === 'mss') {
      ctx.mssDirection = det.direction;
      ctx.mssBrokenSwing = det.properties?.broken_swing;
      ctx.mssDisplacement = det.properties?.displacement;
      ctx.mssOriginCandle = det.properties?.origin_candle;
    }
    
    // OTE: establishes the zone for spatial constraints
    if (prim === 'ote') {
      const fibLevels = det.properties?.fib_levels;
      if (fibLevels) {
        // OTE zone is between lower (0.618) and upper (0.79) fib levels
        ctx.oteZone = {
          low: Math.min(fibLevels.lower || 0, fibLevels.upper || 0),
          high: Math.max(fibLevels.lower || 0, fibLevels.upper || 0),
          sweetSpot: fibLevels.sweet_spot,
        };
      }
      // Also store dealing range for reference
      ctx.dealingRange = det.properties?.dealing_range;
    }
    
    // Sweep: stores swept level for reference
    if (prim === 'liquidity_sweep') {
      ctx.sweptLevel = det.properties?.level_price;
      ctx.sweepSource = det.properties?.source;
    }
  }
  
  return ctx;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Chain Evaluator — Main Function
 * ═══════════════════════════════════════════════════════════════════════════════ */

function evaluateChain() {
  if (sApp.steps.length === 0 || !sApp.detectionData) {
    sApp.chainResults = null;
    updateChainOverlays();
    updateMetadata();
    updateFunnelBar();
    return;
  }
  
  const chainDef = getChainDefinition();
  const { index, kzIndex } = buildDetectionIndex(sApp.detectionData, sApp.tf);
  
  // Get all forex days to evaluate
  const days = sApp.currentWeek?.forex_days || [];
  
  const results = []; // ChainMatch[]
  
  for (const day of days) {
    const dayDets = index[day];
    if (!dayDets) continue;
    
    // Check asia_range gate for this day
    if (chainDef.gates.asia_range_tier && chainDef.gates.asia_range_tier.length > 0) {
      const asiaDets = dayDets['asia_range'] || [];
      if (asiaDets.length > 0) {
        const asiaRangePips = asiaDets[0].properties?.range_pips;
        let tier = 'wide';
        if (asiaRangePips < 10) tier = 'tight';
        else if (asiaRangePips <= 20) tier = 'mid';
        if (!chainDef.gates.asia_range_tier.includes(tier)) continue; // Skip this day
      }
    }
    
    // Get Step 1 candidates
    const step1 = chainDef.steps[0];
    const step1Primitives = Array.isArray(step1.primitive) ? step1.primitive : [step1.primitive];
    
    // Map primitive keys to detection data keys
    // htf_eqh_eql maps to htf_liquidity in detection data
    const mapPrimKey = (k) => k === 'htf_eqh_eql' ? 'htf_liquidity' : k === 'kill_zone' ? null : k;
    
    for (const primKey of step1Primitives) {
      const dataKey = mapPrimKey(primKey);
      if (!dataKey) continue;
      const candidates = dayDets[dataKey] || [];
      
      for (const candidate of candidates) {
        // Check direction
        if (!matchesDirection(candidate, step1.direction_match, chainDef.direction)) continue;
        
        // Check kill_zone gate (chain must start within a kill zone)
        if (chainDef.gates.kill_zone && chainDef.gates.kill_zone.length > 0) {
          const detKz = candidate.tags?.kill_zone || candidate.properties?.kill_zone;
          const detSession = candidate.tags?.session || candidate.properties?.session;
          const inKz = chainDef.gates.kill_zone.includes(detKz) || chainDef.gates.kill_zone.includes(detSession);
          if (!inKz) continue;
        }
        
        // Check Step 1 constraints
        const s1Check = matchesConstraints(candidate, step1.constraints, {});
        if (!s1Check.passed) continue;
        
        // Step 1 matches — now walk forward through remaining steps
        const matchedSteps = [{
          step: 1,
          primitive: primKey,
          detection: candidate,
          passed: true,
          failReason: null,
        }];
        
        let chainContext = buildChainContext(matchedSteps);
        let allPassed = true;
        let failedStepIndex = -1;
        let failedStepReason = null;
        
        for (let si = 1; si < chainDef.steps.length; si++) {
          const stepDef = chainDef.steps[si];
          const stepPrimitives = Array.isArray(stepDef.primitive) ? stepDef.primitive : [stepDef.primitive];
          const prevDet = matchedSteps[matchedSteps.length - 1].detection;
          
          let stepMatched = false;
          let bestCandidate = null;
          let bestFailReason = 'No matching detection found';
          
          for (const sPrimKey of stepPrimitives) {
            const sDataKey = mapPrimKey(sPrimKey);
            if (!sDataKey) continue;
            const stepCandidates = dayDets[sDataKey] || [];
            
            for (const sc of stepCandidates) {
              // Check direction
              if (!matchesDirection(sc, stepDef.direction_match, chainDef.direction)) continue;
              
              // Check timing
              if (!matchesTiming(prevDet, sc, stepDef.timing.window)) continue;
              
              // Check constraints
              const scCheck = matchesConstraints(sc, stepDef.constraints, chainContext);
              if (scCheck.passed) {
                bestCandidate = sc;
                stepMatched = true;
                matchedSteps.push({
                  step: si + 1,
                  primitive: sPrimKey,
                  detection: sc,
                  passed: true,
                  failReason: null,
                });
                chainContext = buildChainContext(matchedSteps);
                break;
              } else {
                // Track the best failure reason (closest to passing)
                bestFailReason = scCheck.failReason;
              }
            }
            if (stepMatched) break;
          }
          
          if (!stepMatched) {
            allPassed = false;
            failedStepIndex = si;
            failedStepReason = bestFailReason;
            
            // Record the failed step for near-miss reporting
            matchedSteps.push({
              step: si + 1,
              primitive: stepPrimitives[0],
              detection: null,
              passed: false,
              failReason: bestFailReason,
            });
            break; // Stop evaluating further steps
          }
        }
        
        // Determine match type
        const matchType = allPassed ? 'FULL_MATCH' : 
          (matchedSteps.filter(ms => ms.passed).length >= chainDef.steps.length - 1) ? 'NEAR_MISS' : null;
        
        if (matchType) {
          results.push({
            type: matchType,
            day: day,
            startTime: candidate.time,
            endTime: matchedSteps.filter(ms => ms.detection).slice(-1)[0]?.detection?.time || candidate.time,
            steps: matchedSteps,
            failedStep: failedStepIndex >= 0 ? failedStepIndex + 1 : null,
            failedReason: failedStepReason,
          });
        }
      }
    }
  }
  
  // Deduplicate: if two matches share the same Step 1 detection, keep the one with more steps matched
  const deduped = [];
  const seen = new Set();
  for (const r of results) {
    const key = r.steps[0]?.detection?.id;
    if (!key || seen.has(key)) continue;
    seen.add(key);
    deduped.push(r);
  }
  
  sApp.chainResults = deduped;
  
  // Update UI
  updateChainOverlays();
  updateMetadata();
  updateFunnelBar();
  
  console.log(`Chain evaluation: ${deduped.filter(r => r.type === 'FULL_MATCH').length} matches, ${deduped.filter(r => r.type === 'NEAR_MISS').length} near-misses`);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Update Funnel Bar
 * ═══════════════════════════════════════════════════════════════════════════════ */

function updateFunnelBar() {
  const bar = document.getElementById('funnel-bar');
  if (!bar) return;

  if (!sApp.chainResults || sApp.chainResults.length === 0) {
    if (sApp.steps.length > 0) {
      bar.innerHTML = '<span class="funnel-label">No matches found for this chain</span>';
    } else {
      bar.innerHTML = '<span class="funnel-label">Define a chain to see convergence funnel</span>';
    }
    return;
  }

  const matches = sApp.chainResults.filter(r => r.type === 'FULL_MATCH').length;
  const nearMisses = sApp.chainResults.filter(r => r.type === 'NEAR_MISS').length;
  
  // Build step-by-step funnel counts
  const stepCounts = [];
  for (let i = 0; i < sApp.steps.length; i++) {
    const count = sApp.chainResults.filter(r => 
      r.steps.filter(s => s.passed).length > i
    ).length;
    stepCounts.push(count);
  }
  
  // Build failure distribution for near-misses
  const failDist = {};
  for (const r of sApp.chainResults.filter(r => r.type === 'NEAR_MISS')) {
    const fs = r.failedStep;
    if (fs != null) {
      failDist[fs] = (failDist[fs] || 0) + 1;
    }
  }
  
  let html = '';
  
  // Step-by-step funnel
  for (let i = 0; i < stepCounts.length; i++) {
    if (i > 0) html += '<span class="funnel-arrow">→</span>';
    const step = sApp.steps[i];
    const prim = S_PRIMITIVES.find(p => p.key === step.primitive);
    html += `<div class="funnel-item">
      <span class="funnel-count">${stepCounts[i]}</span>
      <span class="funnel-label">${prim ? prim.label : step.primitive}</span>
    </div>`;
  }
  
  html += '<span class="funnel-arrow" style="margin:0 8px;">|</span>';
  html += `<div class="funnel-item"><span class="funnel-count" style="color:var(--teal)">${matches}</span> <span class="funnel-label">full</span></div>`;
  html += `<div class="funnel-item"><span class="funnel-count" style="color:var(--yellow)">${nearMisses}</span> <span class="funnel-label">near</span></div>`;
  
  bar.innerHTML = html;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * NOTE: updateChainOverlays() has been moved to strategy-chart.js (Task 6)
 * It is called by evaluateChain() and is available in global scope.
 * ═══════════════════════════════════════════════════════════════════════════════ */
