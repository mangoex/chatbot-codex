import { randomUUID } from "node:crypto";
import type {
  AgentIntent,
  Appointment,
  ChatMessage,
  Conversation,
  Repository,
  Tenant,
} from "../types";

export class MemoryRepository implements Repository {
  readonly tenants = new Map<string, Tenant>();
  readonly conversations = new Map<string, Conversation>();
  readonly messages: ChatMessage[] = [];
  readonly appointments: Appointment[] = [];

  constructor(initialTenants: Tenant[]) {
    for (const tenant of initialTenants) {
      this.tenants.set(tenant.id, tenant);
    }
  }

  async findTenantByPhoneNumber(
    phoneNumberId: string,
    displayPhoneNumber: string | null,
  ): Promise<Tenant | null> {
    return (
      [...this.tenants.values()].find(
        (tenant) =>
          tenant.whatsappPhoneNumberId === phoneNumberId ||
          (displayPhoneNumber && tenant.displayPhoneNumber === displayPhoneNumber),
      ) ?? null
    );
  }

  async getOrCreateConversation(input: {
    tenant: Tenant;
    contactWaId: string;
    contactName: string | null;
  }): Promise<Conversation> {
    const existing = [...this.conversations.values()].find(
      (conversation) =>
        conversation.tenantId === input.tenant.id &&
        conversation.contactWaId === input.contactWaId,
    );

    if (existing) {
      return existing;
    }

    const conversation: Conversation = {
      id: randomUUID(),
      tenantId: input.tenant.id,
      contactWaId: input.contactWaId,
      contactName: input.contactName,
      lastIntent: null,
    };
    this.conversations.set(conversation.id, conversation);
    return conversation;
  }

  async saveInboundMessage(input: {
    tenant: Tenant;
    conversation: Conversation;
    waMessageId: string;
    body: string;
    rawPayload: unknown;
  }): Promise<boolean> {
    if (this.messages.some((message) => message.waMessageId === input.waMessageId)) {
      return false;
    }

    this.messages.push({
      id: randomUUID(),
      tenantId: input.tenant.id,
      conversationId: input.conversation.id,
      waMessageId: input.waMessageId,
      direction: "inbound",
      role: "user",
      body: input.body,
      rawPayload: input.rawPayload,
      createdAt: new Date(),
    });
    return true;
  }

  async saveOutboundMessage(input: {
    tenant: Tenant;
    conversation: Conversation;
    body: string;
    rawPayload?: unknown;
  }): Promise<void> {
    this.messages.push({
      id: randomUUID(),
      tenantId: input.tenant.id,
      conversationId: input.conversation.id,
      waMessageId: null,
      direction: "outbound",
      role: "assistant",
      body: input.body,
      rawPayload: input.rawPayload,
      createdAt: new Date(),
    });
  }

  async listRecentMessages(conversationId: string, limit: number): Promise<ChatMessage[]> {
    return this.messages
      .filter((message) => message.conversationId === conversationId)
      .slice(-limit)
      .reverse();
  }

  async setConversationIntent(
    conversationId: string,
    intent: AgentIntent,
  ): Promise<void> {
    const conversation = this.conversations.get(conversationId);
    if (conversation) {
      conversation.lastIntent = intent;
    }
  }

  async createAppointment(input: {
    tenant: Tenant;
    conversation: Conversation;
    contactWaId: string;
    customerName: string | null;
    serviceName: string | null;
    requestedDateText: string | null;
    scheduledAt: Date | null;
    notes: string | null;
  }): Promise<Appointment> {
    const appointment: Appointment = {
      id: randomUUID(),
      tenantId: input.tenant.id,
      conversationId: input.conversation.id,
      contactWaId: input.contactWaId,
      customerName: input.customerName,
      serviceName: input.serviceName,
      requestedDateText: input.requestedDateText,
      scheduledAt: input.scheduledAt,
      durationMinutes: input.tenant.appointmentDurationMinutes,
      status: "pending",
      notes: input.notes,
    };
    this.appointments.push(appointment);
    return appointment;
  }

  async cancelLatestAppointment(input: {
    tenant: Tenant;
    conversation: Conversation;
    requestedDateText: string | null;
    notes: string | null;
  }): Promise<Appointment | null> {
    const candidate = this.appointments
      .filter(
        (appointment) =>
          appointment.tenantId === input.tenant.id &&
          appointment.conversationId === input.conversation.id &&
          appointment.status !== "cancelled" &&
          (!input.requestedDateText ||
            appointment.requestedDateText
              ?.toLowerCase()
              .includes(input.requestedDateText.toLowerCase()) ||
            appointment.notes
              ?.toLowerCase()
              .includes(input.requestedDateText.toLowerCase())),
      )
      .at(-1);

    if (!candidate) {
      return null;
    }

    candidate.status = "cancelled";
    candidate.notes = input.notes ?? candidate.notes;
    return candidate;
  }
}
