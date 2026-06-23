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


def _bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: str) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return int(default)


PORT = int(_env("PORT", default="8000"))
APP_ENV = _env("APP_ENV", "ENVIRONMENT", default="development").lower()
DEFAULT_BOT_SLUG = _env("DEFAULT_BOT_SLUG", default="asistto")

WEBHOOK_DOMAIN = _env("WEBHOOK_DOMAIN", "PUBLIC_BASE_URL")

WHATSAPP_API_TOKEN = _env("WHATSAPP_API_TOKEN", "WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
VERIFY_TOKEN = _env("VERIFY_TOKEN", "WHATSAPP_VERIFY_TOKEN")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
META_APP_ID = os.getenv("META_APP_ID", "")
META_CONFIG_ID = os.getenv("META_CONFIG_ID", "")
META_GRAPH_API_VERSION = os.getenv("META_GRAPH_API_VERSION", "v25.0").strip().lstrip("/")
META_REDIRECT_URI = _env(
    "META_REDIRECT_URI",
    default=f"{WEBHOOK_DOMAIN.rstrip('/')}/admin/meta/oauth/callback" if WEBHOOK_DOMAIN else "",
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
OPENAI_BASE_URL = _env("OPENAI_BASE_URL")
OPENROUTER_SITE_URL = _env("OPENROUTER_SITE_URL", "PUBLIC_BASE_URL")
OPENROUTER_APP_NAME = _env("OPENROUTER_APP_NAME", default="Asistto by Humanio")
OPENAI_TIMEOUT_SECONDS = _int("OPENAI_TIMEOUT_SECONDS", "45")
OPENAI_MAX_TOKENS = _int("OPENAI_MAX_TOKENS", "450")
EMBEDDING_DIMENSIONS = _int("EMBEDDING_DIMENSIONS", "1536")

# Asistente opcional del panel para crear/editar prompts. Si se dejan vacias,
# usa la configuracion global de OpenAI/OpenRouter.
PROMPT_ASSISTANT_PROVIDER = _env("PROMPT_ASSISTANT_PROVIDER", default="openai_compatible")
PROMPT_ASSISTANT_API_KEY = os.getenv("PROMPT_ASSISTANT_API_KEY", "")
PROMPT_ASSISTANT_BASE_URL = _env("PROMPT_ASSISTANT_BASE_URL")
PROMPT_ASSISTANT_MODEL = os.getenv("PROMPT_ASSISTANT_MODEL", "")
PROMPT_ASSISTANT_MAX_TOKENS = _int("PROMPT_ASSISTANT_MAX_TOKENS", "2500")

# Claude / Anthropic opcional para el asistente de prompts.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1").rstrip("/")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")

DATABASE_URL = os.getenv("DATABASE_URL", "")

HISTORY_WINDOW = _int("HISTORY_WINDOW", "10")
MAX_PROMPT_TOKENS = _int("MAX_PROMPT_TOKENS", "6000")
MAX_USER_MESSAGE_CHARS = _int("MAX_USER_MESSAGE_CHARS", "4000")
HISTORY_TTL_DAYS = _int("HISTORY_TTL_DAYS", "30")

RELOAD_TOKEN = os.getenv("RELOAD_TOKEN", "")
ENABLE_FOLLOW_UPS = _bool("ENABLE_FOLLOW_UPS")
FOLLOW_UP_MINUTES = _int("FOLLOW_UP_MINUTES", "10")

ADMIN_USER = os.getenv("ADMIN_USER", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
INTEGRATION_SECRET_KEY = os.getenv("INTEGRATION_SECRET_KEY", "")
KNOWLEDGE_UPLOAD_MAX_BYTES = _int("KNOWLEDGE_UPLOAD_MAX_BYTES", str(10 * 1024 * 1024))
CONTACTS_UPLOAD_MAX_BYTES = _int("CONTACTS_UPLOAD_MAX_BYTES", str(5 * 1024 * 1024))
CAMPAIGN_MAX_RECIPIENTS = _int("CAMPAIGN_MAX_RECIPIENTS", "500")

# URL opcional para leads calificados: agenda, formulario, landing, checkout, etc.
QUALIFIED_CTA_URL = os.getenv("QUALIFIED_CTA_URL", "")

# Google Calendar OAuth. Guardar valores reales solo en Easypanel/.env, nunca en git.
GOOGLE_CALENDAR_ENABLED = _bool("GOOGLE_CALENDAR_ENABLED")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN", "")
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")
GOOGLE_CALENDAR_TIMEZONE = os.getenv("GOOGLE_CALENDAR_TIMEZONE", "America/Chihuahua")
GOOGLE_APPOINTMENT_DURATION_MINUTES = _int("GOOGLE_APPOINTMENT_DURATION_MINUTES", "30")
GOOGLE_APPOINTMENT_BUFFER_MINUTES = _int("GOOGLE_APPOINTMENT_BUFFER_MINUTES", "0")
GOOGLE_APPOINTMENT_SUMMARY_PREFIX = os.getenv(
    "GOOGLE_APPOINTMENT_SUMMARY_PREFIX", "Llamada Asistto"
)
GOOGLE_APPOINTMENT_LOCATION = os.getenv("GOOGLE_APPOINTMENT_LOCATION", "")

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
        "INTEGRATION_SECRET_KEY",
    ):
        if not globals().get(key):
            missing.append(key)

    if GOOGLE_CALENDAR_ENABLED:
        for key in (
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
            "GOOGLE_REFRESH_TOKEN",
            "GOOGLE_CALENDAR_ID",
        ):
            if not globals().get(key):
                missing.append(key)

    return missing
