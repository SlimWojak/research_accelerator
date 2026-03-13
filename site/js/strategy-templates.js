/* ═══════════════════════════════════════════════════════════════════════════════
 * strategy-templates.js — Template save/load STUB
 *                         for the Strategy Designer page
 * ═══════════════════════════════════════════════════════════════════════════════ */

/* ═══════════════════════════════════════════════════════════════════════════════
 * Save Template (STUB — Task 7 will implement full persistence)
 * ═══════════════════════════════════════════════════════════════════════════════ */

function saveTemplate() {
  const nameInput = document.getElementById('template-name');
  const name = nameInput ? nameInput.value.trim() : '';

  if (!name) {
    alert('Please enter a strategy name');
    return;
  }

  if (sApp.steps.length === 0) {
    alert('Cannot save empty strategy');
    return;
  }

  // Update template name in state
  sApp.templateName = name;

  // Get chain definition
  const definition = getChainDefinition();

  console.log('Template save not yet implemented (Task 7)');
  console.log('Would POST to /api/strategies/' + name);
  console.log('Definition:', JSON.stringify(definition, null, 2));

  // TODO: Task 7 will implement:
  // POST /api/strategies/{name}
  // Body: definition JSON
  // Response: success/failure
  // On success: show confirmation toast

  alert(`Template "${name}" would be saved here.\n\nImplementation coming in Task 7.`);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Load Template List (STUB — Task 7 will implement)
 * ═══════════════════════════════════════════════════════════════════════════════ */

async function loadTemplateList() {
  console.log('Template list loading not yet implemented (Task 7)');

  // TODO: Task 7 will implement:
  // GET /api/strategies
  // Response: array of template names
  // Return: array of { name, created_at, updated_at }

  return [];
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Load Template (STUB — Task 7 will implement)
 * ═══════════════════════════════════════════════════════════════════════════════ */

async function loadTemplate(name) {
  console.log('Template loading not yet implemented (Task 7)');
  console.log('Would GET from /api/strategies/' + name);

  // TODO: Task 7 will implement:
  // GET /api/strategies/{name}
  // Response: definition JSON
  // On success:
  //   - Load definition into sApp.steps
  //   - Load definition gates into sApp.gates
  //   - Set sApp.direction
  //   - Set sApp.templateName
  //   - Re-render chain builder
  //   - Re-evaluate chain

  alert(`Loading template "${name}" not yet implemented.\n\nComing in Task 7.`);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Load Template Dialog (User-facing)
 * ═══════════════════════════════════════════════════════════════════════════════ */

async function loadTemplateDialog() {
  const templates = await loadTemplateList();

  if (templates.length === 0) {
    alert('No saved templates found.\n\nImplementation coming in Task 7.');
    return;
  }

  // TODO: Task 7 will implement:
  // Show modal/dropdown with template list
  // User selects template
  // Call loadTemplate(name)
}

// Expose loadTemplateDialog as the handler for the Load button
window.loadTemplate = loadTemplateDialog;
