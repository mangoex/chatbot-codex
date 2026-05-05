"""Carga de variables de entorno y prompts desde disco."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return default


PORT = int(_env("PORT", default="8000"))

WEBHOOK_DOMAIN = _env("WEBHOOK_DOMAIN", "PUBLIC_BASE_URL")

WHATSAPP_API_TOKEN = _env("WHATSAPP_API_TOKEN", "WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
VERIFY_TOKEN = _env("VERIFY_TOKEN", "WHATSAPP_VERIFY_TOKEN")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
OPENAI_BASE_URL = _env("OPENAI_BASE_URL")
OPENROUTER_SITE_URL = _env("OPENROUTER_SITE_URL", "PUBLIC_BASE_URL")
OPENROUTER_APP_NAME = _env("OPENROUTER_APP_NAME", default="WhatsApp Bot")

DATABASE_URL = os.getenv("DATABASE_URL", "")

HISTORY_WINDOW = int(os.getenv("HISTORY_WINDOW", "10"))
MAX_PROMPT_TOKENS = int(os.getenv("MAX_PROMPT_TOKENS", "6000"))
MAX_USER_MESSAGE_CHARS = int(os.getenv("MAX_USER_MESSAGE_CHARS", "4000"))
HISTORY_TTL_DAYS = int(os.getenv("HISTORY_TTL_DAYS", "30"))

RELOAD_TOKEN = os.getenv("RELOAD_TOKEN", "")
ENABLE_FOLLOW_UPS = os.getenv("ENABLE_FOLLOW_UPS", "false").strip().lower() in {
    "1", "true", "yes", "on"
}
FOLLOW_UP_MINUTES = int(os.getenv("FOLLOW_UP_MINUTES", "10"))

ADMIN_USER = os.getenv("ADMIN_USER", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "")

# URL opcional para leads calificados: agenda, formulario, landing, checkout, etc.
QUALIFIED_CTA_URL = os.getenv("QUALIFIED_CTA_URL", "")

PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR", "prompts"))

SYSTEM_PROMPT: str = ""

FALLBACK_PROMPT = (
    "Eres un asistente util y conciso de atencion al cliente por WhatsApp. "
    "Responde en el mismo idioma que el usuario. Se breve y directo."
)


def load_prompts() -> str:
    """Lee prompts/system.md + prompts/knowledge/*.md y construye el system prompt."""
    global SYSTEM_PROMPT

    system_file = PROMPTS_DIR / "system.md"
    if system_file.exists():
        base = system_file.read_text(encoding="utf-8").strip()
    else:
        base = FALLBACK_PROMPT

    knowledge_dir = PROMPTS_DIR / "knowledge"
    extras: list[str] = []
    if knowledge_dir.is_dir():
        for md in sorted(knowledge_dir.glob("*.md")):
            content = md.read_text(encoding="utf-8").strip()
            if content:
                extras.append(f"--- {md.name} ---\n{content}")
        for txt in sorted(knowledge_dir.glob("*.txt")):
            content = txt.read_text(encoding="utf-8").strip()
            if content:
                extras.append(f"--- {txt.name} ---\n{content}")

    SYSTEM_PROMPT = base + ("\n\n" + "\n\n".join(extras) if extras else "")
    return SYSTEM_PROMPT


def validate() -> list[str]:
    """Devuelve lista de errores de configuracion (vacia = OK)."""
    missing = []
    for key in (
        "WHATSAPP_API_TOKEN",
        "WHATSAPP_PHONE_NUMBER_ID",
        "VERIFY_TOKEN",
        "OPENAI_API_KEY",
        "DATABASE_URL",
        "ADMIN_USER",
        "ADMIN_PASSWORD",
        "SESSION_SECRET",
    ):
        if not globals().get(key):
            missing.append(key)
    return missing
