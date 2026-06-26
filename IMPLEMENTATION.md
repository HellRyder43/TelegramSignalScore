# IMPLEMENTATION.md — Your Setup Runbook (Human Tasks)

> **What this file is:** everything **you** need to set up by hand before Claude Code can build and run the system. Accounts, credentials, installs, and config — not code. Claude Code reads `CLAUDE.md` and writes the software; this file makes sure the environment it runs in is ready.
>
> **Your environment:** Windows machine, MT5 always running, everything (pipeline + dashboard) runs locally. Telegram via your main account. Discord built from scratch (explained below).
>
> Work top to bottom. Each section ends with a ✅ check so you know it's done. Keep every secret you collect in one scratch note for now — you'll paste them into a `.env` file at the end.

---

## Setup checklist (overview)

1. [ ] Install the base tools (Python, Node, Git, code editor)
2. [ ] Install & configure MetaTrader 5, confirm your XAUUSD symbol name
3. [ ] Get your Telegram API credentials (api_id + api_hash)
4. [ ] Identify the Telegram channels you want to track
5. [ ] Create a Discord server, app, and bot — get the token + channel ID
6. [ ] Get an Anthropic API key (for image/vision parsing)
7. [ ] Collect all secrets into one place for the `.env`
8. [ ] Decide on keeping it running 24/7
9. [ ] Hand off to Claude Code

---

## 1. Base tools

Install these first. All free.

| Tool | Why | Where |
|---|---|---|
| **Python 3.11+** | Runs the whole backend pipeline | python.org/downloads — during install, **tick "Add Python to PATH"** |
| **Node.js 20 LTS** | Runs the Next.js dashboard | nodejs.org — take the LTS installer |
| **Git** | Version control / Claude Code works with it | git-scm.com |
| **VS Code** | Editor + where you'll run Claude Code | code.visualstudio.com |

**Verify each install** — open a new PowerShell window and run:
```
python --version
node --version
git --version
```
Each should print a version number. If `python` says "not found," reinstall and make sure the **Add to PATH** box was ticked.

✅ **Check:** all three commands print versions.

---

## 2. MetaTrader 5 (your price source)

The system verifies every signal against real XAUUSD candles pulled from **your** MT5 terminal. This only works on Windows with MT5 installed, running, and logged in.

### 2a. Install & log in
1. Install MT5 from your broker (you already trade XAUUSD on **RoboForex** — use their MT5 build so the price feed matches what you trade).
2. Log into your account (demo or live — either works for price data).
3. Leave it running and logged in. If MT5 is closed, the system can't verify anything.

### 2b. Find your exact gold symbol name — **important**
Brokers name gold differently (`XAUUSD`, `XAUUSD.r`, `GOLD`, `XAUUSDm`...). You must give the system the **exact** name your broker uses.
1. In MT5, open **Market Watch** (Ctrl+M).
2. Right-click → **Symbols** (or **Show All**) to reveal everything.
3. Find gold and note the **exact** spelling, including any suffix. Example: `XAUUSD.r`.
4. Write it down — this becomes `MT5_SYMBOL` in your `.env`.

### 2c. Make sure history is available
1. In Market Watch, right-click gold → **Chart Window**.
2. Set the timeframe to **M1** (1-minute).
3. Scroll back a few days so the terminal downloads history. The more it caches, the more past signals can be verified.

✅ **Check:** MT5 is logged in, you know your exact gold symbol name, and an M1 gold chart shows recent candles.

> Note: verification uses *your* broker's feed by design — it reflects the prices you'd actually trade. A signal may "win" on another broker and "lose" on yours; that's expected, not a bug.

---

## 3. Telegram API credentials

The system logs into Telegram **as you** (a "user client") so it can read the channels you've joined and — critically — catch when messages are **edited or deleted** (the anti-fraud signal). This requires a personal `api_id` + `api_hash`.

