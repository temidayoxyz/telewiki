"""/start and /help commands."""

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

START_TEXT = (
    "👋 Welcome to <b>TeleWiki</b> — Wikipedia on Telegram.\n\n"
    "What I can do:\n"
    "📖 <b>/wiki</b> <i>topic</i> — look up any Wikipedia article\n"
    "📰 <b>/digest</b> — get a daily Wikipedia digest on your topics\n"
    "🧠 <b>/quiz</b> <i>[topic]</i> — test your knowledge, solo or in groups\n\n"
    "Use /help for full command details."
)

HELP_TEXT = (
    "📖 <b>Wiki lookup</b>\n"
    "/wiki <i>black holes</i> — article summary with a link and photo\n\n"
    "📰 <b>Digest</b>\n"
    "/digest — show status and help\n"
    "/digest add <i>physics space</i> [HH:MM] — subscribe (UTC time, optional)\n"
    "/digest remove <i>space</i> — unsubscribe from topics\n"
    "/digest list — show your topics\n"
    "/digest time <i>08:00</i> — set delivery time (UTC)\n"
    "/digest on|off — pause or resume\n\n"
    "🧠 <b>Quiz</b>\n"
    "/quiz — random question\n"
    "/quiz <i>space</i> — question on a topic\n"
    "In a private chat /quiz starts a <b>session</b>: new questions keep\n"
    "coming after each answer until you send /stop.\n"
    "/stop — end the quiz session\n"
    "/score — your score in this chat\n"
    "/leaderboard — top players in this chat\n\n"
    "In groups the fastest correct answer wins. Streaks earn bonus points. 🔥"
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(START_TEXT, parse_mode=ParseMode.HTML)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


MENU_TEXT = (
    "👋 Hi! I'm <b>TeleWiki</b> — Wikipedia on Telegram.\n\n"
    "📖 /wiki <i>topic</i> — look up an article\n"
    "📰 /digest — daily briefing on your topics\n"
    "🧠 /quiz — play a quiz\n\n"
    "Send /help for full details."
)


async def text_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply to plain (non-command) text with a menu — private chats only,
    so the bot never spams groups."""
    if update.effective_chat.type != "private":
        return
    await update.message.reply_text(MENU_TEXT, parse_mode=ParseMode.HTML)


def register(app) -> None:
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_menu))
