"""Single-document behavior editor for the client panel."""
import html


def render_prompt_workspace(bot_id: int, prompt: str, csrf_token: str, *, readonly: bool) -> str:
    disabled = "disabled" if readonly else ""
    read_attr = "readonly" if readonly else ""
    return f"""
      <form id="behaviorForm" method="post" action="/client/bots/{bot_id}/prompt/save?csrf_token={html.escape(csrf_token)}">
        <input type="hidden" name="csrf_token" value="{html.escape(csrf_token)}">
        <input type="hidden" name="prompt_format" value="single_prompt">
        <input type="hidden" id="reviewReceipt" name="review_receipt" value="">
        <input type="hidden" id="reviewRequired" name="review_required" value="0">
        <div class="prompt-workspace" style="display:block; max-width:960px; margin:0 auto;">
          <div class="card">
            <div class="card-header">
              <h2>Tu prompt maestro</h2>
              <p>Define el comportamiento de tu bot en un solo documento. El asistente de Asistto te ayuda a integrar objetivos, criterios de respuesta, guardrails, reglas y ejemplos usando tu base de conocimiento y tus integraciones.</p>
            </div>
            <label for="aiPromptInstruction">1. Describe lo que necesitas crear o cambiar</label>
            <textarea id="aiPromptInstruction" style="min-height:130px;" {read_attr} placeholder="Ej. Los sábados atendemos de 9 a 14. Agrega el servicio de instalación. Nuestra dirección ahora es Avenida Central 20. Conserva las demás reglas."></textarea>
            <p class="muted-text" style="font-size:13px;">Describe el cambio con tus palabras. Revisaremos las reglas y las fuentes; si falta información o hay un conflicto, te indicaremos qué resolver.</p>
            <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin:12px 0 24px;">
              <button class="btn primary-btn" type="button" id="btnAssistPrompt" onclick="requestAIPrompt()" {disabled}>Generar o ajustar prompt maestro</button>
              <span id="aiAssistLoader" role="status" aria-live="polite" style="display:none;">Revisando solicitud, reglas y fuentes…</span>
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
        let reviewedPrompt = null;
        function currentMasterPrompt() {{
          return window.promptEditor ? window.promptEditor.value() : document.getElementById("activePromptEditor").value;
        }}

        document.getElementById("behaviorForm")?.addEventListener("submit", function(event) {{
          if (window.promptEditor?.codemirror) window.promptEditor.codemirror.save();
          if (document.getElementById("reviewRequired").value === "1" &&
              (!document.getElementById("reviewReceipt").value || currentMasterPrompt() !== reviewedPrompt)) {{
            event.preventDefault();
            document.getElementById("promptAssistError").textContent = "El borrador cambió después de revisarlo. Recarga el prompt activo y pide los ajustes desde el cuadro superior.";
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
          formData.append("current_prompt", current);
          formData.append("mode", "guarded_prompt");
          formData.append("review_receipt", document.getElementById("reviewReceipt").value);
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
            if (currentMasterPrompt() !== current || document.getElementById("aiPromptInstruction").value.trim() !== instruction) {{
              throw new Error("Editaste el prompt mientras se generaba. Conservamos tus cambios; vuelve a solicitar el ajuste con esta versión.");
            }}
            if (!data.review_receipt) {{
              throw new Error("La revisión no terminó. Conservamos el prompt actual; vuelve a solicitar el ajuste.");
            }}
            if (window.promptEditor) {{
              window.promptEditor.value(data.prompt);
              window.promptEditor.codemirror?.save();
            }} else {{
              document.getElementById("activePromptEditor").value = data.prompt;
            }}
            const warnings = data.validation?.warnings || [];
            document.getElementById("reviewReceipt").value = data.review_receipt;
            document.getElementById("reviewRequired").value = "1";
            reviewedPrompt = currentMasterPrompt();
            const changes = (data.changes || []).map(change =>
              "Antes: " + change.before.slice(0, 300) + " → Después: " + (change.after.slice(0, 300) || "(retirado)")).join("\\n");
            result.textContent = "Borrador revisado. " + (data.summary || "Revisa el resultado antes de guardarlo.") +
              (changes ? "\\n" + changes : "") + "\\nTodavía no se ha activado. Puedes pedir otro ajuste arriba o guardar esta versión." +
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
