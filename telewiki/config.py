"""Configuration loading for TeleWiki."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    wiki_lang: str = "en"
    db_path: str = "telewiki.db"
    default_digest_time: str = "08:00"  # HH:MM, UTC
    # Wikimedia's User-Agent policy blocks datacenter IPs without contact
    # info in the UA. Set USER_AGENT to include YOUR contact details.
    user_agent: str = (
        "TeleWiki/0.1 (Telegram bot; contact: telewiki-admin@example.com)"
    )


def load_settings(env_file: str = ".env") -> Settings:
    """Load settings from environment (optionally via a .env file)."""
    load_dotenv(env_file)
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "BOT_TOKEN is not set. Copy .env.example to .env "
            "and add your token from @BotFather."
        )
    return Settings(
        bot_token=token,
        wiki_lang=os.environ.get("WIKI_LANG", "en").strip() or "en",
        db_path=os.environ.get("DB_FILE", "telewiki.db").strip() or "telewiki.db",
        default_digest_time=os.environ.get("DIGEST_TIME", "08:00").strip() or "08:00",
        user_agent=os.environ.get("USER_AGENT", "").strip()
        or Settings.user_agent,
    )
