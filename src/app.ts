import express, { type Request, type Response } from "express";
import type { AppConfig } from "./config";
import { logger } from "./logger";
import { executeTool } from "./tools";
import type { AgentEngine, Repository, WhatsAppMessenger } from "./types";
import { extractIncomingMessages } from "./whatsapp";

export interface AppDependencies {
  config: AppConfig;
  repository: Repository;
  agent: AgentEngine;
  messenger: WhatsAppMessenger;
}

export function createApp(deps: AppDependencies) {
  const app = express();

  app.use(express.json({ limit: "2mb" }));

  app.get("/health", (_req, res) => {
    res.status(200).json({
      ok: true,
      service: "asistto-whatsapp-agent",
    });
  });

  app.get("/webhooks/whatsapp", (req: Request, res: Response) => {
    const mode = req.query["hub.mode"];
    const token = req.query["hub.verify_token"];
    const challenge = req.query["hub.challenge"];

    if (
      mode === "subscribe" &&
      typeof token === "string" &&
      token === deps.config.WHATSAPP_VERIFY_TOKEN &&
      typeof challenge === "string"
    ) {
      res.status(200).send(challenge);
      return;
    }

    res.sendStatus(403);
  });

  app.post("/webhooks/whatsapp", async (req: Request, res: Response) => {
    const incomingMessages = extractIncomingMessages(req.body);

    if (!incomingMessages.length) {
      res.status(200).json({ ok: true, ignored: true });
      return;
    }

    const results = [];

    for (const incoming of incomingMessages) {
      try {
        const result = await processIncomingMessage(deps, incoming);
        results.push(result);
      } catch (error) {
        logger.error({ error, messageId: incoming.messageId }, "Webhook processing failed");
        results.push({ messageId: incoming.messageId, ok: false });
      }
    }

    res.status(200).json({ ok: true, results });
  });

  return app;
}

async function processIncomingMessage(
  deps: AppDependencies,
  incoming: ReturnType<typeof extractIncomingMessages>[number],
) {
  const tenant = await deps.repository.findTenantByPhoneNumber(
    incoming.phoneNumberId,
    incoming.displayPhoneNumber,
  );

  if (!tenant) {
    logger.warn(
      {
        phoneNumberId: incoming.phoneNumberId,
        displayPhoneNumber: incoming.displayPhoneNumber,
      },
      "No tenant found for WhatsApp phone number",
    );
    return { messageId: incoming.messageId, ok: true, skipped: "unknown_tenant" };
  }

  const conversation = await deps.repository.getOrCreateConversation({
    tenant,
    contactWaId: incoming.fromWaId,
    contactName: incoming.contactName,
  });

  const inserted = await deps.repository.saveInboundMessage({
    tenant,
    conversation,
    waMessageId: incoming.messageId,
    body: incoming.body,
    rawPayload: incoming.rawPayload,
  });

  if (!inserted) {
    return { messageId: incoming.messageId, ok: true, skipped: "duplicate" };
  }

  const recentMessages = await deps.repository.listRecentMessages(conversation.id, 12);
  const decision = await deps.agent.decide({
    tenant,
    conversation,
    incomingText: incoming.body,
    recentMessages,
  });

  const toolExecution = await executeTool({
    decision,
    tenant,
    conversation,
    contactWaId: incoming.fromWaId,
    repository: deps.repository,
  });

  const whatsappResponse = await deps.messenger.sendText({
    phoneNumberId: incoming.phoneNumberId,
    to: incoming.fromWaId,
    body: toolExecution.reply,
  });

  await deps.repository.saveOutboundMessage({
    tenant,
    conversation,
    body: toolExecution.reply,
    rawPayload: {
      decision,
      toolResult: toolExecution.toolResult,
      whatsappResponse,
    },
  });
  await deps.repository.setConversationIntent(conversation.id, decision.intent);

  return {
    messageId: incoming.messageId,
    ok: true,
    intent: decision.intent,
    tool: decision.tool?.name ?? "none",
  };
}
