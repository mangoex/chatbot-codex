import asyncio
from app import db
from pprint import pprint

async def main():
    await db.init_pool()
    bots = await db.fetch_all("SELECT bot_id, client_id, name, slug, phone_number_id FROM bots")
    print("BOTS:")
    for b in bots:
        print(dict(b))
    
    knowledge = await db.fetch_all("SELECT id, bot_id, title FROM knowledge_documents")
    print("\nKNOWLEDGE:")
    for k in knowledge:
        print(dict(k))

    skills = await db.fetch_all("SELECT id, bot_id, skill_type, enabled FROM bot_skills")
    print("\nSKILLS:")
    for s in skills:
        print(dict(s))

if __name__ == "__main__":
    asyncio.run(main())
