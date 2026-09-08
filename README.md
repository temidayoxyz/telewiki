# TeleWiki

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/telegram-bot-blue?logo=telegram)](https://core.telegram.org/bots)

**TeleWiki** is a 3-in-1 Telegram bot that brings Wikipedia into chat:
**article lookup**, **daily digests**, and **quiz games** — for DMs and groups.

Try it: [@tele_wikipedia_bot](https://t.me/tele_wikipedia_bot)

---

## Features

### 📖 Wiki lookup — `/wiki`
Look up any Wikipedia article without leaving Telegram.

```
/wiki black holes
```

Returns a summary with photo (when available), a link to the full article,
buttons for alternative matches, and a **🎲 Quiz me on this** button that
jumps straight into a quiz on the topic. Ambiguous queries show a
disambiguation picker.

### 📰 Digest — `/digest`
A daily Wikipedia briefing delivered to the chat on your topics.

```
/digest add physics space 08:00
```

Each digest contains the featured article of the day plus "On this day"
events matched to your topics. Schedules survive restarts and the
subscription auto-disables if the bot is removed from the chat.

### 🧠 Quiz — `/quiz`
Single and multiplayer trivia generated from Wikipedia content.

```
/quiz
/quiz space
```

- Questions come from daily "On this day" events plus a curated bank
- In **private chats** `/quiz` starts a continuous session — new questions
  keep coming until `/stop`
- In **groups** quizzes are one round at a time: fastest correct answer wins
- Scoring with streak bonuses (`/score`, `/leaderboard`)

---

## Quick start

**Prerequisites:** Python 3.10+, a bot token from
[@BotFather](https://t.me/BotFather).

```bash
git clone https://github.com/temidayoxyz/telewiki.git
cd telewiki
python -m venv .venv
.venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # Windows: copy .env.example .env
# put your token in .env, then:
python main.py
```

Register the commands in [@BotFather](https://t.me/BotFather) with
`/setcommands`:

```
start - Start TeleWiki and see what it can do
help - Full command guide
wiki - Look up a Wikipedia article. Usage: /wiki black holes
quiz - Play a quiz. DM runs a session until /stop
stop - End the current quiz session
score - Your score and streak in this chat
leaderboard - Top players in this chat
digest - Daily Wikipedia briefing. See /digest for setup
```

---

## Commands

| Command | Where | Description |
|---|---|---|
| `/start`, `/help` | anywhere | Welcome message and full guide |
| `/wiki <topic>` | anywhere | Article summary with photo, link and quiz button |
| `/quiz [topic]` | anywhere | Quiz question; continuous session in DMs |
| `/stop` | DMs | End the quiz session |
| `/score` | anywhere | Your points, accuracy and streak in the chat |
| `/leaderboard` | anywhere | Top players in the chat |
| `/digest` | anywhere | Digest status and help |
| `/digest add <topics> [HH:MM]` | anywhere | Subscribe (UTC time, optional) |
| `/digest remove <topics>` | anywhere | Unsubscribe |
| `/digest list` | anywhere | Show topics |
| `/digest time <HH:MM>` | anywhere | Set delivery time (UTC) |
| `/digest on\|off` | anywhere | Pause or resume |

Any non-command text sent in a DM gets a short menu reply. In groups the
bot stays silent on plain text to avoid noise.

---

## Configuration

All settings live in `.env` (see `.env.example`):

| Variable | Required | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | yes | — | Bot token from @BotFather |
| `WIKI_LANG` | no | `en` | Wikipedia language edition |
| `DB_FILE` | no | `telewiki.db` | SQLite database path (auto-created) |
| `DIGEST_TIME` | no | `08:00` | Default digest time, HH:MM UTC |
| `USER_AGENT` | no | TeleWiki default | HTTP User-Agent for Wikimedia APIs |

> **Note:** Wikimedia blocks requests from datacenter IPs whose User-Agent
> has no contact info (HTTP 403). If you host on a VPS/cloud VM, set
> `USER_AGENT` with your real contact details.

---

## Project structure

```
telewiki/
├── main.py                     # Entry point: wiring, scheduling, polling
├── requirements.txt
├── telewiki.service            # systemd unit for VM deployment
├── telewiki/
│   ├── config.py               # Settings from environment
│   ├── storage.py              # SQLite: subscriptions + scores
│   ├── wikipedia.py            # MediaWiki/REST/Feed API client
│   ├── quiz.py                 # Question engine (no network, no Telegram)
│   ├── data/questions.json     # Curated fallback question bank
│   └── handlers/
│       ├── start.py            # /start, /help, DM menu
│       ├── wiki.py             # /wiki + disambiguation buttons
│       ├── quiz.py             # /quiz, /stop, answers, scores
│       └── digest.py           # /digest subscriptions + delivery
└── tests/                      # unittest suite (no network)
```

Design notes:

- **Polling, single process** — fits a small VM; no webhook infra needed.
- **SQLite via stdlib** — zero-dependency persistence; scores and
  subscriptions survive restarts.
- **Digest scheduling** uses the framework's JobQueue; jobs are rehydrated
  from the database on every boot.
- **Quiz engine is pure logic** — question generation is fully unit-tested
  without network access.

---

## Tests

```bash
python -m unittest discover -s tests
```

36 tests covering the quiz engine, Wikipedia response parsing, scoring math
and storage. Handler-level behavior is verified against a live test bot.

---

## Deployment

A `telewiki.service` systemd unit is included for a Linux VM
(e.g. a Google Cloud `e2-micro` instance):

```bash
sudo cp telewiki.service /etc/systemd/system/
sudo systemctl enable --now telewiki
```

The bot idles under 256 MB RAM — comfortably inside free-tier limits.

---

## Roadmap

- Webhook mode for hosting on serverless platforms
- PostgreSQL option for multi-instance deployments
- More quiz generators (Wikidata-backed fact questions)
- Per-user language preferences (`/lang`)
