/* ═══════════════════════════════════════════════════════════════════════════════
 * strategy-templates.js — Template save/load persistence
 *                         for the Strategy Designer page
 *
 * When serve.py is running (localhost), disk persistence works via API.
 * When on static hosting (GitHub Pages), localStorage is used automatically.
 * ═══════════════════════════════════════════════════════════════════════════════ */

/* ── Server Detection ──────────────────────────────────────────────────────── */

let _stServerAvailable = null;

async function isSTServerAvailable() {
  if (_stServerAvailable !== null) return _stServerAvailable;
  try {
    const resp = await fetch('/api/strategies', { method: 'GET' });
    _stServerAvailable = resp.ok;
  } catch (e) {
    _stServerAvailable = false;
  }
  return _stServerAvailable;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Save Template
 * ═══════════════════════════════════════════════════════════════════════════════ */

async function saveTemplate() {
  const def = getChainDefinition();
  const name = sApp.templateName.trim();
  
  if (!name) {
    alert('Enter a strategy name first');
    return;
  }
  
  if (def.steps.length === 0) {
    alert('Add at least one step to save');
    return;
  }
  
  // Sanitize name for URL (alphanumeric, hyphens, underscores only)
  const safeName = name.replace(/[^a-zA-Z0-9_-]/g, '_');
  
  // Try server first
  try {
    const resp = await fetch(`/api/strategies/${safeName}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(def),
    });
    
    if (resp.ok) {
      console.log(`Strategy "${name}" saved as ${safeName}`);
      // Brief visual feedback
      const btn = document.getElementById('btn-save-template');
      if (btn) {
        btn.textContent = 'Saved!';
        btn.style.background = 'var(--teal)';
        setTimeout(() => {
          btn.textContent = 'Save';
          btn.style.background = '';
        }, 1500);
      }
      return;
    }
  } catch (e) { /* server not available */ }

  // Fallback: localStorage
  try {
    localStorage.setItem('ra_strategy_' + safeName, JSON.stringify(def));
    // Maintain an index of saved strategy names
    const index = JSON.parse(localStorage.getItem('ra_strategy_index') || '[]');
    if (!index.includes(safeName)) {
      index.push(safeName);
      index.sort();
    }
    localStorage.setItem('ra_strategy_index', JSON.stringify(index));

    console.log(`Strategy "${name}" saved to localStorage as ${safeName}`);
    const btn = document.getElementById('btn-save-template');
    if (btn) {
      btn.textContent = 'Saved!';
      btn.style.background = 'var(--teal)';
      setTimeout(() => {
        btn.textContent = 'Save';
        btn.style.background = '';
      }, 1500);
    }
  } catch (e) {
    console.error('Save error:', e);
    alert('Save error: ' + e.message);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Load Template List
 * ═══════════════════════════════════════════════════════════════════════════════ */

async function loadTemplateList() {
  // Try server first
  try {
    const resp = await fetch('/api/strategies');
    if (resp.ok) return await resp.json();
  } catch (e) { /* server not available */ }

  // Fallback: localStorage
  try {
    return JSON.parse(localStorage.getItem('ra_strategy_index') || '[]');
  } catch (e) {
    console.error('Load list error:', e);
    return [];
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Load Template
 * ═══════════════════════════════════════════════════════════════════════════════ */

async function loadTemplate(name) {
  let def = null;

  // Try server first
  try {
    const resp = await fetch(`/api/strategies/${name}`);
    if (resp.ok) {
      def = await resp.json();
    }
  } catch (e) { /* server not available */ }

  // Fallback: localStorage
  if (!def) {
    try {
      const stored = localStorage.getItem('ra_strategy_' + name);
      if (stored) {
        def = JSON.parse(stored);
      }
    } catch (e) { /* parse error */ }
  }

  if (!def) {
    alert('Load failed: strategy not found');
    return;
  }

  // Apply template to sApp state
  sApp.templateName = def.name || name;
  sApp.direction = def.direction || 'bearish';
  sApp.steps = (def.steps || []).map(s => ({
    ...s,
    _advancedExpanded: false,
  }));
  sApp.gates = def.gates || { kill_zone: ['lokz', 'nyokz'], asia_range_tier: ['tight', 'mid'] };
  
  // Update UI
  const nameInput = document.getElementById('template-name');
  if (nameInput) nameInput.value = sApp.templateName;
  
  // Update direction buttons
  const bullBtn = document.getElementById('btn-bull');
  const bearBtn = document.getElementById('btn-bear');
  if (bullBtn && bearBtn) {
    bullBtn.className = 'direction-btn' + (sApp.direction === 'bullish' ? ' active-bull' : '');
    bearBtn.className = 'direction-btn' + (sApp.direction === 'bearish' ? ' active-bear' : '');
  }
  
  // Re-render chain builder and gates
  renderChainBuilder();
  renderGates();
  
  // Re-evaluate chain
  evaluateChain();
  
  console.log(`Template "${name}" loaded`);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Load Template Dialog (User-facing)
 * ═══════════════════════════════════════════════════════════════════════════════ */

function showLoadDialog() {
  loadTemplateList().then(names => {
    if (names.length === 0) {
      alert('No saved strategies found');
      return;
    }
    
    // Create simple overlay dialog with list
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:300;display:flex;align-items:center;justify-content:center;';
    
    const dialog = document.createElement('div');
    dialog.style.cssText = 'background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px;min-width:280px;max-height:400px;overflow-y:auto;';
    
    const title = document.createElement('div');
    title.style.cssText = 'font-size:13px;font-weight:600;color:var(--text);margin-bottom:12px;';
    title.textContent = 'Load Strategy';
    dialog.appendChild(title);
    
    for (const name of names) {
      const btn = document.createElement('button');
      btn.style.cssText = 'display:block;width:100%;text-align:left;padding:8px 12px;margin-bottom:4px;background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text);font-family:var(--mono);font-size:12px;cursor:pointer;';
      btn.textContent = name;
      btn.addEventListener('click', () => {
        overlay.remove();
        loadTemplate(name);
      });
      btn.addEventListener('mouseenter', () => { btn.style.borderColor = 'var(--blue)'; });
      btn.addEventListener('mouseleave', () => { btn.style.borderColor = 'var(--border)'; });
      dialog.appendChild(btn);
    }
    
    const cancelBtn = document.createElement('button');
    cancelBtn.style.cssText = 'display:block;width:100%;text-align:center;padding:8px;margin-top:8px;background:none;border:1px solid var(--border);border-radius:4px;color:var(--muted);font-size:11px;cursor:pointer;';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.addEventListener('click', () => overlay.remove());
    dialog.appendChild(cancelBtn);
    
    overlay.appendChild(dialog);
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
    document.body.appendChild(overlay);
  });
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Export / Import Strategies
 * ═══════════════════════════════════════════════════════════════════════════════ */

/**
 * Export all saved strategies as a single JSON file download.
 */
function exportStrategies() {
  loadTemplateList().then(async function(names) {
    var strategies = {};
    for (var i = 0; i < names.length; i++) {
      var name = names[i];
      // Try server first
      try {
        var resp = await fetch('/api/strategies/' + name);
        if (resp.ok) { strategies[name] = await resp.json(); continue; }
      } catch (e) { /* server not available */ }
      // Fallback: localStorage
      var stored = localStorage.getItem('ra_strategy_' + name);
      if (stored) {
        try { strategies[name] = JSON.parse(stored); } catch (e) { /* skip */ }
      }
    }

    var exportData = {
      type: 'ra_strategies_export',
      strategies: strategies,
      exportedAt: new Date().toISOString(),
    };

    var blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'ra_strategies.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  });
}

/**
 * Import strategies from a JSON file. Prompts for file selection.
 */
function importStrategies() {
  var input = document.createElement('input');
  input.type = 'file';
  input.accept = '.json';
  input.addEventListener('change', async function(e) {
    var file = e.target.files[0];
    if (!file) return;
    try {
      var text = await file.text();
      var data = JSON.parse(text);
      if (data.type !== 'ra_strategies_export' || !data.strategies) {
        alert('Unrecognized file format');
        return;
      }
      var count = 0;
      var entries = Object.entries(data.strategies);
      for (var i = 0; i < entries.length; i++) {
        var name = entries[i][0];
        var def = entries[i][1];
        var saved = false;
        // Try server first
        try {
          var resp = await fetch('/api/strategies/' + name, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(def),
          });
          if (resp.ok) { saved = true; }
        } catch (e) { /* server not available */ }
        // Fallback: localStorage
        if (!saved) {
          localStorage.setItem('ra_strategy_' + name, JSON.stringify(def));
          var index = JSON.parse(localStorage.getItem('ra_strategy_index') || '[]');
          if (!index.includes(name)) {
            index.push(name);
            index.sort();
          }
          localStorage.setItem('ra_strategy_index', JSON.stringify(index));
        }
        count++;
      }
      alert('Imported ' + count + ' strategies');
    } catch (err) {
      alert('Import error: ' + err.message);
    }
  });
  input.click();
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Event Listeners
 * ═══════════════════════════════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {
  const nameInput = document.getElementById('template-name');
  if (nameInput) {
    nameInput.addEventListener('input', (e) => {
      sApp.templateName = e.target.value;
    });
  }
});
