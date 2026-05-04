import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { Pool } from "pg";
import type { AppConfig } from "../config";
import type {
  AgentIntent,
  Appointment,
  ChatMessage,
  Conversation,
  Repository,
  Tenant,
} from "../types";

export function createPool(config: AppConfig): Pool {
  if (!config.DATABASE_URL) {
    throw new Error("DATABASE_URL is required");
  }

  return new Pool({
    connectionString: config.DATABASE_URL,
  });
}

export async function runMigrations(pool: Pool): Promise<void> {
  const migrationPath = path.join(process.cwd(), "migrations", "001_init.sql");
  const sql = await readFile(migrationPath, "utf8");
  await pool.query(sql);
}

export async function ensureDefaultTenant(
  pool: Pool,
  config: AppConfig,
): Promise<void> {
  if (!config.WHATSAPP_PHONE_NUMBER_ID) {
    return;
  }

  await pool.query(
    `
    INSERT INTO tenants (
      id,
      name,
      whatsapp_phone_number_id,
      timezone,
      appointment_duration_minutes,
      services,
      business_description
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7)
    ON CONFLICT (whatsapp_phone_number_id)
    DO UPDATE SET
      name = EXCLUDED.name,
      timezone = EXCLUDED.timezone,
      appointment_duration_minutes = EXCLUDED.appointment_duration_minutes,
      services = EXCLUDED.services,
      updated_at = NOW()
    `,
    [
      randomUUID(),
      config.DEFAULT_TENANT_NAME,
      config.WHATSAPP_PHONE_NUMBER_ID,
      config.DEFAULT_TENANT_TIMEZONE,
      config.DEFAULT_TENANT_APPOINTMENT_MINUTES,
      config.DEFAULT_TENANT_SERVICES,
      "Asistente dental por WhatsApp para informacion, agenda y cancelacion de citas.",
    ],
  );
}

export class PostgresRepository implements Repository {
  constructor(private readonly pool: Pool) {}

  async findTenantByPhoneNumber(
    phoneNumberId: string,
    displayPhoneNumber: string | null,
  ): Promise<Tenant | null> {
    const result = await this.pool.query(
      `
      SELECT *
      FROM tenants
      WHERE active = TRUE
        AND (
          whatsapp_phone_number_id = $1
          OR ($2::TEXT IS NOT NULL AND display_phone_number = $2)
        )
      LIMIT 1
      `,
      [phoneNumberId, displayPhoneNumber],
    );

    return result.rows[0] ? mapTenant(result.rows[0]) : null;
  }

  async getOrCreateConversation(input: {
    tenant: Tenant;
    contactWaId: string;
    contactName: string | null;
  }): Promise<Conversation> {
    const id = randomUUID();
    const result = await this.pool.query(
      `
      INSERT INTO conversations (id, tenant_id, contact_wa_id, contact_name)
      VALUES ($1, $2, $3, $4)
      ON CONFLICT (tenant_id, contact_wa_id)
      DO UPDATE SET
        contact_name = COALESCE(EXCLUDED.contact_name, conversations.contact_name),
        updated_at = NOW()
      RETURNING *
      `,
      [id, input.tenant.id, input.contactWaId, input.contactName],
    );

    return mapConversation(result.rows[0]);
  }

  async saveInboundMessage(input: {
    tenant: Tenant;
    conversation: Conversation;
    waMessageId: string;
    body: string;
    rawPayload: unknown;
  }): Promise<boolean> {
    const result = await this.pool.query(
      `
      INSERT INTO messages (
        id,
        tenant_id,
        conversation_id,
        wa_message_id,
        direction,
        role,
        body,
        raw_payload
      )
      VALUES ($1, $2, $3, $4, 'inbound', 'user', $5, $6)
      ON CONFLICT (wa_message_id) DO NOTHING
      RETURNING id
      `,
      [
        randomUUID(),
        input.tenant.id,
        input.conversation.id,
        input.waMessageId,
        input.body,
        JSON.stringify(input.rawPayload),
      ],
    );

    return result.rowCount === 1;
  }

  async saveOutboundMessage(input: {
    tenant: Tenant;
    conversation: Conversation;
    body: string;
    rawPayload?: unknown;
  }): Promise<void> {
    await this.pool.query(
      `
      INSERT INTO messages (
        id,
        tenant_id,
        conversation_id,
        wa_message_id,
        direction,
        role,
        body,
        raw_payload
      )
      VALUES ($1, $2, $3, NULL, 'outbound', 'assistant', $4, $5)
      `,
      [
        randomUUID(),
        input.tenant.id,
        input.conversation.id,
        input.body,
        input.rawPayload ? JSON.stringify(input.rawPayload) : null,
      ],
    );
  }

