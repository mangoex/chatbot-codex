import sys
import types
# Mock dotenv module to prevent import errors in config.py
sys.modules['dotenv'] = types.SimpleNamespace(load_dotenv=lambda: None)

import os
import asyncio

# Parse .env file manually
if os.path.exists(".env"):
    with open(".env", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip().strip('"').strip("'")

from app import db

async def main():
    await db.init_pool()
    try:
        async with db._pool.acquire() as conn:
            bots = await conn.fetch("SELECT id, name, slug FROM bots")
            print("=== BOTS ===")
            for b in bots:
                print(f"Bot ID: {b['id']}, Name: {b['name']}, Slug: {b['slug']}")
                
                # Fetch whatsapp connection
                wa = await conn.fetchrow("SELECT phone_number_id, display_phone_number, sync_status FROM bot_whatsapp_connections WHERE bot_id = $1", b['id'])
                if wa:
                    print(f"WhatsApp Connection: Phone ID: {wa['phone_number_id']}, Number: {wa['display_phone_number']}, Status: {wa['sync_status']}")
                else:
                    print("WhatsApp Connection: None")
                print("----------------")
            print("=========================================\n")
    finally:
        await db.close_pool()

if __name__ == "__main__":
    asyncio.run(main())
