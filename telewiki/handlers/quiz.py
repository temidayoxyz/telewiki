"""/quiz, /score, /leaderboard — solo and group quiz game."""

import datetime
import html
import logging
import random
from dataclasses import dataclass, field

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from telewiki.handlers.wiki import _quiz_topic_key
from telewiki.quiz import Question, decode_answer, encode_answer, new_quiz_id

log = logging.getLogger(__name__)

LETTERS = "ABCD"
OPTION_BUTTON_LEN = 28

# Active (unanswered) quizzes, keyed by (chat_id, message_id).
# In-memory by design: scores persist in SQLite, open rounds do not survive
# a restart (players just start a new round with /quiz).
ACTIVE: dict = {}


@dataclass
class ActiveQuiz:
    quiz_id: str
    question: Question
    is_group: bool
    closed: bool = False
    winner_id: int | None = None


# Continuous quiz sessions: chat_id -> topic (None = mixed topics).
# Private chats only — group quizzes stay one round at a time to avoid spam.
SESSIONS: dict = {}


def start_session(chat_id: int, topic: str | None) -> None:
    SESSIONS[chat_id] = topic


def end_session(chat_id: int) -> bool:
    """End a session. Returns True if one was running."""
    if chat_id in SESSIONS:
        del SESSIONS[chat_id]
        return True
    return False


def in_session(chat_id: int) -> bool:
    return chat_id in SESSIONS


def session_topic(chat_id: int) -> str | None:
    return SESSIONS.get(chat_id)


def _short_option(option: str) -> str:
    return option if len(option) <= OPTION_BUTTON_LEN else option[: OPTION_BUTTON_LEN - 1] + "…"


def format_question_html(question: Question) -> str:
    lines = [f"🧠 <b>Quiz</b>  <i>{html.escape(question.tag)}</i>", "", html.escape(question.text), ""]
    for letter, option in zip(LETTERS, question.options):
        lines.append(f"<b>{letter}.</b> {html.escape(option)}")
    return "\n".join(lines)


def _keyboard(question: Question, quiz_id: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"{letter}) {_short_option(option)}",
                callback_data=encode_answer(quiz_id, i),
            )
        ]
        for i, (letter, option) in enumerate(zip(LETTERS, question.options))
    ]
    return InlineKeyboardMarkup(rows)


def format_reveal_html(
    question: Question,
    correct: bool,
    winner_mention: str | None = None,
    score: dict | None = None,
) -> str:
    icon = "✅" if correct else "❌"
    lines = [
        f"🧠 <b>Quiz</b>  <i>{html.escape(question.tag)}</i>",
        "",
        html.escape(question.text),
        "",
        f"{icon} <b>Correct answer: {html.escape(question.answer)}</b>",
    ]
    if question.explanation:
        lines.append(html.escape(question.explanation))
    if question.source_url:
        lines.append(f'<a href="{question.source_url}">Source on Wikipedia</a>')
    if winner_mention and score is not None:
        lines += [
            "",
            f"🏆 {winner_mention} wins! "
            f"<b>+{score['gained']} pts</b> (total {score['points']}, streak 🔥×{score['streak']})",
            "New round: /quiz",
        ]
    elif score is not None and correct:
        lines += [
            "",
            f"<b>+{score['gained']} pts</b> (total {score['points']}, streak 🔥×{score['streak']})",
            "New round: /quiz",
        ]
    else:
        lines += ["", "New round: /quiz"]
    return "\n".join(lines)


async def send_quiz(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, topic: str | None = None
) -> None:
    """Build and send a quiz question. Falls back to the bank if Wikipedia fails."""
    wiki = context.bot_data["wiki"]
    engine = context.bot_data["engine"]
    events = None
    today = datetime.datetime.now(datetime.timezone.utc)
    try:
        events = await wiki.on_this_day(today.month, today.day)
    except httpx.HTTPError:
        log.warning("on-this-day fetch failed; falling back to question bank", exc_info=True)

    question = engine.next_question(events=events, topic=topic, rng=random.Random())
    quiz_id = new_quiz_id()
    sent = await context.bot.send_message(
        chat_id=chat_id,
        text=format_question_html(question),
        parse_mode=ParseMode.HTML,
        reply_markup=_keyboard(question, quiz_id),
    )
    chat = await context.bot.get_chat(chat_id)
    ACTIVE[(chat_id, sent.message_id)] = ActiveQuiz(
        quiz_id=quiz_id, question=question, is_group=chat.type in ("group", "supergroup")
    )


