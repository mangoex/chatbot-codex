import sys
import types
# Mock dotenv module
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
            print("=== BOTS ===")
            bots = await conn.fetch("SELECT id, name, slug FROM bots")
            for b in bots:
                print(f"Bot ID: {b['id']}, Name: {b['name']}, Slug: {b['slug']}")
            
            print("\n=== BOT WHATSAPP NUMBERS ===")
            numbers = await conn.fetch("SELECT id, bot_id, phone_number_id, display_phone_number, status, business_id, waba_id FROM bot_whatsapp_numbers")
            for n in numbers:
                print(f"ID: {n['id']}, Bot ID: {n['bot_id']}, Phone ID: {n['phone_number_id']}, Display: {n['display_phone_number']}, Status: {n['status']}, Business: {n['business_id']}, WABA: {n['waba_id']}")
                
            print("\n=== BOT INTEGRATIONS ===")
            integrations = await conn.fetch("SELECT id, bot_id, integration_type, name, enabled FROM bot_integrations")
            for i in integrations:
                print(f"ID: {i['id']}, Bot ID: {i['bot_id']}, Type: {i['integration_type']}, Name: {i['name']}, Enabled: {i['enabled']}")
                
            print("\n=== LEADS ===")
            leads = await conn.fetch("SELECT id, bot_id, wa_id, nombre, qualification_status FROM leads ORDER BY id DESC LIMIT 10")
            for l in leads:
                print(f"ID: {l['id']}, Bot ID: {l['bot_id']}, WA ID: {l['wa_id']}, Name: {l['nombre']}, Status: {l['qualification_status']}")
                
            print("\n=== CONVERSATIONS (LAST 10) ===")
            convs = await conn.fetch("SELECT id, bot_id, wa_id, role, content, created_at FROM conversations ORDER BY id DESC LIMIT 10")
            for c in convs:
                print(f"ID: {c['id']}, Bot ID: {c['bot_id']}, WA ID: {c['wa_id']}, Role: {c['role']}, Content: {c['content']}, Date: {c['created_at']}")
                
            print("\n=== ESCALATIONS ===")
            escalations = await conn.fetch("SELECT id, bot_id, wa_id, status, reason FROM escalations ORDER BY id DESC LIMIT 10")
            for e in escalations:
                print(f"ID: {e['id']}, Bot ID: {e['bot_id']}, WA ID: {e['wa_id']}, Status: {e['status']}, Reason: {e['reason']}")
    finally:
        await db.close_pool()

if __name__ == "__main__":
    asyncio.run(main())
