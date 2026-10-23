// Run with: node tests/test_prompt_workspace.js (Python launcher `py` required).
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const vm = require('node:vm');

const render = spawnSync('py', ['-c',
  'from app.prompt_workspace import render_prompt_workspace; print(render_prompt_workspace(7, "Original", "csrf", readonly=False))'
], { encoding: 'utf8', env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
assert.equal(render.status, 0, render.stderr);
const script = render.stdout.match(/<script>([\s\S]*?)<\/script>/)[1];

function setup() {
  const elements = Object.fromEntries([
    'behaviorForm', 'aiPromptInstruction', 'activePromptEditor', 'promptAssistError',
    'promptAssistResult', 'aiAssistLoader', 'btnAssistPrompt', 'btnSavePrompt',
    'promptEditMode', 'promptFormat', 'patchReceipt', 'patchBefore', 'patchAfter', 'patchFields',
  ].map(id => [id, { value: '', style: {}, disabled: false, textContent: '',
    focus() { this.focused = true; }, addEventListener(type, fn) { this[type] = fn; } }]));
  elements.activePromptEditor.value = 'Original';
  elements.aiPromptInstruction.value = 'Ajusta el tono';
  elements.promptEditMode.value = 'single_prompt';
  const requests = [];
  const sandbox = {
    window: {}, FormData, Blob, URL, console,
    document: {
      getElementById: id => elements[id], querySelector: () => ({ value: 'csrf' }),
    },
    fetch: async (url, options) => {
      requests.push({ url, options });
      return { ok: true, json: async () => ({ ok: true, prompt: 'Nuevo', validation: { warnings: [] } }) };
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(script, sandbox);
  return { sandbox, elements, requests };
}

(async () => {
  let { sandbox, elements, requests } = setup();
  elements.aiPromptInstruction.value = ' ';
  await sandbox.requestAIPrompt();
  assert.equal(requests.length, 0);
  assert.equal(elements.aiPromptInstruction.focused, true);
  assert.equal(elements.activePromptEditor.value, 'Original');

  ({ sandbox, elements, requests } = setup());
  await sandbox.requestAIPrompt();
  assert.equal(elements.activePromptEditor.value, 'Nuevo');
  assert.equal(requests.length, 1);
  assert.equal(requests[0].options.body.get('mode'), 'single_prompt');
  assert.equal(requests[0].options.body.get('current_prompt'), 'Original');
  assert.equal(requests[0].options.body.get('auto_publish'), null);
  assert.equal(requests[0].options.body.get('pbd_constitution'), null);
  assert.equal(requests[0].options.headers['X-CSRF-Token'], 'csrf');
  assert.equal(elements.btnSavePrompt.disabled, false);

  for (const response of [
    { ok: false, json: async () => ({ error: 'Proveedor falló' }) },
    { ok: true, json: async () => ({ blocked: true, blocked_reason: 'Regla incompatible' }) },
    { ok: false, json: async () => { throw new Error('Respuesta incompleta'); } },
  ]) {
    ({ sandbox, elements } = setup());
    sandbox.fetch = async () => response;
    await sandbox.requestAIPrompt();
    assert.equal(elements.activePromptEditor.value, 'Original');
    assert.equal(elements.promptAssistError.style.display, 'block');
    assert.equal(elements.btnSavePrompt.disabled, false);
    assert.equal(elements.btnAssistPrompt.disabled, false);
  }

  ({ sandbox, elements } = setup());
  let complete;
  sandbox.fetch = () => new Promise(resolve => { complete = resolve; });
  const pending = sandbox.requestAIPrompt();
  assert.equal(elements.btnSavePrompt.disabled, true);
  elements.activePromptEditor.value = 'Edición mientras espero';
  complete({ ok: true, json: async () => ({ ok: true, prompt: 'Respuesta anterior' }) });
  await pending;
  assert.equal(elements.activePromptEditor.value, 'Edición mientras espero');
  assert.match(elements.promptAssistError.textContent, /Conservamos tus cambios/);

  ({ sandbox, elements } = setup());
  let richValue = 'Borrador enriquecido';
  sandbox.window.promptEditor = {
    value(next) { if (next !== undefined) richValue = next; return richValue; },
    codemirror: { save() { elements.activePromptEditor.value = richValue; } },
  };
  await sandbox.requestAIPrompt();
  assert.equal(richValue, 'Nuevo');
  assert.equal(elements.activePromptEditor.value, 'Nuevo');

  ({ sandbox, elements } = setup());
  elements.activePromptEditor.value = '';
  let prevented = false;
  elements.behaviorForm.submit({ preventDefault() { prevented = true; } });
  assert.equal(prevented, true);

  // A targeted change is never saved without a receipt, even if the editor is valid.
  ({ sandbox, elements, requests } = setup());
  elements.promptEditMode.value = 'targeted_patch';
  elements.patchBefore.value = 'Original';
  elements.patchAfter.value = 'Nuevo';
  sandbox.changePromptMode();
  assert.equal(elements.promptFormat.value, 'targeted_patch');
  prevented = false;
  elements.behaviorForm.submit({ preventDefault() { prevented = true; } });
  assert.equal(prevented, true);
  sandbox.fetch = async (url, options) => {
    requests.push({ url, options });
    return { ok: true, json: async () => ({ ok: true, prompt: 'Nuevo', patch_receipt: 'signed-review',
      change: { before: 'Original', after: 'Nuevo', occurrences: 1 } }) };
  };
  await sandbox.requestAIPrompt();
  assert.equal(requests[0].options.body.get('mode'), 'targeted_patch');
  assert.equal(requests[0].options.body.get('patch_before'), 'Original');
  assert.equal(requests[0].options.body.get('patch_after'), 'Nuevo');
  assert.equal(elements.patchReceipt.value, 'signed-review');
  assert.match(elements.promptAssistResult.textContent, /Original.*Nuevo/);
  prevented = false;
  elements.behaviorForm.submit({ preventDefault() { prevented = true; } });
  assert.equal(prevented, false);
  // Re-review uses the active baseline, never chains model edits as a new source.
  await sandbox.requestAIPrompt();
  assert.equal(requests[1].options.body.get('current_prompt'), 'Original');
  elements.activePromptEditor.value = 'Nuevo con otra regla';
  elements.behaviorForm.submit({ preventDefault() { prevented = true; } });
  assert.equal(prevented, true);
  sandbox.invalidatePatch();
  assert.equal(elements.patchReceipt.value, '');

  // Incomplete targeted response cannot replace the editor.
  ({ sandbox, elements } = setup());
  elements.promptEditMode.value = 'targeted_patch';
  elements.patchBefore.value = 'Original';
  elements.patchAfter.value = 'Nuevo';
  await sandbox.requestAIPrompt();
  assert.equal(elements.activePromptEditor.value, 'Original');
  assert.equal(elements.patchReceipt.value, '');

  // Changing requested values while reviewing must not apply the old result.
  ({ sandbox, elements } = setup());
  elements.promptEditMode.value = 'targeted_patch';
  elements.patchBefore.value = 'Original';
  elements.patchAfter.value = 'Nuevo';
  sandbox.fetch = () => new Promise(resolve => { complete = resolve; });
  const reviewing = sandbox.requestAIPrompt();
  elements.patchAfter.value = 'Otro';
  complete({ ok: true, json: async () => ({ ok: true, prompt: 'Nuevo', patch_receipt: 'signed', change: {} }) });
  await reviewing;
  assert.equal(elements.activePromptEditor.value, 'Original');
  assert.equal(elements.patchReceipt.value, '');
  console.log('Editor: generación, errores, conflicto, edición concurrente y guardado verificados.');
})().catch(error => { console.error(error); process.exitCode = 1; });
