CREATE TABLE IF NOT EXISTS tenants (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  whatsapp_phone_number_id TEXT UNIQUE,
  display_phone_number TEXT,
  timezone TEXT NOT NULL DEFAULT 'America/Mazatlan',
  appointment_duration_minutes INTEGER NOT NULL DEFAULT 60,
  services TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  business_description TEXT NOT NULL DEFAULT '',
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  contact_wa_id TEXT NOT NULL,
  contact_name TEXT,
  last_intent TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, contact_wa_id)
);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  wa_message_id TEXT UNIQUE,
  direction TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  body TEXT NOT NULL,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS appointments (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  contact_wa_id TEXT NOT NULL,
  customer_name TEXT,
  service_name TEXT,
  requested_date_text TEXT,
  scheduled_at TIMESTAMPTZ,
  duration_minutes INTEGER NOT NULL DEFAULT 60,
  status TEXT NOT NULL CHECK (status IN ('pending', 'confirmed', 'cancelled')),
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
  ON messages (conversation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_appointments_conversation_status
  ON appointments (conversation_id, status, created_at DESC);