  async listRecentMessages(conversationId: string, limit: number): Promise<ChatMessage[]> {
    const result = await this.pool.query(
      `
      SELECT *
      FROM messages
      WHERE conversation_id = $1
      ORDER BY created_at DESC
      LIMIT $2
      `,
      [conversationId, limit],
    );

    return result.rows.map(mapChatMessage);
  }

  async setConversationIntent(
    conversationId: string,
    intent: AgentIntent,
  ): Promise<void> {
    await this.pool.query(
      `
      UPDATE conversations
      SET last_intent = $2, updated_at = NOW()
      WHERE id = $1
      `,
      [conversationId, intent],
    );
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
    const result = await this.pool.query(
      `
      INSERT INTO appointments (
        id,
        tenant_id,
        conversation_id,
        contact_wa_id,
        customer_name,
        service_name,
        requested_date_text,
        scheduled_at,
        duration_minutes,
        status,
        notes
      )
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'pending', $10)
      RETURNING *
      `,
      [
        randomUUID(),
        input.tenant.id,
        input.conversation.id,
        input.contactWaId,
        input.customerName,
        input.serviceName,
        input.requestedDateText,
        input.scheduledAt,
        input.tenant.appointmentDurationMinutes,
        input.notes,
      ],
    );

    return mapAppointment(result.rows[0]);
  }

  async cancelLatestAppointment(input: {
    tenant: Tenant;
    conversation: Conversation;
    requestedDateText: string | null;
    notes: string | null;
  }): Promise<Appointment | null> {
    const result = await this.pool.query(
      `
      WITH candidate AS (
        SELECT id
        FROM appointments
        WHERE tenant_id = $1
          AND conversation_id = $2
          AND status IN ('pending', 'confirmed')
          AND (
            $3::TEXT IS NULL
            OR requested_date_text ILIKE '%' || $3 || '%'
            OR notes ILIKE '%' || $3 || '%'
          )
        ORDER BY created_at DESC
        LIMIT 1
      )
      UPDATE appointments
      SET status = 'cancelled',
          notes = COALESCE($4, notes),
          updated_at = NOW()
      WHERE id IN (SELECT id FROM candidate)
      RETURNING *
      `,
      [input.tenant.id, input.conversation.id, input.requestedDateText, input.notes],
    );

    return result.rows[0] ? mapAppointment(result.rows[0]) : null;
  }
}

function mapTenant(row: Record<string, unknown>): Tenant {
  return {
    id: String(row.id),
    name: String(row.name),
    whatsappPhoneNumberId: nullableString(row.whatsapp_phone_number_id),
    displayPhoneNumber: nullableString(row.display_phone_number),
    timezone: String(row.timezone),
    appointmentDurationMinutes: Number(row.appointment_duration_minutes),
    services: Array.isArray(row.services) ? row.services.map(String) : [],
    businessDescription: String(row.business_description ?? ""),
    active: Boolean(row.active),
  };
}

function mapConversation(row: Record<string, unknown>): Conversation {
  return {
    id: String(row.id),
    tenantId: String(row.tenant_id),
    contactWaId: String(row.contact_wa_id),
    contactName: nullableString(row.contact_name),
    lastIntent: nullableString(row.last_intent) as AgentIntent | null,
  };
}

function mapChatMessage(row: Record<string, unknown>): ChatMessage {
  return {
    id: String(row.id),
    tenantId: String(row.tenant_id),
    conversationId: String(row.conversation_id),
    waMessageId: nullableString(row.wa_message_id),
    direction: row.direction === "inbound" ? "inbound" : "outbound",
    role:
      row.role === "assistant" || row.role === "system"
        ? row.role
        : "user",
    body: String(row.body),
    rawPayload: row.raw_payload,
    createdAt: new Date(String(row.created_at)),
  };
}

function mapAppointment(row: Record<string, unknown>): Appointment {
  return {
    id: String(row.id),
    tenantId: String(row.tenant_id),
    conversationId: String(row.conversation_id),
    contactWaId: String(row.contact_wa_id),
    customerName: nullableString(row.customer_name),
    serviceName: nullableString(row.service_name),
    requestedDateText: nullableString(row.requested_date_text),
    scheduledAt: row.scheduled_at ? new Date(String(row.scheduled_at)) : null,
    durationMinutes: Number(row.duration_minutes),
    status:
      row.status === "confirmed" || row.status === "cancelled"
        ? row.status
        : "pending",
    notes: nullableString(row.notes),
  };
}

function nullableString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}
