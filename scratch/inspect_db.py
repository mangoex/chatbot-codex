import os
import asyncio
import asyncpg

# Parse .env file manually
env_vars = {}
if os.path.exists(".env"):
    with open(".env", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                env_vars[key.strip()] = val.strip().strip('"').strip("'")

DATABASE_URL = env_vars.get("DATABASE_URL") or os.environ.get("DATABASE_URL")
print(f"Connecting to database (length of URL: {len(DATABASE_URL) if DATABASE_URL else 0})...")

async def main():
    if not DATABASE_URL:
        print("Error: DATABASE_URL not found in .env or environment")
        return
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        print("=== BOTS ===")
        bots = await conn.fetch("SELECT id, name, slug, status, openai_model FROM bots")
        for b in bots:
            print(f"Bot ID: {b['id']}, Name: {b['name']}, Slug: {b['slug']}, Status: {b['status']}, Model: {b['openai_model']}")
            
            # Fetch from bot_whatsapp_numbers
            wa = await conn.fetchrow("SELECT phone_number_id, display_phone_number, status, whatsapp_access_token FROM bot_whatsapp_numbers WHERE bot_id = $1", b['id'])
            if wa:
                token_preview = (wa['whatsapp_access_token'][:15] + "...") if wa['whatsapp_access_token'] else "None"
                print(f"  WhatsApp Connection: Phone ID: {wa['phone_number_id']}, Number: {wa['display_phone_number']}, Status: {wa['status']}, Token: {token_preview}")
            else:
                print("  WhatsApp Connection: None")
            
            # Fetch integrations
            integrations = await conn.fetch("SELECT id, name, integration_type, enabled FROM bot_integrations WHERE bot_id = $1", b['id'])
            print(f"  Integrations ({len(integrations)}):")
            for inte in integrations:
                print(f"    - ID: {inte['id']}, Name: {inte['name']}, Type: {inte['integration_type']}, Enabled: {inte['enabled']}")
            
            # Fetch active prompt
            prompt = await conn.fetchrow("SELECT id, status, content FROM bot_prompts WHERE bot_id = $1 AND status = 'active' LIMIT 1", b['id'])
            if prompt:
                print(f"  Active Prompt ID: {prompt['id']}, Length: {len(prompt['content']) if prompt['content'] else 0}")
            else:
                print("  Active Prompt: None")
                
            # Fetch knowledge documents
            docs = await conn.fetch("SELECT id, title, status FROM bot_knowledge WHERE bot_id = $1", b['id'])
            print(f"  Knowledge Docs ({len(docs)}):")
            for d in docs:
                print(f"    - ID: {d['id']}, Title: {d['title']}, Status: {d['status']}")
            print("----------------")
            
        print("\n=== Bot WhatsApp Numbers raw ===")
        all_wa = await conn.fetch("SELECT * FROM bot_whatsapp_numbers")
        for w in all_wa:
            print(dict(w))
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
