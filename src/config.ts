import { z } from "zod";

const envSchema = z.object({
  NODE_ENV: z
    .enum(["development", "test", "production"])
    .default("development"),
  PORT: z.coerce.number().int().positive().default(3000),
  PUBLIC_BASE_URL: z.string().url().optional(),
  DATABASE_URL: z.string().min(1).optional(),
  WHATSAPP_VERIFY_TOKEN: z.string().min(1).optional(),
  WHATSAPP_ACCESS_TOKEN: z.string().min(1).optional(),
  WHATSAPP_PHONE_NUMBER_ID: z.string().min(1).optional(),
  WHATSAPP_API_VERSION: z.string().min(1).default("v25.0"),
  OPENROUTER_API_KEY: z.string().min(1).optional(),
  OPENROUTER_MODEL: z.string().min(1).default("openai/gpt-4.1-mini"),
  OPENROUTER_SITE_URL: z.string().url().optional(),
  OPENROUTER_APP_NAME: z.string().min(1).default("Asistto WhatsApp Agent"),
  DEFAULT_TENANT_NAME: z.string().min(1).default("Consultorio Dental Mangoex"),
  DEFAULT_TENANT_TIMEZONE: z.string().min(1).default("America/Mazatlan"),
  DEFAULT_TENANT_APPOINTMENT_MINUTES: z.coerce.number().int().positive().default(60),
  DEFAULT_TENANT_SERVICES: z
    .string()
    .default("Limpieza dental, Valoracion, Ortodoncia, Blanqueamiento"),
  RUN_MIGRATIONS: z
    .enum(["true", "false"])
    .default("true")
    .transform((value) => value === "true"),
});

export type AppConfig = ReturnType<typeof loadConfig>;

export function loadConfig(env: NodeJS.ProcessEnv = process.env) {
  const parsed = envSchema.parse(env);

  return {
    ...parsed,
    DEFAULT_TENANT_SERVICES: parsed.DEFAULT_TENANT_SERVICES.split(",")
      .map((service) => service.trim())
      .filter(Boolean),
  };
}
