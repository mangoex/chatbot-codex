import request from "supertest";
import { describe, expect, it, vi } from "vitest";
import { createApp } from "../src/app";
import type { AppConfig } from "../src/config";
import { MemoryRepository } from "../src/repository/memory";
import type { AgentDecision, AgentEngine, Tenant, WhatsAppMessenger } from "../src/types";

const tenant: Tenant = {
  id: "tenant-1",
  name: "Consultorio Dental Mangoex",
  whatsappPhoneNumberId: "phone-number-1",
  displayPhoneNumber: "5216140000000",
  timezone: "America/Mazatlan",
  appointmentDurationMinutes: 60,
  services: ["Limpieza dental", "Valoracion"],
  businessDescription: "Consultorio dental de prueba.",
  active: true,
};

const config: AppConfig = {
  NODE_ENV: "test",
  PORT: 3000,
  PUBLIC_BASE_URL: "https://bot.example.com",
  DATABASE_URL: "postgres://example",
  WHATSAPP_VERIFY_TOKEN: "verify-me",
  WHATSAPP_ACCESS_TOKEN: "token",
  WHATSAPP_PHONE_NUMBER_ID: "phone-number-1",
  WHATSAPP_API_VERSION: "v25.0",
  OPENROUTER_API_KEY: "or-token",
  OPENROUTER_MODEL: "openai/gpt-4.1-mini",
  OPENROUTER_SITE_URL: "https://bot.example.com",
  OPENROUTER_APP_NAME: "Asistto WhatsApp Agent",
  DEFAULT_TENANT_NAME: tenant.name,
  DEFAULT_TENANT_TIMEZONE: tenant.timezone,
  DEFAULT_TENANT_APPOINTMENT_MINUTES: 60,
  DEFAULT_TENANT_SERVICES: tenant.services,
  RUN_MIGRATIONS: false,
};

function webhookPayload(messageId = "wamid-1", text = "Hola") {
  return {
    object: "whatsapp_business_account",
    entry: [
      {
        changes: [
          {
            value: {
              metadata: {
                display_phone_number: "5216140000000",
                phone_number_id: "phone-number-1",
              },
              contacts: [
                {
                  profile: { name: "Miguel" },
                  wa_id: "5216141111111",
                },
              ],
              messages: [
                {
                  from: "5216141111111",
                  id: messageId,
                  timestamp: "1760000000",
                  text: { body: text },
                  type: "text",
                },
              ],
            },
            field: "messages",
          },
        ],
      },
    ],
  };
}

function createTestApp(decision: AgentDecision) {
  const repository = new MemoryRepository([tenant]);
  const agent: AgentEngine = {
    decide: vi.fn(async () => decision),
  };
  const messenger: WhatsAppMessenger = {
    sendText: vi.fn(async () => ({ messages: [{ id: "outbound-1" }] })),
  };

  return {
    app: createApp({ config, repository, agent, messenger }),
    repository,
    agent,
    messenger,
  };
}

describe("asistto whatsapp api", () => {
  it("returns health status", async () => {
    const { app } = createTestApp({
      intent: "general",
      reply: "Hola",
      tool: { name: "none" },
    });

    await request(app).get("/health").expect(200, {
      ok: true,
      service: "asistto-whatsapp-agent",
    });
  });

  it("verifies Meta webhook challenge", async () => {
    const { app } = createTestApp({
      intent: "general",
      reply: "Hola",
      tool: { name: "none" },
    });

    await request(app)
      .get("/webhooks/whatsapp")
      .query({
        "hub.mode": "subscribe",
        "hub.verify_token": "verify-me",
        "hub.challenge": "abc123",
      })
      .expect(200, "abc123");
  });

  it("rejects invalid webhook verification token", async () => {
    const { app } = createTestApp({
      intent: "general",
      reply: "Hola",
      tool: { name: "none" },
    });

    await request(app)
      .get("/webhooks/whatsapp")
      .query({
        "hub.mode": "subscribe",
        "hub.verify_token": "wrong",
        "hub.challenge": "abc123",
      })
      .expect(403);
  });

  it("handles an inbound WhatsApp text and sends an agent reply", async () => {
    const { app, repository, agent, messenger } = createTestApp({
      intent: "services",
      reply: "Tenemos limpieza dental y valoracion.",
      tool: { name: "list_services", arguments: {} },
    });

    const response = await request(app)
      .post("/webhooks/whatsapp")
      .send(webhookPayload())
      .expect(200);

    expect(response.body.results[0]).toMatchObject({
      ok: true,
      intent: "services",
      tool: "list_services",
    });
    expect(agent.decide).toHaveBeenCalledTimes(1);
    expect(messenger.sendText).toHaveBeenCalledWith({
      phoneNumberId: "phone-number-1",
      to: "5216141111111",
      body: "Tenemos limpieza dental y valoracion.",
    });
    expect(repository.messages.map((message) => message.direction)).toEqual([
      "inbound",
      "outbound",
    ]);
  });

  it("does not process duplicate WhatsApp message ids twice", async () => {
    const { app, agent, messenger } = createTestApp({
      intent: "general",
      reply: "Hola Miguel",
      tool: { name: "none" },
    });

    await request(app).post("/webhooks/whatsapp").send(webhookPayload()).expect(200);
    const duplicate = await request(app)
      .post("/webhooks/whatsapp")
      .send(webhookPayload())
      .expect(200);

    expect(duplicate.body.results[0]).toMatchObject({
      skipped: "duplicate",
    });
    expect(agent.decide).toHaveBeenCalledTimes(1);
    expect(messenger.sendText).toHaveBeenCalledTimes(1);
  });

  it("creates and cancels appointments through tools", async () => {
    const { app, repository } = createTestApp({
      intent: "schedule",
      reply: "Listo, tengo tu solicitud para el viernes a las 10.",
      tool: {
        name: "create_appointment",
        arguments: {
          customerName: "Miguel",
          serviceName: "Limpieza dental",
          requestedDateText: "viernes a las 10",
        },
      },
    });

    await request(app)
      .post("/webhooks/whatsapp")
      .send(webhookPayload("wamid-schedule", "Quiero cita el viernes a las 10"))
      .expect(200);

    expect(repository.appointments).toHaveLength(1);
    expect(repository.appointments[0]?.status).toBe("pending");

    const cancelDecision: AgentDecision = {
      intent: "cancel",
      reply: "Listo, cancele esa cita.",
      tool: {
        name: "cancel_appointment",
        arguments: {
          requestedDateText: "viernes a las 10",
        },
      },
    };
    const cancelAgent: AgentEngine = {
      decide: vi.fn(async () => cancelDecision),
    };

    const cancelApp = createApp({
      config,
      repository,
      agent: cancelAgent,
      messenger: {
        sendText: vi.fn(async () => ({ messages: [{ id: "outbound-2" }] })),
      },
    });

    await request(cancelApp)
      .post("/webhooks/whatsapp")
      .send(webhookPayload("wamid-cancel", "Cancela la del viernes a las 10"))
      .expect(200);

    expect(repository.appointments[0]?.status).toBe("cancelled");
  });
});
