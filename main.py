"""TeleWiki entry point — polling bot for a single VM."""

import logging
from pathlib import Path

from telegram import Update
from telegram.ext import Application

from telewiki.config import load_settings
from telewiki.handlers import register_all
from telewiki.handlers.digest import schedule_chat
from telewiki.quiz import QuizEngine, load_bank
from telewiki.storage import Database
from telewiki.wikipedia import WikipediaClient

log = logging.getLogger("telewiki")

BANK_PATH = Path(__file__).resolve().parent / "telewiki" / "data" / "questions.json"


async def post_init(app: Application) -> None:
    """Rehydrate digest schedules from the database on every boot."""
    db: Database = app.bot_data["db"]
    subs = db.list_subscriptions(enabled_only=True)
    count = sum(1 for sub in subs if schedule_chat(app, db, sub.chat_id))
    me = await app.bot.get_me()
    log.info("TeleWiki started as @%s — %d digest job(s) scheduled", me.username, count)


async def post_shutdown(app: Application) -> None:
    await app.bot_data["wiki"].aclose()
    app.bot_data["db"].close()


async def on_error(update: Update, context) -> None:
    log.exception("unhandled error while processing update %r", update)


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
    )
    settings = load_settings()
    db = Database(settings.db_path)
    wiki = WikipediaClient(lang=settings.wiki_lang, user_agent=settings.user_agent)
    engine = QuizEngine(load_bank(str(BANK_PATH)))

    app = (
        Application.builder()
        .token(settings.bot_token)
        .connect_timeout(20.0)
        .read_timeout(30.0)
        .write_timeout(20.0)
        .pool_timeout(10.0)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.bot_data.update(
        {"settings": settings, "db": db, "wiki": wiki, "engine": engine}
    )
    register_all(app)
    app.add_error_handler(on_error)
    app.run_polling(allowed_updates=Update.ALL_TYPES, timeout=30)


if __name__ == "__main__":
    main()
