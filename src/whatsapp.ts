import type { AppConfig } from "./config";
import type { IncomingWhatsAppMessage, WhatsAppMessenger } from "./types";

interface WhatsAppValue {
  metadata?: {
    display_phone_number?: string;
    phone_number_id?: string;
  };
  contacts?: Array<{
    wa_id?: string;
    profile?: {
      name?: string;
    };
  }>;
  messages?: Array<{
    id?: string;
    from?: string;
    type?: string;
    text?: {
      body?: string;
    };
  }>;
}

interface WhatsAppChange {
  value?: WhatsAppValue;
}

interface WhatsAppEntry {
  changes?: WhatsAppChange[];
}

interface WhatsAppWebhookPayload {
  object?: string;
  entry?: WhatsAppEntry[];
}

export function extractIncomingMessages(
  payload: WhatsAppWebhookPayload,
): IncomingWhatsAppMessage[] {
  const incoming: IncomingWhatsAppMessage[] = [];

  for (const entry of payload.entry ?? []) {
    for (const change of entry.changes ?? []) {
      const value = change.value;
      const phoneNumberId = value?.metadata?.phone_number_id;

      if (!value || !phoneNumberId || !value.messages?.length) {
        continue;
      }

      for (const message of value.messages) {
        if (message.type !== "text" || !message.text?.body || !message.from || !message.id) {
          continue;
        }

        const contact = value.contacts?.find((item) => item.wa_id === message.from);

        incoming.push({
          messageId: message.id,
          fromWaId: message.from,
          contactName: contact?.profile?.name ?? null,
          phoneNumberId,
          displayPhoneNumber: value.metadata?.display_phone_number ?? null,
          body: message.text.body.trim(),
          rawPayload: payload,
        });
      }
    }
  }

  return incoming;
}

export class MetaWhatsAppMessenger implements WhatsAppMessenger {
  constructor(private readonly config: AppConfig) {}

  async sendText(input: {
    phoneNumberId: string;
    to: string;
    body: string;
  }): Promise<unknown> {
    if (!this.config.WHATSAPP_ACCESS_TOKEN) {
      throw new Error("WHATSAPP_ACCESS_TOKEN is required to send WhatsApp messages");
    }

    const url = `https://graph.facebook.com/${this.config.WHATSAPP_API_VERSION}/${input.phoneNumberId}/messages`;
    const response = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${this.config.WHATSAPP_ACCESS_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        messaging_product: "whatsapp",
        recipient_type: "individual",
        to: input.to,
        type: "text",
        text: {
          preview_url: false,
          body: input.body,
        },
      }),
    });

    const body = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(`WhatsApp send failed: ${response.status} ${JSON.stringify(body)}`);
    }

    return body;
  }
}
