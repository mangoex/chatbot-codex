import { createApp } from "./app";
import { OpenRouterAgent } from "./agent";
import { loadConfig } from "./config";
import { logger } from "./logger";
import {
  createPool,
  ensureDefaultTenant,
  PostgresRepository,
  runMigrations,
} from "./repository/postgres";
import { MetaWhatsAppMessenger } from "./whatsapp";

async function main() {
  const config = loadConfig();
  const pool = createPool(config);

  if (config.RUN_MIGRATIONS) {
    await runMigrations(pool);
  }
  await ensureDefaultTenant(pool, config);

  const app = createApp({
    config,
    repository: new PostgresRepository(pool),
    agent: new OpenRouterAgent(config),
    messenger: new MetaWhatsAppMessenger(config),
  });

  app.listen(config.PORT, () => {
    logger.info(
      {
        port: config.PORT,
        service: "asistto-whatsapp-agent",
      },
      "Server listening",
    );
  });
}

main().catch((error) => {
  logger.error({ error }, "Fatal startup error");
  process.exit(1);
});