### Steps
1. Go to **https://my.telegram.org** in a browser.
2. Enter the **phone number of your main Telegram account** (with country code, e.g. +60…). Click **Next**.
3. Telegram sends a **login code** to your Telegram app on your phone. Enter it on the website to sign in.
4. Click **API development tools**.
5. Fill in the **Create new application** form:
   - **App title:** anything (e.g. `XAU Trust Monitor`)
   - **Short name:** anything 5–32 chars, no spaces (e.g. `xautrust`)
   - **URL / platform / description:** can be left blank or filled with anything; platform "Desktop" is fine.
6. Click **Create application**.
7. You'll land on a page showing **App api_id** (a number) and **App api_hash** (a long string). **Copy both** into your scratch note.

### Important safety notes
- The **api_hash cannot be revoked** — treat it like a password, never share or commit it.
- Telegram automatically watches accounts using the API. **Don't** use this to spam, mass-message, or scrape aggressively — just passively read your own channels. Abuse can get an account banned.
- Each phone number can only have **one** api_id. If you already created one before, reuse it.

✅ **Check:** you have `api_id` and `api_hash` saved.

---

## 4. Identify your channels

You don't need anything technical here — just decide *which* channels to track.
1. Make sure your main Telegram account has **already joined** every XAUUSD signal channel you want monitored. The system can only see channels you're a member of.
2. List them (names or @handles) in your scratch note. Claude Code will add a small helper to list joined channels and let you pick, but having your shortlist ready speeds this up.

✅ **Check:** you've joined all target channels and have a list.

---

## 5. Discord — from scratch

Goal: a private place where the bot DMs-style posts alerts to you, plus a **bot token** and a **channel ID** for the system to use.

**Quick mental model:**
- A **server** = your own private space (free; only you need to be in it).
- A **channel** = a room inside that server where alerts will appear (e.g. `#xau-signals`).
- An **application/bot** = the automated account your system controls to post those alerts.
- The **bot token** = the bot's password (keep secret).
- The **channel ID** = the exact address of the room to post in.

### 5a. Get Discord & make a server
1. Install Discord (desktop app or use the browser) and sign in / create an account: **discord.com**.
2. In the left sidebar, click the **+** → **Create My Own** → **For me and my friends**. Name it anything (e.g. `Trading Alerts`).
3. Inside it, you'll have a default channel like `#general`. Either use it or make a new one: click the **+** next to "Text Channels", name it `xau-signals`.

