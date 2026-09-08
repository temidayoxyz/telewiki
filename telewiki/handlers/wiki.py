"""/wiki command — Wikipedia article lookup with disambiguation handling."""

import html
import logging

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from telewiki.wikipedia import ArticleSummary, format_summary_html

log = logging.getLogger(__name__)

USAGE = "Usage: /wiki <i>topic</i>\nExample: /wiki <i>black holes</i>"
MAX_BUTTON_TITLE = 40


def _search_key(chat_id: int, user_id: int) -> str:
    return f"wikisearch:{chat_id}:{user_id}"


def _quiz_topic_key(chat_id: int, user_id: int) -> str:
    return f"quiztopic:{chat_id}:{user_id}"


def _short(title: str) -> str:
    return title if len(title) <= MAX_BUTTON_TITLE else title[: MAX_BUTTON_TITLE - 1] + "…"


def _buttons(summary: ArticleSummary, alternatives: list) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("🎲 Quiz me on this", callback_data="qzm")]]
    for i, alt in enumerate(alternatives[:4]):
        rows.append([InlineKeyboardButton(f"📖 {_short(alt)}", callback_data=f"wk:{i}")])
    return InlineKeyboardMarkup(rows)


async def _deliver(
    placeholder: Message, summary: ArticleSummary, alternatives: list
) -> Message:
    """Replace the 'searching…' placeholder with the article (photo if available)."""
    markup = _buttons(summary, alternatives)
    if summary.image:
        sent = await placeholder.chat.send_photo(
            photo=summary.image,
            caption=format_summary_html(summary, limit=700)[:1024],
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
        await placeholder.delete()
        return sent
    await placeholder.edit_text(
        format_summary_html(summary),
        parse_mode=ParseMode.HTML,
        reply_markup=markup,
    )
    return placeholder


async def _resolve_title(wiki, title: str):
    """Fetch a summary, returning (summary, error_message)."""
    try:
        summary = await wiki.summary(title)
    except httpx.HTTPError:
        log.warning("Wikipedia summary fetch failed for %r", title, exc_info=True)
        return None, "⚠️ Wikipedia is unreachable right now. Try again in a bit."
    if summary is None:
        return None, "⚠️ I couldn't load that article. Try another one."
    return summary, None


async def wiki_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = " ".join(context.args).strip() if context.args else ""
    if not query:
        await update.message.reply_text(USAGE, parse_mode=ParseMode.HTML)
        return

    wiki = context.bot_data["wiki"]
    placeholder = await update.message.reply_text("🔎 Searching Wikipedia…")

    try:
        results = await wiki.search(query, limit=5)
    except httpx.HTTPError:
        log.warning("Wikipedia search failed for %r", query, exc_info=True)
        await placeholder.edit_text("⚠️ Wikipedia is unreachable right now. Try again in a bit.")
        return

    if not results:
        await placeholder.edit_text(
            f"❌ No Wikipedia articles found for <b>{html.escape(query)}</b>.",
            parse_mode=ParseMode.HTML,
        )
        return

    titles = [r.title for r in results]
    context.bot_data[_search_key(update.effective_chat.id, update.effective_user.id)] = titles

    summary, error = await _resolve_title(wiki, titles[0])
    if error:
        await placeholder.edit_text(error)
        return

    if summary.is_disambiguation:
        await placeholder.edit_text(
            f"🤔 <b>{html.escape(summary.title)}</b> could mean several things — pick one:",
            parse_mode=ParseMode.HTML,
            reply_markup=_buttons(summary, titles[1:]),
        )
        return

    context.bot_data[_quiz_topic_key(update.effective_chat.id, update.effective_user.id)] = (
        summary.title
    )
    await _deliver(placeholder, summary, titles[1:])


async def wiki_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User picked one of the alternative / disambiguation titles."""
    query = update.callback_query
    try:
        index = int(query.data.split(":")[1])
    except (IndexError, ValueError):
        await query.answer()
        return

    titles = context.bot_data.get(
        _search_key(update.effective_chat.id, update.effective_user.id), []
    )
    if not 0 <= index < len(titles):
        await query.answer("That option expired — search again with /wiki.")
        return

    await query.answer()
    summary, error = await _resolve_title(context.bot_data["wiki"], titles[index])
    if error:
        await query.edit_message_text(error)
        return

    context.bot_data[_quiz_topic_key(update.effective_chat.id, update.effective_user.id)] = (
        summary.title
    )
    markup = _buttons(summary, [t for t in titles if t != summary.title])
    text = format_summary_html(summary)
    if query.message.photo:
        await query.edit_message_caption(
            caption=text[:1024], parse_mode=ParseMode.HTML, reply_markup=markup
        )
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


def register(app) -> None:
    app.add_handler(CommandHandler("wiki", wiki_command))
    app.add_handler(CallbackQueryHandler(wiki_choice_callback, pattern=r"^wk:\d+$"))