async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    topic = " ".join(context.args).strip() if context.args else None
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        start_session(chat_id, topic)
    try:
        await send_quiz(context, chat_id, topic=topic)
    except Exception:
        log.exception("failed to send quiz")
        await update.message.reply_text("⚠️ Couldn't start a quiz right now. Try again in a bit.")


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type != "private":
        await update.message.reply_text("Group quizzes are one round at a time — nothing to stop. 🙂")
        return
    if end_session(update.effective_chat.id):
        await update.message.reply_text(
            "⏹️ Quiz session ended. Well played! Send /quiz anytime for a new session."
        )
    else:
        await update.message.reply_text("No quiz session running. Send /quiz to start one!")


async def quiz_me_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """'🎲 Quiz me on this' button from a /wiki result."""
    query = update.callback_query
    topic = context.bot_data.pop(
        _quiz_topic_key(update.effective_chat.id, update.effective_user.id), None
    )
    if not topic:
        await query.answer("That topic expired — search again with /wiki.")
        return
    await query.answer()
    try:
        await send_quiz(context, update.effective_chat.id, topic=topic)
    except Exception:
        log.exception("failed to send quiz from wiki topic")
        await update.effective_message.reply_text(
            "⚠️ Couldn't start a quiz right now. Try again in a bit."
        )


async def quiz_answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    decoded = decode_answer(query.data or "")
    if decoded is None:
        await query.answer()
        return
    quiz_id, index = decoded
    key = (update.effective_chat.id, query.message.message_id)
    active = ACTIVE.get(key)
    if active is None or active.quiz_id != quiz_id:
        await query.answer("This quiz expired (bot restarted?). Send /quiz for a new one.")
        return
    if active.closed:
        await query.answer("Quiz closed — send /quiz for a new round.")
        return
    if not 0 <= index < len(active.question.options):
        await query.answer()
        return

    user = query.from_user
    db = context.bot_data["db"]
    correct = index == active.question.correct_index

    if active.is_group and not correct:
        # Group play: wrong guesses don't reveal or punish — anyone can try.
        await query.answer("❌ Not quite — try again!")
        return

    # Solo play (any first answer locks), or a winning group answer.
    before = db.get_score(user.id, update.effective_chat.id)["points"]
    score = db.record_result(user.id, update.effective_chat.id, correct)
    score["gained"] = score["points"] - before
    active.closed = True
    ACTIVE.pop(key, None)
    if correct:
        active.winner_id = user.id

    await query.answer("✅ Correct!" if correct else "❌ Wrong!")
    winner = user.mention_html() if active.is_group and correct else None
    await query.edit_message_text(
        format_reveal_html(active.question, correct, winner_mention=winner, score=score),
        parse_mode=ParseMode.HTML,
    )

    # Continuous session in private chats: next question follows automatically.
    chat_id = update.effective_chat.id
    if not active.is_group and in_session(chat_id):
        try:
            await send_quiz(context, chat_id, topic=session_topic(chat_id))
        except Exception:
            log.exception("failed to continue quiz session in chat %s", chat_id)


async def score_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    score = context.bot_data["db"].get_score(
        update.effective_user.id, update.effective_chat.id
    )
    accuracy = (
        f"{100 * score['correct'] // score['answered']}%"
        if score["answered"]
        else "—"
    )
    await update.message.reply_text(
        f"🏅 <b>{html.escape(update.effective_user.first_name)}'s score</b>\n\n"
        f"Points: <b>{score['points']}</b>\n"
        f"Correct: {score['correct']}/{score['answered']} ({accuracy})\n"
        f"Streak: 🔥×{score['streak']}",
        parse_mode=ParseMode.HTML,
    )


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = context.bot_data["db"].leaderboard(update.effective_chat.id)
    if not rows:
        await update.message.reply_text("No scores yet — be the first with /quiz!")
        return
    lines = ["🏆 <b>Leaderboard</b>", ""]
    medals = ["🥇", "🥈", "🥉"]
    for i, row in enumerate(rows):
        try:
            member = await context.bot.get_chat_member(update.effective_chat.id, row["user_id"])
            name = member.user.mention_html()
        except Exception:
            name = f"user {row['user_id']}"
        prefix = medals[i] if i < len(medals) else f"{i + 1}."
        lines.append(f"{prefix} {name} — <b>{row['points']}</b> pts")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


def register(app) -> None:
    app.add_handler(CommandHandler("quiz", quiz_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("score", score_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CallbackQueryHandler(quiz_me_callback, pattern=r"^qzm$"))
    app.add_handler(CallbackQueryHandler(quiz_answer_callback, pattern=r"^qz:"))