### 5b. Create the application + bot
1. Go to **https://discord.com/developers/applications** (sign in with the same account).
2. Click **New Application** (top right). Name it (e.g. `XAU Trust Bot`), accept the terms, **Create**.
3. In the left sidebar, click **Bot**.
4. Under **Token**, click **Reset Token** → **Yes** → **Copy**. Save this to your scratch note — this is `DISCORD_BOT_TOKEN`. (You can't view it again later; if lost, reset to get a new one.)
5. **Privileged Gateway Intents:** since this bot only *sends* alerts to you (it doesn't need to read other people's message text), you can leave **Message Content Intent OFF**. Leave the others off too. Minimal = safer. (If a future feature needs to read messages, you'd toggle Message Content on here and **Save Changes**.)

### 5c. Invite the bot to your server
1. Still in the developer portal, go to **OAuth2** in the sidebar.
2. Find **OAuth2 URL Generator**. Under **Scopes**, tick **bot**.
3. A **Bot Permissions** box appears below. Tick: **Send Messages**, **Embed Links**, **Create Public Threads**, **Send Messages in Threads**, **Read Message History**. (These let it post alerts and thread follow-ups.)
4. Copy the **Generated URL** at the bottom, paste it into your browser, hit Enter.
5. In the prompt, choose **Add to Server** → select your `Trading Alerts` server → **Authorize** → complete the captcha.
6. Back in Discord, you should now see the bot appear in your server's member list (offline until the system runs it — that's normal).

### 5d. Get the channel ID
1. In Discord, open **User Settings** (gear icon, bottom-left) → **Advanced** → turn **Developer Mode ON**.
2. Go back to your server, **right-click** the `xau-signals` channel → **Copy Channel ID**.
3. Save it — this is `DISCORD_CHANNEL_ID`.

✅ **Check:** you have the **bot token** and the **channel ID**, and the bot shows up in your server.

---

## 6. Anthropic API key (image parsing)

Some channels post signals as **images** (chart + colored zone, or MT5 profit screenshots). The system reads those with Claude's vision API, which needs an API key. This is **separate** from any Claude.ai chat subscription.
1. Go to **https://console.anthropic.com**, sign in / sign up.
2. Add a payment method and a little credit under **Billing** (vision calls are cheap, but the key won't work without credit).
3. Go to **API Keys** → **Create Key** → copy it. Save as `ANTHROPIC_API_KEY`.
4. Treat it like a password; never commit it.

✅ **Check:** you have a working API key with some billing credit.

> If you'd rather not parse images at all to start, you can skip this — the system will still handle text signals. But zone images and screenshots won't be processed until you add the key.

---

## 7. Collect everything for the `.env`

Claude Code will create the actual `.env` file. Your job is to have all the values ready. You should now have:

| Value | From | Example |
|---|---|---|
| `TG_API_ID` | Step 3 | `1234567` |
| `TG_API_HASH` | Step 3 | `0123ab...def` |
| `MT5_SYMBOL` | Step 2b | `XAUUSD.r` |
| `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER` | your RoboForex account (optional — only if Claude Code's setup asks for programmatic login) | — |
| `DISCORD_BOT_TOKEN` | Step 5b | `MTIx...` |
| `DISCORD_CHANNEL_ID` | Step 5d | `112233445566` |
| `ANTHROPIC_API_KEY` | Step 6 | `sk-ant-...` |

**Security rules (non-negotiable):**
- Never paste these into a chat, a public repo, or anywhere shared.
- Confirm `.env` is listed in `.gitignore` before the first commit (ask Claude Code to verify this).
- The Telegram **session file** it creates is as sensitive as your password — keep it private, don't commit it.

✅ **Check:** every value above is collected in your private scratch note.

---

## 8. Keeping it running 24/7 (live capture)

Live signal capture and the edit/delete tampering detection **only work while the listener is running**. Telegram does not replay edits that happened while you were offline — so uptime = data quality.

For a single Windows machine, simplest options:
- **Keep the machine on** and the listener process running in a terminal (fine for testing).
- For unattended running, have Claude Code set it up as a **Windows service** or a **Task Scheduler** task that auto-starts on boot and restarts on crash.
- Make sure **Windows sleep/hibernate is disabled** (Settings → System → Power → Screen and sleep → set to Never while plugged in), otherwise the listener pauses when the PC sleeps.
- MT5 must also stay open and logged in for verification to keep working.

You don't need to build this now — just know that gaps in uptime mean missed signals and missed tampering detection. Decide whether v1 runs only when you're at the machine, or always-on.

✅ **Check:** you've decided on always-on vs. when-present, and disabled sleep if going always-on.

---

## 9. Hand off to Claude Code

Once the checks above pass:
1. Create an empty project folder, open it in VS Code.
2. Put `CLAUDE.md` and `IMPLEMENTATION.md` in the folder root.
3. Start Claude Code and point it at `CLAUDE.md`.
4. Suggested first instruction: *"Read CLAUDE.md. Start by building and testing the MT5 price verifier against a XAUUSD signal I'll give you with a known outcome, before anything else."* (The verifier is the riskiest piece — prove it works before building the rest.)
5. When it asks for credentials, paste them from your scratch note into the `.env` it creates — **not** into the chat.

✅ **Check:** Claude Code is running in your project folder with both `.md` files present.

---

---

## 10. Wire Phase 1 credentials *(do this now — before Phase 3 starts)*

Phase 1 code is generated. Before Claude Code can build or test anything real, you need to:
1. Create the Python virtual environment and install packages
2. Fill in `.env` with your credentials
3. Apply the Supabase database schema
4. Fill in `frontend/.env.local` so the dashboard can query Supabase

Work through each section below in order. Each ends with a ✅ check.

---

### 10a. Python virtual environment + packages

Open a **PowerShell** window in the project root (`D:\AmirForex\TelegramSignalScore`) and run:

```powershell
# 1. Move into the backend folder
cd backend

# 2. Create the venv (do this once only)
python -m venv .venv

# 3. Activate it (you must do this every time you open a new terminal)
.\.venv\Scripts\Activate.ps1

# 4. Install all dependencies
pip install -r requirements.txt
```

**If `Activate.ps1` is blocked by execution policy**, run this first (once):
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```
Then re-run `.\.venv\Scripts\Activate.ps1`.

**Verify the install:**
```powershell
python -c "import fastapi, MetaTrader5, telethon, supabase, discord; print('all good')"
```
Should print `all good`. If any import fails, re-run `pip install -r requirements.txt`.

> `MetaTrader5` only installs on Windows — that's expected.

✅ **Check:** `python -c "import fastapi"` runs without error inside the venv.

---

### 10b. Fill in `.env`

In the project root (`D:\AmirForex\TelegramSignalScore`) you'll find `.env.example`.

1. Copy it to `.env` (same folder):
   ```powershell
   Copy-Item .env.example .env
   ```
2. Open `.env` in VS Code and paste in every value. Use the table below as a lookup:

| Key | Where to find it | Example |
|---|---|---|
| `TG_API_ID` | [my.telegram.org](https://my.telegram.org) → API development tools | `1234567` |
| `TG_API_HASH` | Same page | `0abc123def...` |
| `MT5_SYMBOL` | MT5 → Market Watch → exact gold symbol name | `XAUUSD.r` |
| `MT5_LOGIN` | Your RoboForex account number (optional) | `123456` |
| `MT5_PASSWORD` | Your RoboForex password (optional) | — |
| `MT5_SERVER` | Shown in MT5 login screen (optional) | `RoboForex-ECN` |
| `DISCORD_BOT_TOKEN` | Discord Developer Portal → your app → Bot → Token | `MTIx...` |
| `DISCORD_CHANNEL_ID` | Discord → Developer Mode on → right-click channel → Copy Channel ID | `112233445566` |
| `SUPABASE_URL` | Supabase → Project Settings → API → Project URL | `https://xxxx.supabase.co` |
| `SUPABASE_ANON_KEY` | Supabase → Project Settings → API → `anon` `public` key | `eyJh...` |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase → Project Settings → API → `service_role` key | `eyJh...` |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) → API Keys | `sk-ant-...` |

Leave `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER` blank for now if MT5 is already open and logged in — the verifier connects to the running terminal without needing credentials.

Leave `ANTHROPIC_API_KEY` blank if you're skipping image parsing for now (Phase 7).

> **Security:** `.env` is already in `.gitignore`. Never paste any of these values into a chat or commit them. The `SUPABASE_SERVICE_ROLE_KEY` bypasses all row-level security — treat it like a root password.

✅ **Check:** `.env` exists at the project root and every key has a value (except the optional ones you're deferring).

---

### 10c. Apply the Supabase schema

The migration file at `supabase/migrations/001_initial_schema.sql` creates all 8 tables with the correct columns, indexes, and row-level security policies. Apply it via the Supabase SQL editor:

1. Go to [supabase.com](https://supabase.com) → open your project.
2. In the left sidebar click **SQL Editor**.
3. Click **New query** (top-right of the SQL editor pane).
4. Open `supabase/migrations/001_initial_schema.sql` in VS Code, select all (`Ctrl+A`), copy.
5. Paste into the Supabase SQL editor, then click **Run** (or `Ctrl+Enter`).
6. You should see `Success. No rows returned` (or similar). If you see an error, read it — most common causes:
   - **"already exists"** — you ran the migration twice. Click **Table Editor** in the sidebar; if all 8 tables are there, you're fine; skip the error.
   - **"syntax error"** — copy/paste may have dropped a character. Re-copy from VS Code and paste fresh.

**Verify the tables exist:**
1. In Supabase, click **Table Editor** in the left sidebar.
2. You should see all 8 tables listed:
   - `channels`, `messages`, `message_edits`, `signals`, `signal_outcomes`, `screenshot_claims`, `score_breakdowns`, `discord_alerts`

**Verify RLS is on:**
1. Click **Authentication** → **Policies** in the sidebar.
2. Each table should show an `anon read …` policy allowing `SELECT`.

✅ **Check:** all 8 tables appear in Table Editor; each has at least one RLS policy.

---

### 10d. Fill in `frontend/.env.local`

The Next.js dashboard needs Supabase credentials to query data. These use the **public `NEXT_PUBLIC_` prefix** (safe to expose in browser bundles — they're the anon key, not the service role key).

1. Copy the example file:
   ```powershell
   Copy-Item frontend\.env.local.example frontend\.env.local
   ```
2. Open `frontend/.env.local` and fill in:

| Key | Value |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Same `SUPABASE_URL` as in your root `.env` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Same `SUPABASE_ANON_KEY` as in your root `.env` |

> These two keys are **intentionally public** — Supabase's anon key is designed to be exposed to the browser; the row-level security policies you applied in step 10c enforce what the anon key can and cannot do.

✅ **Check:** `frontend/.env.local` exists and both keys are filled in.

---

### 10e. Smoke-test the setup

Run these checks in order. Each one surfaces a specific failure mode.

**1. Backend can load config without errors:**
```powershell
cd D:\AmirForex\TelegramSignalScore\backend
.\.venv\Scripts\Activate.ps1
python -c "import config; print('symbol:', config.MT5_SYMBOL)"
```
Expected: prints `symbol: XAUUSD.r` (or your symbol).

**2. Backend can reach Supabase:**
```powershell
python -c "
from supabase import create_client
import config, os
from dotenv import load_dotenv; load_dotenv()
c = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)
result = c.table('channels').select('id').limit(1).execute()
print('Supabase OK — rows:', len(result.data))
"
```
Expected: `Supabase OK — rows: 0` (table exists, no data yet — that's correct).

**3. Dashboard starts:**
```powershell
cd D:\AmirForex\TelegramSignalScore\frontend
npm run dev
```
Open [http://localhost:3000](http://localhost:3000). The channel overview table should load (mock data, white/minimalist).

**4. FastAPI health check:**
```powershell
cd D:\AmirForex\TelegramSignalScore\backend
uvicorn api.main:app --reload --port 8000
```
Open [http://localhost:8000/health](http://localhost:8000/health). Should return `{"status":"ok"}`.

✅ **Check:** all four smoke tests pass. Then hand back to Claude Code — Phase 3 (MT5 verifier) is next.

---

## Troubleshooting quick reference

| Symptom | Likely cause | Fix |
|---|---|---|
| Verifier returns no candles | MT5 closed, wrong symbol name, or history not cached | Open MT5, confirm `MT5_SYMBOL` exactly, scroll an M1 gold chart back |
| Telegram login loops / fails | Wrong code, or api_id/hash mismatch | Re-copy api_id/api_hash; codes expire fast — request a fresh one |
| Bot offline in Discord | System not running, or bad token | Start the listener/bot; if token leaked or wrong, Reset Token and update `.env` |
| Bot can't post in channel | Missing permission or wrong channel ID | Re-invite with Send Messages + Embed Links; re-copy Channel ID (Developer Mode on) |
| Images not parsed | No Anthropic key or no billing credit | Add key + credit in console.anthropic.com |
| Account warning from Telegram | API used too aggressively | Keep usage passive (read-only); never spam/scrape |
| `Activate.ps1` blocked by PowerShell | Execution policy restriction | `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` |
| `pip install` fails on `MetaTrader5` | Not on Windows, or Python version mismatch | MT5 package is Windows-only; must use Python 3.11+ 64-bit |
| Supabase `create_client` import error | Wrong package version or venv not active | Activate venv first; `pip install supabase==2.10.0` |
| Dashboard shows "env not defined" error | `.env.local` missing or keys not prefixed `NEXT_PUBLIC_` | Create `frontend/.env.local` with both `NEXT_PUBLIC_` keys |
| Migration fails with "already exists" | Migration run twice | Check Table Editor for all 8 tables; if present, ignore the error |
| `uvicorn` command not found | Venv not active | Run `.\.venv\Scripts\Activate.ps1` from the backend folder first |
