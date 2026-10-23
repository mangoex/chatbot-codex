// Run with: node tests/test_prompt_workspace.js (Python launcher `py` required).
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const vm = require('node:vm');

const render = spawnSync('py', ['-c',
  'from app.prompt_workspace import render_prompt_workspace; print(render_prompt_workspace(7, "Original", "csrf", readonly=False))'
], { encoding: 'utf8', env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
assert.equal(render.status, 0, render.stderr);
assert.equal((render.stdout.match(/<textarea/g) || []).length, 2);
assert.equal(render.stdout.includes('<select'), false);
assert.equal(render.stdout.includes('patchBefore'), false);
assert.equal(render.stdout.includes('patchAfter'), false);
const script = render.stdout.match(/<script>([\s\S]*?)<\/script>/)[1];

function setup() {
  const elements = Object.fromEntries([
    'behaviorForm', 'aiPromptInstruction', 'activePromptEditor', 'promptAssistError',
    'promptAssistResult', 'aiAssistLoader', 'btnAssistPrompt', 'btnSavePrompt',
    'reviewReceipt', 'reviewRequired',
  ].map(id => [id, { value: '', style: {}, disabled: false, textContent: '',
    focus() { this.focused = true; }, addEventListener(type, fn) { this[type] = fn; } }]));
  elements.activePromptEditor.value = 'Original';
  elements.aiPromptInstruction.value = 'Ajusta el tono';
  elements.reviewRequired.value = '0';
  const requests = [];
  const sandbox = {
    window: {}, FormData, Blob, URL, console,
    document: {
      getElementById: id => elements[id], querySelector: () => ({ value: 'csrf' }),
    },
    fetch: async (url, options) => {
      requests.push({ url, options });
      return { ok: true, json: async () => ({ ok: true, prompt: 'Nuevo', review_receipt: 'signed-review',
        changes: [{ before: 'Horario anterior', after: 'Horario nuevo' }],
        summary: 'Horario actualizado; otras reglas conservadas.', validation: { warnings: [] } }) };
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
  assert.equal(requests[0].options.body.get('mode'), 'guarded_prompt');
  assert.equal(requests[0].options.body.get('review_receipt'), '');
  assert.equal(elements.reviewReceipt.value, 'signed-review');
  assert.equal(elements.reviewRequired.value, '1');
  assert.match(elements.promptAssistResult.textContent, /Horario anterior.*Horario nuevo/);
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

  ({ sandbox, elements, requests } = setup());
  await sandbox.requestAIPrompt();
  elements.aiPromptInstruction.value = 'Ahora agrega el servicio de instalación';
  await sandbox.requestAIPrompt();
  assert.equal(requests[1].options.body.get('current_prompt'), 'Nuevo');
  assert.equal(requests[1].options.body.get('review_receipt'), 'signed-review');
  assert.equal(requests[1].options.body.get('patch_before'), null);
  prevented = false;
  elements.behaviorForm.submit({ preventDefault() { prevented = true; } });
  assert.equal(prevented, false);
  elements.activePromptEditor.value = 'Nuevo con regla adicional';
  elements.behaviorForm.submit({ preventDefault() { prevented = true; } });
  assert.equal(prevented, true);

  ({ sandbox, elements } = setup());
  sandbox.fetch = async () => ({ ok: true, json: async () => ({ ok: true, prompt: 'Sin revisión' }) });
  await sandbox.requestAIPrompt();
  assert.equal(elements.activePromptEditor.value, 'Original');
  assert.equal(elements.reviewReceipt.value, '');

  ({ sandbox, elements } = setup());
  sandbox.fetch = () => new Promise(resolve => { complete = resolve; });
  const reviewing = sandbox.requestAIPrompt();
  elements.aiPromptInstruction.value = 'Cambia la dirección';
  complete({ ok: true, json: async () => ({ ok: true, prompt: 'Obsoleto', review_receipt: 'signed' }) });
  await reviewing;
  assert.equal(elements.activePromptEditor.value, 'Original');
  assert.equal(elements.reviewReceipt.value, '');
  console.log('Editor: generación, errores, conflicto, edición concurrente y guardado verificados.');
})().catch(error => { console.error(error); process.exitCode = 1; });
