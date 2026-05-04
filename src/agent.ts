import type { AppConfig } from "./config";
import type {
  AgentDecision,
  AgentEngine,
  ChatMessage,
  Conversation,
  Tenant,
} from "./types";

const fallbackDecision: AgentDecision = {
  intent: "handoff",
  reply:
    "Gracias por escribirnos. En este momento no pude procesar tu mensaje automaticamente, pero ya lo tengo registrado para darle seguimiento.",
  tool: { name: "none" },
};

export class OpenRouterAgent implements AgentEngine {
  constructor(private readonly config: AppConfig) {}

  async decide(input: {
    tenant: Tenant;
    conversation: Conversation;
    incomingText: string;
    recentMessages: ChatMessage[];
  }): Promise<AgentDecision> {
    if (!this.config.OPENROUTER_API_KEY) {
      throw new Error("OPENROUTER_API_KEY is required to call the agent");
    }

    const response = await fetch("https://openrouter.ai/api/v1/chat/completions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${this.config.OPENROUTER_API_KEY}`,
        "Content-Type": "application/json",
        ...(this.config.OPENROUTER_SITE_URL
          ? { "HTTP-Referer": this.config.OPENROUTER_SITE_URL }
          : {}),
        "X-Title": this.config.OPENROUTER_APP_NAME,
      },
      body: JSON.stringify({
        model: this.config.OPENROUTER_MODEL,
        temperature: 0.2,
        messages: [
          {
            role: "system",
            content: buildSystemPrompt(input.tenant),
          },
          ...formatHistory(input.recentMessages),
          {
            role: "user",
            content: input.incomingText,
          },
        ],
      }),
    });

    const body = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(`OpenRouter request failed: ${response.status} ${JSON.stringify(body)}`);
    }

    const content = body?.choices?.[0]?.message?.content;
    if (typeof content !== "string") {
      return fallbackDecision;
    }

    return parseAgentDecision(content);
  }
}

export function parseAgentDecision(content: string): AgentDecision {
  const normalized = content
    .trim()
    .replace(/^```json\s*/i, "")
    .replace(/^```\s*/i, "")
    .replace(/```$/i, "")
    .trim();

  try {
    const parsed = JSON.parse(normalized) as Partial<AgentDecision>;
    const reply = typeof parsed.reply === "string" ? parsed.reply.trim() : "";

    if (!reply) {
      return fallbackDecision;
    }

    return {
      reply,
      intent: normalizeIntent(parsed.intent),
      tool: {
        name: normalizeToolName(parsed.tool?.name),
        arguments:
          parsed.tool?.arguments && typeof parsed.tool.arguments === "object"
            ? parsed.tool.arguments
            : {},
      },
    };
  } catch {
    return {
      intent: "general",
      reply: normalized || fallbackDecision.reply,
      tool: { name: "none" },
    };
  }
}

function normalizeIntent(intent: unknown): AgentDecision["intent"] {
  if (
    intent === "general" ||
    intent === "services" ||
    intent === "schedule" ||
    intent === "cancel" ||
    intent === "handoff" ||
    intent === "unknown"
  ) {
    return intent;
  }

  return "unknown";
}

function normalizeToolName(name: unknown): NonNullable<AgentDecision["tool"]>["name"] {
  if (
    name === "list_services" ||
    name === "create_appointment" ||
    name === "cancel_appointment" ||
    name === "none"
  ) {
    return name;
  }

  return "none";
}

function formatHistory(messages: ChatMessage[]) {
  return messages
    .slice()
    .reverse()
    .map((message) => ({
      role: message.role,
      content: message.body,
    }));
}

function buildSystemPrompt(tenant: Tenant): string {
  return [
    `Eres Asistto, un asistente de WhatsApp para ${tenant.name}.`,
    "Responde siempre en espanol natural, breve y util.",
    "Debes priorizar cancelaciones antes que crear nuevas citas si el usuario esta continuando una cancelacion.",
    `Zona horaria del negocio: ${tenant.timezone}.`,
    `Duracion normal de cita: ${tenant.appointmentDurationMinutes} minutos.`,
    tenant.services.length
      ? `Servicios disponibles: ${tenant.services.join(", ")}.`
      : "Si el usuario pregunta por servicios y no hay lista, ofrece pedir detalles al negocio.",
    tenant.businessDescription,
    "Devuelve exclusivamente JSON valido con esta forma:",
    '{"reply":"texto para enviar por WhatsApp","intent":"general|services|schedule|cancel|handoff|unknown","tool":{"name":"none|list_services|create_appointment|cancel_appointment","arguments":{}}}',
    "Para agendar usa create_appointment con customerName, serviceName, requestedDateText y notes si existen.",
    "Para cancelar usa cancel_appointment con requestedDateText y notes si existen.",
  ]
    .filter(Boolean)
    .join("\n");
}
