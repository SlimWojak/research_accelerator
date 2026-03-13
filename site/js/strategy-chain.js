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
 * Chain Evaluator STUB (Task 5 will implement full logic)
 * ═══════════════════════════════════════════════════════════════════════════════ */

function evaluateChain() {
  if (sApp.steps.length === 0) {
    sApp.chainResults = null;
    updateMetadata();
    updateFunnelBar();
    return;
  }

  console.log('Chain evaluation not yet implemented (Task 5)');
  console.log('Chain definition:', getChainDefinition());

  // STUB: return empty results for now
  sApp.chainResults = [];
  updateMetadata();
  updateFunnelBar();

  // TODO: Task 5 will implement:
  // 1. Pre-index detections by (forex_day, kill_zone)
  // 2. For each Step 1 candidate matching direction + constraints:
  //    a. Walk forward through subsequent steps
  //    b. Search temporal index within timing window for each step
  //    c. Check step-specific constraints
  //    d. Accumulate chain_context
  //    e. Record FULL_MATCH / NEAR_MISS (N-1) / NO_MATCH
  // 3. For near-misses: record which step failed, why, specific values vs thresholds
  // 4. Return ChainMatch[] with timestamps, step details, failure diagnostics
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Update Funnel Bar
 * ═══════════════════════════════════════════════════════════════════════════════ */

function updateFunnelBar() {
  const bar = document.getElementById('funnel-bar');
  if (!bar) return;

  if (!sApp.chainResults || sApp.chainResults.length === 0) {
    bar.innerHTML = '<span class="funnel-label">Define a chain to see convergence funnel</span>';
    return;
  }

  // TODO: Task 6 will implement real funnel stats display
  // For now, just show a placeholder
  const matches = sApp.chainResults.filter(r => r.type === 'FULL_MATCH').length;
  const nearMisses = sApp.chainResults.filter(r => r.type === 'NEAR_MISS').length;

  bar.innerHTML = `
    <div class="funnel-item">
      <span class="funnel-count">${matches}</span>
      <span class="funnel-label">matches</span>
    </div>
    <span class="funnel-arrow">→</span>
    <div class="funnel-item">
      <span class="funnel-count" style="color:var(--yellow)">${nearMisses}</span>
      <span class="funnel-label">near-misses</span>
    </div>
  `;
}
