"""/digest — daily Wikipedia digest subscriptions per chat."""

import datetime
import html
import logging
import re

import httpx
from telegram import Update
from telegram.constants import ParseMode
from telegram.error import Forbidden
from telegram.ext import CommandHandler, ContextTypes

from telewiki.storage import Subscription
from telewiki.wikipedia import truncate

log = logging.getLogger(__name__)

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
JOB_PREFIX = "digest:"
MAX_EVENTS = 5

HELP = (
    "📰 <b>Digest</b> — a daily Wikipedia briefing in this chat.\n\n"
    "/digest — show status\n"
    "/digest add <i>physics space</i> [HH:MM] — subscribe (UTC)\n"
    "/digest remove <i>space</i> — unsubscribe\n"
    "/digest list — show topics\n"
    "/digest time <i>08:00</i> — set delivery time (UTC)\n"
    "/digest on|off — pause or resume"
)


def job_name(chat_id: int) -> str:
    return f"{JOB_PREFIX}{chat_id}"


def parse_time(value: str) -> datetime.time | None:
    match = TIME_RE.match((value or "").strip())
    if not match:
        return None
    return datetime.time(
        hour=int(match.group(1)), minute=int(match.group(2)), tzinfo=datetime.timezone.utc
    )


def schedule_chat(app, db, chat_id: int) -> bool:
    """(Re)schedule the daily digest job for a chat. Returns True if scheduled."""
    for job in app.job_queue.get_jobs_by_name(job_name(chat_id)):
        job.schedule_removal()
    sub = db.get_subscription(chat_id)
    if not sub or not sub.enabled or not sub.topics:
        return False
    send_time = parse_time(sub.time)
    if send_time is None:
        log.error("chat %s has invalid stored digest time %r", chat_id, sub.time)
        return False
    app.job_queue.run_daily(
        send_digest_job, time=send_time, chat_id=chat_id, name=job_name(chat_id)
    )
    return True


async def send_digest_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = context.job.chat_id
    db = context.bot_data["db"]
    wiki = context.bot_data["wiki"]
    sub = db.get_subscription(chat_id)
    if not sub or not sub.enabled or not sub.topics:
        return

    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        featured = await wiki.featured(now.year, now.month, now.day)
        events = await wiki.on_this_day(now.month, now.day)
    except httpx.HTTPError:
        log.warning("digest fetch failed for chat %s", chat_id, exc_info=True)
        return

    matched = [
        e for e in events if any(t.lower() in (e.text or "").lower() for t in sub.topics)
    ]
    picked = (matched or events)[:MAX_EVENTS]

    lines = [f"📰 <b>Your daily digest</b>  <i>{now:%b %d}</i>", ""]
    if featured and featured.extract:
        lines += [
            f"🌟 <a href=\"{featured.url}\">{html.escape(featured.title)}</a>",
            html.escape(truncate(featured.extract, 400)),
            "",
        ]
    if picked:
        lines.append("📅 <b>On this day</b>")
        for event in picked:
            year = f"{event.year} — " if event.year else ""
            lines.append(f"• {year}{html.escape(truncate(event.text, 200))}")
        lines.append("")
    lines.append(f"Topics: {html.escape(', '.join(sub.topics))} · /digest for settings")

    try:
        await context.bot.send_message(
            chat_id=chat_id, text="\n".join(lines), parse_mode=ParseMode.HTML
        )
    except Forbidden:
        log.info("bot removed/blocked in chat %s; disabling digest", chat_id)
        sub.enabled = False
        db.save_subscription(sub)
        schedule_chat(context.application, db, chat_id)
    except Exception:
        log.exception("failed to deliver digest to chat %s", chat_id)


def _save_and_schedule(context, sub: Subscription) -> bool:
    db = context.bot_data["db"]
    db.save_subscription(sub)
    return schedule_chat(context.application, db, sub.chat_id)


