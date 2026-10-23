"""Single-document behavior editor for the client panel."""
import html


def render_prompt_workspace(bot_id: int, prompt: str, csrf_token: str, *, readonly: bool) -> str:
    disabled = "disabled" if readonly else ""
    read_attr = "readonly" if readonly else ""
    return f"""
      <form id="behaviorForm" method="post" action="/client/bots/{bot_id}/prompt/save?csrf_token={html.escape(csrf_token)}">
        <input type="hidden" name="csrf_token" value="{html.escape(csrf_token)}">
        <input type="hidden" id="promptFormat" name="prompt_format" value="{'targeted_patch' if prompt.strip() else 'single_prompt'}">
        <input type="hidden" id="patchReceipt" name="patch_receipt" value="">
        <div class="prompt-workspace" style="display:block; max-width:960px; margin:0 auto;">
          <div class="card">
            <div class="card-header">
              <h2>Tu prompt maestro</h2>
              <p>Define el comportamiento de tu bot en un solo documento. El asistente de Asistto te ayuda a integrar objetivos, criterios de respuesta, guardrails, reglas y ejemplos usando tu base de conocimiento y tus integraciones.</p>
            </div>
            <label for="promptEditMode">Tipo de cambio</label>
            <select id="promptEditMode" onchange="changePromptMode()" {disabled}>
              <option value="targeted_patch" {'selected' if prompt.strip() else ''}>Cambio puntual: conservar el resto</option>
              <option value="single_prompt" {'' if prompt.strip() else 'selected'}>Crear o revisar el comportamiento completo</option>
            </select>
            <div id="patchFields" style="display:{'block' if prompt.strip() else 'none'}; margin:16px 0;">
              <p>Reemplaza un dato en el contexto del negocio o los ejemplos. Las reglas y la constitución se conservan. Si hay dependencias pendientes en tus fuentes, el cambio se bloquea.</p>
              <label for="patchBefore">Dato actual (cópialo exactamente del prompt)</label>
              <input id="patchBefore" type="text" maxlength="240" {read_attr} oninput="invalidatePatch()" style="width:100%; box-sizing:border-box;" placeholder="Ej. Calle Antigua 10">
              <label for="patchAfter">Dato nuevo</label>
              <input id="patchAfter" type="text" maxlength="240" {read_attr} oninput="invalidatePatch()" style="width:100%; box-sizing:border-box;" placeholder="Ej. Calle Nueva 20">
              <p class="muted-text">Se revisan todas las apariciones del dato. No se modifican documentos de conocimiento ni configuraciones automáticamente.</p>
            </div>
            <label for="aiPromptInstruction">1. Describe lo que necesitas crear o cambiar</label>
            <textarea id="aiPromptInstruction" oninput="invalidatePatch()" style="min-height:130px;" {read_attr} placeholder="Ej. Cambia únicamente el domicilio donde se realizan las pruebas; conserva todas las demás reglas."></textarea>
            <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin:12px 0 24px;">
              <button class="btn primary-btn" type="button" id="btnAssistPrompt" onclick="requestAIPrompt()" {disabled}>Generar o ajustar prompt maestro</button>
              <span id="aiAssistLoader" role="status" aria-live="polite" style="display:none;">Preparando tu prompt maestro…</span>
            </div>
            <div id="promptAssistError" role="alert" style="display:none; margin-bottom:16px; color:var(--red); white-space:pre-wrap;"></div>
            <div id="promptAssistResult" role="status" aria-live="polite" style="display:none; margin-bottom:16px; white-space:pre-wrap;"></div>
            <label for="activePromptEditor">2. Revisa y edita tu prompt maestro</label>
            <p class="muted-text" style="font-size:13px;">Este documento contiene las instrucciones que ejecutará tu bot. Puedes editarlo directamente o pedirle ajustes al asistente. Generarlo no cambia el comportamiento activo.</p>
            <textarea id="activePromptEditor" name="prompt" style="min-height:350px; width:100%; box-sizing:border-box;" {read_attr} placeholder="Tu prompt maestro aparecerá aquí…">{html.escape(prompt)}</textarea>
            <div style="display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-top:20px;">
              <button class="btn primary-btn" id="btnSavePrompt" type="submit" {disabled}>Guardar y activar prompt maestro</button>
              <button class="btn secondary" type="button" onclick="downloadMasterPrompt()">Descargar prompt (.md)</button>
            </div>
            <p class="muted-text" style="font-size:12px; margin-top:12px;">Al guardar, esta versión se convierte en el comportamiento activo de tu bot en WhatsApp.</p>
          </div>
        </div>
      </form>
      <script>
        const patchOriginal = document.getElementById("activePromptEditor").value;
        let reviewedPatch = null;
        function invalidatePatch() {{
          document.getElementById("patchReceipt").value = "";
        }}
        function changePromptMode() {{
          const mode = document.getElementById("promptEditMode").value;
          document.getElementById("promptFormat").value = mode;
          document.getElementById("patchFields").style.display = mode === "targeted_patch" ? "block" : "none";
          invalidatePatch();
          document.getElementById("promptAssistResult").style.display = "none";
        }}
        function currentMasterPrompt() {{
          return window.promptEditor ? window.promptEditor.value() : document.getElementById("activePromptEditor").value;
        }}

        document.getElementById("behaviorForm")?.addEventListener("submit", function(event) {{
          if (window.promptEditor?.codemirror) window.promptEditor.codemirror.save();
          if (document.getElementById("promptEditMode").value === "targeted_patch" &&
              (!document.getElementById("patchReceipt").value || currentMasterPrompt() !== reviewedPatch)) {{
            event.preventDefault();
            document.getElementById("promptAssistError").textContent = "Revisa el cambio puntual antes de activarlo. No se permiten ediciones adicionales al reemplazo revisado.";
            document.getElementById("promptAssistError").style.display = "block";
            return;
          }}
          if (!currentMasterPrompt().trim()) {{
            event.preventDefault();
            document.getElementById("promptAssistError").textContent = "Escribe o genera un prompt maestro antes de guardar.";
            document.getElementById("promptAssistError").style.display = "block";
          }}
        }});

        function downloadMasterPrompt() {{
          const blob = new Blob([currentMasterPrompt()], {{ type: "text/markdown;charset=utf-8" }});
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = "prompt-maestro.md";
          link.click();
          URL.revokeObjectURL(url);
        }}

        async function requestAIPrompt() {{
          const instruction = document.getElementById("aiPromptInstruction").value.trim();
          const current = currentMasterPrompt();
          const mode = document.getElementById("promptEditMode").value;
          const before = document.getElementById("patchBefore").value;
          const after = document.getElementById("patchAfter").value;
          const error = document.getElementById("promptAssistError");
          const result = document.getElementById("promptAssistResult");
          error.style.display = "none";
          result.style.display = "none";
          if (!instruction) {{
            error.textContent = "Describe qué quieres que haga tu bot o qué necesitas cambiar.";
            error.style.display = "block";
            document.getElementById("aiPromptInstruction").focus();
            return;
          }}
          if (mode === "targeted_patch" && (!before.trim() || !after.trim())) {{
            error.textContent = "Indica el dato actual y el nuevo para limitar el cambio.";
            error.style.display = "block";
            return;
          }}
          invalidatePatch();
          const loader = document.getElementById("aiAssistLoader");
          const btn = document.getElementById("btnAssistPrompt");
          const saveBtn = document.getElementById("btnSavePrompt");
          const wasSaveDisabled = saveBtn.disabled;
          loader.style.display = "inline-block";
          btn.disabled = true;
          saveBtn.disabled = true;
          const csrfToken = document.querySelector('#behaviorForm input[name="csrf_token"]').value;
          const formData = new FormData();
          formData.append("instruction", instruction);
          formData.append("current_prompt", mode === "targeted_patch" && current === reviewedPatch ? patchOriginal : current);
          formData.append("mode", mode);
          formData.append("patch_before", before);
          formData.append("patch_after", after);
          formData.append("csrf_token", csrfToken);
          try {{
            const response = await fetch(`/client/bots/{bot_id}/prompt/assist?csrf_token=${{encodeURIComponent(csrfToken)}}`, {{
              method: "POST",
              headers: {{ "X-CSRF-Token": csrfToken, "Accept": "application/json" }},
              body: formData
            }});
            const data = await response.json();
            if (!response.ok || !data.ok || data.blocked) {{
              throw new Error(data.blocked_reason || data.error || "No fue posible generar el prompt maestro.");
            }}
            if (currentMasterPrompt() !== current || document.getElementById("promptEditMode").value !== mode ||
                document.getElementById("aiPromptInstruction").value.trim() !== instruction ||
                document.getElementById("patchBefore").value !== before || document.getElementById("patchAfter").value !== after) {{
              throw new Error("Editaste el prompt mientras se generaba. Conservamos tus cambios; vuelve a solicitar el ajuste con esta versión.");
            }}
            if (mode === "targeted_patch" && (!data.patch_receipt || !data.change)) {{
              throw new Error("La revisión del cambio puntual está incompleta. No se aplicó.");
            }}
            if (window.promptEditor) {{
              window.promptEditor.value(data.prompt);
              window.promptEditor.codemirror?.save();
            }} else {{
              document.getElementById("activePromptEditor").value = data.prompt;
            }}
            const warnings = data.validation?.warnings || [];
            document.getElementById("promptFormat").value = mode;
            document.getElementById("patchReceipt").value = data.patch_receipt || "";
            reviewedPatch = mode === "targeted_patch" ? currentMasterPrompt() : null;
            result.textContent = (mode === "targeted_patch"
              ? `Cambio puntual revisado (${{data.change.occurrences}} apariciones). Antes: ${{data.change.before}} → Después: ${{data.change.after}}. El resto del prompt se conserva. Revisa y guarda para activarlo.`
              : "Prompt preparado. Se revisó que incluya las secciones requeridas. Revisa sus reglas y ejemplos antes de guardarlo.") +
              (warnings.length ? "\\n" + warnings.join("\\n") : "");
            result.style.display = "block";
          }} catch (e) {{
            error.textContent = e.message;
            error.style.display = "block";
          }} finally {{
            loader.style.display = "none";
            btn.disabled = {str(readonly).lower()};
            saveBtn.disabled = wasSaveDisabled;
          }}
        }}
      </script>
"""
