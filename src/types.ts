export type MessageRole = "user" | "assistant" | "system";
export type MessageDirection = "inbound" | "outbound";

export interface Tenant {
  id: string;
  name: string;
  whatsappPhoneNumberId: string | null;
  displayPhoneNumber: string | null;
  timezone: string;
  appointmentDurationMinutes: number;
  services: string[];
  businessDescription: string;
  active: boolean;
}

export interface Conversation {
  id: string;
  tenantId: string;
  contactWaId: string;
  contactName: string | null;
  lastIntent: AgentIntent | null;
}

export interface ChatMessage {
  id: string;
  tenantId: string;
  conversationId: string;
  waMessageId: string | null;
  direction: MessageDirection;
  role: MessageRole;
  body: string;
  rawPayload?: unknown;
  createdAt: Date;
}

export interface Appointment {
  id: string;
  tenantId: string;
  conversationId: string;
  contactWaId: string;
  customerName: string | null;
  serviceName: string | null;
  requestedDateText: string | null;
  scheduledAt: Date | null;
  durationMinutes: number;
  status: "pending" | "confirmed" | "cancelled";
  notes: string | null;
}

export type AgentIntent =
  | "general"
  | "services"
  | "schedule"
  | "cancel"
  | "handoff"
  | "unknown";

export type ToolName =
  | "none"
  | "list_services"
  | "create_appointment"
  | "cancel_appointment";

export interface AgentToolCall {
  name: ToolName;
  arguments?: Record<string, unknown>;
}

export interface AgentDecision {
  reply: string;
  intent: AgentIntent;
  tool?: AgentToolCall;
}

export interface IncomingWhatsAppMessage {
  messageId: string;
  fromWaId: string;
  contactName: string | null;
  phoneNumberId: string;
  displayPhoneNumber: string | null;
  body: string;
  rawPayload: unknown;
}

export interface Repository {
  findTenantByPhoneNumber(
    phoneNumberId: string,
    displayPhoneNumber: string | null,
  ): Promise<Tenant | null>;
  getOrCreateConversation(input: {
    tenant: Tenant;
    contactWaId: string;
    contactName: string | null;
  }): Promise<Conversation>;
  saveInboundMessage(input: {
    tenant: Tenant;
    conversation: Conversation;
    waMessageId: string;
    body: string;
    rawPayload: unknown;
  }): Promise<boolean>;
  saveOutboundMessage(input: {
    tenant: Tenant;
    conversation: Conversation;
    body: string;
    rawPayload?: unknown;
  }): Promise<void>;
  listRecentMessages(conversationId: string, limit: number): Promise<ChatMessage[]>;
  setConversationIntent(conversationId: string, intent: AgentIntent): Promise<void>;
  createAppointment(input: {
    tenant: Tenant;
    conversation: Conversation;
    contactWaId: string;
    customerName: string | null;
    serviceName: string | null;
    requestedDateText: string | null;
    scheduledAt: Date | null;
    notes: string | null;
  }): Promise<Appointment>;
  cancelLatestAppointment(input: {
    tenant: Tenant;
    conversation: Conversation;
    requestedDateText: string | null;
    notes: string | null;
  }): Promise<Appointment | null>;
}

export interface AgentEngine {
  decide(input: {
    tenant: Tenant;
    conversation: Conversation;
    incomingText: string;
    recentMessages: ChatMessage[];
  }): Promise<AgentDecision>;
}

export interface WhatsAppMessenger {
  sendText(input: {
    phoneNumberId: string;
    to: string;
    body: string;
  }): Promise<unknown>;
}