async def digest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    db = context.bot_data["db"]
    default_time = context.bot_data["settings"].default_digest_time
    args = context.args or []

    if not args:
        sub = db.get_subscription(chat_id)
        if not sub or not sub.topics:
            await update.message.reply_text(
                "No digest set up here yet.\n\n" + HELP, parse_mode=ParseMode.HTML
            )
            return
        state = "on 🟢" if sub.enabled else "paused ⏸️"
        await update.message.reply_text(
            f"📰 Digest is <b>{state}</b>\n"
            f"Topics: <b>{html.escape(', '.join(sub.topics))}</b>\n"
            f"Time: <b>{sub.time}</b> UTC\n\n{HELP}",
            parse_mode=ParseMode.HTML,
        )
        return

    action = args[0].lower()
    rest = args[1:]

    if action == "list":
        sub = db.get_subscription(chat_id)
        if not sub or not sub.topics:
            await update.message.reply_text("No topics yet. /digest add <i>physics</i>")
            return
        await update.message.reply_text(
            f"Topics: <b>{html.escape(', '.join(sub.topics))}</b> at <b>{sub.time}</b> UTC",
            parse_mode=ParseMode.HTML,
        )
        return

    if action in ("on", "off"):
        sub = db.get_subscription(chat_id) or Subscription(chat_id, [], default_time, True)
        sub.enabled = action == "on"
        scheduled = _save_and_schedule(context, sub)
        if action == "on" and sub.topics and scheduled:
            await update.message.reply_text(
                f"🟢 Digest resumed — daily at <b>{sub.time}</b> UTC.", parse_mode=ParseMode.HTML
            )
        elif action == "on":
            await update.message.reply_text("🟢 Digest enabled, but no topics yet. /digest add …")
        else:
            await update.message.reply_text("⏸️ Digest paused. /digest on to resume.")
        return

    if action == "time" and len(rest) == 1 and parse_time(rest[0]):
        sub = db.get_subscription(chat_id) or Subscription(chat_id, [], default_time, True)
        sub.time = rest[0].strip()
        scheduled = _save_and_schedule(context, sub)
        extra = "" if scheduled else " (takes effect once you add topics)"
        await update.message.reply_text(
            f"⏰ Digest time set to <b>{sub.time}</b> UTC{extra}.", parse_mode=ParseMode.HTML
        )
        return

    if action in ("add", "remove"):
        topics = [t.lower() for t in rest if not TIME_RE.match(t)]
        time_arg = next((t for t in rest if TIME_RE.match(t)), None)
        if action == "add" and not topics:
            await update.message.reply_text("Usage: /digest add <i>physics space</i> [HH:MM]")
            return
        if action == "remove" and not topics:
            await update.message.reply_text("Usage: /digest remove <i>space</i>")
            return
        sub = db.get_subscription(chat_id) or Subscription(
            chat_id, [], time_arg or default_time, True
        )
        if time_arg:
            sub.time = time_arg
        if action == "add":
            sub.topics = list(dict.fromkeys(sub.topics + [t for t in topics if t not in sub.topics]))
        else:
            sub.topics = [t for t in sub.topics if t not in topics]
        scheduled = _save_and_schedule(context, sub)
        if action == "add":
            await update.message.reply_text(
                f"✅ Subscribed: <b>{html.escape(', '.join(topics))}</b>\n"
                f"Digest arrives daily at <b>{sub.time}</b> UTC"
                + ("" if scheduled else " (paused — /digest on)"),
                parse_mode=ParseMode.HTML,
            )
        else:
            remaining = f"Remaining: <b>{html.escape(', '.join(sub.topics))}</b>" if sub.topics else "No topics left — digest unscheduled."
            await update.message.reply_text(
                f"🗑️ Removed: <b>{html.escape(', '.join(topics))}</b>\n{remaining}",
                parse_mode=ParseMode.HTML,
            )
        return

    await update.message.reply_text(HELP, parse_mode=ParseMode.HTML)


def register(app) -> None:
    app.add_handler(CommandHandler("digest", digest_command))
