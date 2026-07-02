# IMPLEMENTATION.md — Your Setup Runbook (Human Tasks)

> **What this file is:** everything **you** need to set up by hand before Claude Code can build and run the system. Accounts, credentials, installs, and config — not code. Claude Code reads `CLAUDE.md` and writes the software; this file makes sure the environment it runs in is ready.
>
> **Your environment:** Windows machine, MT5 always running, everything (pipeline + dashboard) runs locally. Telegram via your main account. Discord built from scratch (explained below).
>
> Work top to bottom. Each section ends with a ✅ check so you know it's done. Keep every secret you collect in one scratch note for now — you'll paste them into a `.env` file at the end.

---

## ▶ RUN IT LIVE — start here (you only need this)

**Your setup is already done.** The Python venv (`backend\.venv`), `.env`, tracked channel IDs, Supabase, and the dashboard are all configured and verified. To monitor signals **from now on**, you do **not** need to load any history — you just start **three** processes, each in its own PowerShell window, and leave them running.

> ### ⚠️ The one mistake that causes 90% of errors
> **Every window must activate the venv first** with `.\.venv\Scripts\Activate.ps1`. You'll know it worked when the prompt shows `(.venv)` at the start.
> If you run `python` **without** activating it, you get `ModuleNotFoundError: No module named 'dotenv'`. That does **not** mean anything is broken — it just means the venv isn't active. (This is exactly the error you hit.)

**Before you start:** open MetaTrader 5, log into RoboForex, and leave an **M1 XAUUSD chart** visible. Verification can't run without it.

---

> **Both backend windows must be run from the project root** (`D:\AmirForex\TelegramSignalScore`), not from `backend\`. The commands below activate the venv *from* the root so you never have to `cd` around — if you run them from inside `backend\` you'll get `No module named 'backend'`.

### Window 1 — Backend API  *(verifies signals every 5 min, sends Discord follow-ups)*

```powershell
cd D:\AmirForex\TelegramSignalScore
.\backend\.venv\Scripts\Activate.ps1
uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
```
Wait for: `Uvicorn running on http://127.0.0.1:8000`. Leave it running.

### Window 2 — Telegram listener  *(captures new messages/edits/deletes, fires Discord alerts)*

```powershell
cd D:\AmirForex\TelegramSignalScore
.\backend\.venv\Scripts\Activate.ps1
python -m backend.ingestor
```
Wait for: `Telegram ingestor running. Press Ctrl-C to stop.` Leave it running. **From this moment, every new signal in your tracked channels is captured live.**

### Window 3 — Dashboard

```powershell
cd D:\AmirForex\TelegramSignalScore\frontend
npm run dev
```
Wait for `Ready in x.xs`, then open **http://localhost:3000**.

---

**That's the whole system.** The dashboard starts **empty** and fills in as new signals arrive and resolve against MT5 — that's expected, since you're monitoring from now on, not importing the past.

- **New signal posted** → captured, AI-assessed, instant Discord alert.
- **Signal edited/deleted** → recorded, Discord follow-up fires (your tampering tripwire).
- **Every 5 minutes** → the verifier checks open signals against MT5; resolved ones update the Trust Scores automatically.

**To stop:** press `Ctrl+C` in each window. Everything is saved in Supabase; next time, just run the three commands again.

> **Don't want to bother with history at all?** Then you're done — skip everything below about backfill. The old "Day 1" steps (`backfill`, `reprocess_images`, `ai_assess`) **only import past signals**, which you've said you don't care about. Ignore them.
>
> The reference sections below (one-time account/credential setup, historical loading, troubleshooting) are kept for completeness, but for day-to-day live monitoring the three windows above are all you need.

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

## 11. Before you start for the very first time

This section covers three quick one-time tasks. You only ever do these once, then never again.

---

### 11a. Apply the Realtime database migration

**What this does:** lets the dashboard refresh automatically when trust scores change, without you having to reload the page.

1. Go to [supabase.com](https://supabase.com) → open your project.
2. In the left sidebar click **SQL Editor**.
3. Click **New query** (top-right of the SQL editor pane).
4. In VS Code, open the file `supabase/migrations/002_enable_realtime.sql`. Press **Ctrl+A** to select all, **Ctrl+C** to copy.
5. Click inside the Supabase SQL editor, press **Ctrl+V** to paste, then click **Run**.
6. You should see `Success. No rows returned`. That's correct — it means it worked.

> If you see `ERROR: relation already exists` or `already added`, that means you ran this before. That's fine — move on.

✅ **Done when:** Supabase shows success (or "already added").

---

### 11b. Check the AI migration is in place (nothing to run — just verify)

**What this is:** the AI intelligence migration (`003_ai_intelligence.sql`) was already applied automatically when the system was built. You don't need to run it. This step just confirms it's there.

1. In Supabase, click **Table Editor** in the left sidebar.
2. Scroll through the list of tables. You should see **`signal_quality_assessments`** and **`channel_ai_assessments`** in the list alongside the other tables.

> If those two tables are missing, go to SQL Editor → New query → open `supabase/migrations/003_ai_intelligence.sql` in VS Code → copy/paste → Run.

✅ **Done when:** both AI tables are visible in Table Editor.

---

### 11c. Find your Telegram channel IDs and set them in `.env`

**What this does:** the system needs the numeric IDs of your Telegram channels (not their names — actual numbers like `-1001234567890`). This script logs into Telegram as you and lists every channel you're a member of, with their IDs.

**Step 1 — Open a PowerShell window in the project root and activate the Python environment:**

```powershell
cd D:\AmirForex\TelegramSignalScore\backend
.\.venv\Scripts\Activate.ps1
cd ..
```

You'll see `(.venv)` appear at the start of the prompt. That means the environment is active. Every command in this section needs this environment active.

**Step 2 — Run the channel listing script:**

```powershell
python -m scripts.list_channels
```

The **very first time** you run any Telegram script, it will pause and ask:

```
Please enter your phone number (with country code, e.g. +60123456789):
```

Type your number and press Enter. Telegram will send a **login code** to your Telegram app on your phone. Type that code when asked. This creates a session file on your computer — after this you won't be asked to log in again.

**Step 3 — Read the output:**

The script prints a table like this:

```
ID                   Type      Members  Name
-1001234567890       channel   48200    Gold Signals VIP
-1009876543210       channel   12300    XAUUSD Pro
-1007777777777       channel    3100    FX Premium Alerts
...
```

Write down the **ID** column for every channel you want to track. IDs are always negative numbers starting with `-100`.

**Step 4 — Add the IDs to your `.env` file:**

Open `.env` in VS Code. Find the line that says `TRACKED_CHANNEL_IDS=` and fill it in:

```
TRACKED_CHANNEL_IDS=-1001234567890,-1009876543210,-1007777777777
```

Rules:
- Separate multiple IDs with commas — no spaces
- Negative numbers are correct
- The system will only monitor these channels and ignore everything else

Save the file.

✅ **Done when:** `.env` has `TRACKED_CHANNEL_IDS=` set with at least one ID.

---

## 12. (OPTIONAL) Loading historical data

> **Skip this whole section if you only want to monitor from now on.** You already have the live system running from the **▶ RUN IT LIVE** section at the top — that's all you need. This section only *imports past signals* so the dashboard has data before new signals arrive. It does **not** change how live monitoring works.

This is the optional first-day flow if you *do* want history. You'll start the three background processes, then load history from your channels so the dashboard has past data to score.

**Set aside about 30–60 minutes.** Most of that time is waiting for scripts to finish — you don't need to watch them.

**Before you begin:** make sure MetaTrader 5 is open, logged into your RoboForex account, and an M1 XAUUSD chart is visible. If MT5 is closed, signals can't be verified and scores won't update.

---

### Step 1 — Open four PowerShell windows

You'll need four separate PowerShell windows open at the same time. The easiest way:

- Right-click the PowerShell icon in your taskbar → **Open new window** — do this four times.
- Arrange them on screen so you can see all four (Windows key + arrow keys to snap them).

Label them mentally: Window A, Window B, Window C, Window D.

---

### Step 2 — Start the Backend API (Window A)

**What this does:** runs the engine that verifies signals against MT5 price data every 5 minutes and updates trust scores. It also sends Discord follow-up messages when a signal resolves.

In **Window A**, run:

```powershell
cd D:\AmirForex\TelegramSignalScore\backend
.\.venv\Scripts\Activate.ps1
cd ..
uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
```

Wait for this output (takes a few seconds):

```
INFO:     Started server process [12345]
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO      backend.api.main — Discord notifier initialized
```

> **Why `127.0.0.1` and not `0.0.0.0`?** The API has no authentication and uses the Supabase service-role key, and its `/verify/run` and `/ai/assess/channel` endpoints trigger MT5 work and paid Claude calls. Binding to `127.0.0.1` keeps it reachable only from this machine (your dashboard and `curl` commands all use localhost), so nothing on your network can read your data or run up Anthropic charges. Only change this if you deliberately put it behind an authenticated reverse proxy.

> The `Discord notifier initialized` line only appears if `DISCORD_BOT_TOKEN` is set in `.env`. If you see it, Discord alerts are working. If you don't see it, double-check your Discord token in `.env`.

**Leave Window A running.** Do not close it or press Ctrl+C.

---

### Step 3 — Start the Telegram listener (Window B)

**What this does:** connects to Telegram as you, listens to your tracked channels in real time, and automatically saves every new message, edit, and deletion. When it sees a trading signal, it sends an instant Discord alert.

In **Window B**, run:

```powershell
cd D:\AmirForex\TelegramSignalScore\backend
.\.venv\Scripts\Activate.ps1
cd ..
python -m backend.ingestor
```

Wait for this output:

```
INFO      backend.ingestor — Telegram ingestor running. Press Ctrl-C to stop.
```

> If Telethon asks for your phone number again here, enter it the same way you did in step 11c. This shouldn't happen if you already ran `list_channels`, but occasionally the session needs refreshing.

**Leave Window B running.** From this moment on, any new messages posted in your tracked channels will be captured automatically.

---

### Step 4 — Start the dashboard (Window C)

**What this does:** starts the web dashboard you view in your browser.

In **Window C**, run:

```powershell
cd D:\AmirForex\TelegramSignalScore\frontend
npm run dev
```

Wait until you see:

```
▲ Next.js 14.x.x
- Local:        http://localhost:3000
- Ready in 2.1s
```

Now open your browser and go to **http://localhost:3000**.

The dashboard will show an empty table for now — that's normal. You haven't loaded any history yet. You'll fill it in the next steps.

**Leave Window C running.**

---

### Step 5 — Load historical messages for each channel (Window D)

**What this does:** goes back through each channel's Telegram message history and imports all the signals, edits, and deletions that happened before you started the listener. This gives the system enough past data to calculate a meaningful trust score.

> **First-run login (one time only):** backfill uses its **own** Telegram session, separate from the live listener in Window B. Telegram cannot share one session across two running processes — if backfill reused the listener's session it would hang forever at "Connecting to Telegram". So the **very first** backfill command will pause and ask for your phone number and a login code (same as step 11c). Enter them once; a separate `xau_signal_bot_backfill.session` file is created and you won't be asked again. Because it's a separate session, **backfill is safe to run while the listener (Window B) is up** — no need to stop it.

In **Window D**, run **one** command — it backfills every channel on a single connection. Pass all IDs comma-separated, or use `--all` to read them from `TRACKED_CHANNEL_IDS` in `.env`.

```powershell
cd D:\AmirForex\TelegramSignalScore\backend
.\.venv\Scripts\Activate.ps1
cd ..

# All channels in one run (recommended) — uses TRACKED_CHANNEL_IDS from .env:
python -m scripts.backfill --all --limit 500

# ...or list specific IDs, comma-separated, no spaces:
python -m scripts.backfill --channel -1001234567890,-1009876543210,-1007777777777 --limit 500
```

> **Why one command, not one per channel:** backfill connects to Telegram once and loops through every channel on that connection. Launching a *separate* command per channel reconnects the same session within seconds each time, which can stall at "Connecting to Telegram". The single run avoids that.

**What `--limit 500` means:** fetch the last 500 messages from that channel. For channels that post multiple signals per day, 500 messages may only cover a few weeks. If you want more history, increase the number:
- `--limit 1000` → roughly 1–3 months depending on how active the channel is
- `--limit 2000` → more history but takes longer

**What you'll see while it runs:**

```
Backfilling channel -1001234567890 (Gold Signals VIP)...
  50 processed (inserted=48, skipped=2, signals=12)
  100 processed (inserted=95, skipped=5, signals=28)
  ...
Done. 487 inserted, 13 skipped, 94 signals found.
```

It typically takes 1–5 minutes per channel; the single run processes them back-to-back, so just let it finish.

✅ **Done when:** all your channels have been backfilled and the script prints "Done" for each one.

> **Backfill alone does not produce Trust Scores.** It only *imports* history (text parsed by regex, images stored for later). Channels stay unscored until you run the verification pass in **Step 8** — and a meaningful score needs several signals to actually resolve against MT5 (a handful of resolved signals shows only the integrity baseline, not real performance).

---

### Step 6 — Process channel images (Window D, same window)

**What this does:** during backfill, any message that contained an image (chart screenshots, MT5 profit screenshots) was saved but not analysed yet — the system needs to look at each image with AI vision to understand what it shows. This step does that.

> **Session note:** like backfill, this uses the **separate** backfill session (`xau_signal_bot_backfill.session`), so it's safe to run while the live listener (Window B) is up — no need to stop it. You already logged that session in during Step 5, so there's no new login here.

Still in Window D, run:

```powershell
python -m scripts.reprocess_images --limit 200
```

**What you'll see:**

```
Reprocessing 200 deferred images...
  msg=11111 → zone_image signal inserted (dir=BUY)
  msg=22222 → mt5_screenshot, verdict=confirmed
  msg=33333 → non_signal (no levels found)
  ...
Done. 200 images processed.
```

**Cost note:** each image uses 1–2 Claude API calls. 200 images costs roughly $0.20–$0.60. You can re-run this any time; images that are already processed are skipped automatically.

If you have more than 200 deferred images (check Window A logs — it will say `image_deferred` for images that weren't processed during backfill), run it again with a higher limit:

```powershell
python -m scripts.reprocess_images --limit 500
```

✅ **Done when:** the script finishes and prints "Done".

---

### Step 7 — Run AI quality assessment on your history (Window D, same window)

**What this does:** goes through all the signals and edits you just imported and uses Claude to assess each one:
- **Signals:** is this a genuine forward signal, or is it a hindsight post pretending to be one? How high quality is it?
- **Edits:** was this edit an innocent typo fix, or did the channel owner suspiciously change the price levels after the market moved?
- **Channels:** based on all the above, how fraudulent does this channel's overall behaviour look?

This is what makes the trust scores meaningful instead of just counting wins and losses.

In Window D, run:

```powershell
python -m scripts.ai_assess --mode all --delay 1.0
```

This runs three steps automatically, one after another:

```
[signals] Assessing quality for 94 signals...
  10 / 94 done
  20 / 94 done
  ...
Signals: assessed 94 rows.

[edits] Analyzing intent for 18 edits...
  10 / 18 done
  ...
Edits: analyzed 18 rows.

[channels] Analyzing behavior for 3 channels...
  Gold Signals VIP — fraud_risk=0.12, findings: Channel posts genuine forward signals...
  XAUUSD Pro — fraud_risk=0.71, findings: 3 of 5 edits changed TP levels after price...
  ...
Channels: analyzed 3.
```

**How long this takes:** roughly 1–2 seconds per signal/edit (the `--delay 1.0` adds a pause between calls to avoid rate limits). For 100 signals + 20 edits = about 2–3 minutes total.

**Cost:** approximately $0.30–$0.70 for a few hundred signals/edits.

✅ **Done when:** the script prints results for all three modes and exits.

---

### Step 8 — Trigger a verification pass and see scores in the dashboard

**What this does:** runs the MT5 price verifier against all the signals you just imported. For each signal, it checks whether the price actually hit stop-loss or take-profit, and records the outcome (win/loss/unresolved). These outcomes are what drive the trust score numbers.

Make sure MT5 is open and logged in, then in Window D run:

```powershell
Invoke-RestMethod -Uri http://localhost:8000/verify/run -Method Post
```

You'll see in **Window A**:

```
INFO      backend.api.main — Verification pass: processed 47 signals
INFO      backend.api.main — Score updated for channel: Gold Signals VIP
INFO      backend.api.main — Score updated for channel: XAUUSD Pro
```

Now go to **http://localhost:3000** in your browser. You should see:
- Each tracked channel appears as a row in the table
- Trust Score column shows a number (0–100)
- Verdict column shows `avoid`, `observe`, `caution`, or `trusted`
- Win rate, signal count, and other stats are populated

> Signals posted very recently (less than 48 hours ago) may still show as "unresolved" — that's normal. The verification loop in Window A will keep checking them every 5 minutes automatically.

✅ **Done when:** the dashboard shows at least one channel with a trust score and signal count.

---

### What you now have

At this point your system is fully running:

| Component | Status |
|---|---|
| Window A (Backend API) | Running — verifies signals every 5 min, updates scores |
| Window B (Ingestor) | Running — capturing new messages, edits, and deletions live |
| Window C (Dashboard) | Running — visible at http://localhost:3000 |
| Historical data | Loaded — backfill + images + AI assessment + scores all done |
| Discord alerts | Active — new forward signals will ping you instantly |

You can close Window D — it was only needed for the one-time setup scripts.

---

## 13. Every day after — starting the system

From Day 2 onwards, the process is much simpler. You just need to start the three background processes. **You never run the setup scripts again** (backfill, reprocess_images, ai_assess) — those were one-time only.

---

### Before you open anything

Make sure **MetaTrader 5** is open and logged into your RoboForex account with an M1 XAUUSD chart visible. The verifier can't work without it.

---

### Open three PowerShell windows and run one command in each

**Window 1 — Backend API:**

```powershell
cd D:\AmirForex\TelegramSignalScore\backend
.\.venv\Scripts\Activate.ps1
cd ..
uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
```

Wait for: `Uvicorn running on http://127.0.0.1:8000`

---

**Window 2 — Telegram ingestor:**

```powershell
cd D:\AmirForex\TelegramSignalScore\backend
.\.venv\Scripts\Activate.ps1
cd ..
python -m backend.ingestor
```

Wait for: `Telegram ingestor running. Press Ctrl-C to stop.`

---

**Window 3 — Dashboard:**

```powershell
cd D:\AmirForex\TelegramSignalScore\frontend
npm run dev
```

Wait for: `Ready in x.xs`

Then open **http://localhost:3000** in your browser. Everything you saw yesterday is still there — trust scores, signal history, edit logs. The table updates automatically as new signals come in.

---

### What happens automatically while the system is running

You don't need to do anything — just leave the three windows open:

| Every time a new signal is posted | Ingestor captures it, AI assesses quality, Discord alert fires |
|---|---|
| Every time a signal is edited | Edit is recorded, AI classifies intent (typo vs. suspicious), Discord follow-up fires if it was a signal |
| Every time a signal is deleted | Deletion is recorded, Discord follow-up fires, channel's delete count goes up |
| Every 5 minutes | MT5 verifier checks all open signals — any that have resolved get scored and trust scores update |
| After each verification pass | Channel behavior is re-assessed by AI if new signals resolved |

---

### To stop the system

Press **Ctrl+C** in each of the three windows. The system saves everything to Supabase as it goes, so nothing is lost — when you start again tomorrow, it picks up exactly where it left off.

---

### Tips for the rest of the week

**If you restart and don't see recent signals on the dashboard:** they're already in Supabase. The dashboard loads from the database, not from memory — a restart changes nothing.

**If you missed a few hours of live monitoring:** the ingestor can't backfill edits/deletions that happened while it was offline (Telegram doesn't replay those). But new messages posted while you were offline will be fetched when the ingestor reconnects. Run `python -m scripts.backfill --channel <id> --limit 100` in a fourth window to catch up on any missed messages. Backfill uses its own session, so it's fine to run this while the listener (Window 2) is still running.

**If a channel's score looks wrong after a few days:** the AI channel assessment runs automatically, but you can force a fresh one by running in a fourth window (while Window 1 is running):
```powershell
Invoke-RestMethod -Uri http://localhost:8000/ai/assess/channel/<channel-uuid> -Method Post
```
Get the UUID from Supabase → Table Editor → channels → copy the `id` value for that channel.

**If MT5 was closed and you missed a verification window:** open MT5, then in a fourth window run:
```powershell
cd D:\AmirForex\TelegramSignalScore\backend
.\.venv\Scripts\Activate.ps1
cd ..
Invoke-RestMethod -Uri http://localhost:8000/verify/run -Method Post
```
This triggers an immediate pass — you don't have to wait 5 minutes.

---

## 14. Optional: tune AI scoring behaviour

These settings have sensible defaults. You don't need to change them unless the trust scores feel off after a week of data.

Open `.env` in VS Code and add or change any of these lines:

```
# Set any of these to false to disable that specific AI feature:
AI_PARSER_ENABLED=true           # AI tries to parse signals the regex couldn't read
AI_QUALITY_ENABLED=true          # AI filters out retrospective/hindsight signals
AI_EDIT_ANALYSIS_ENABLED=true    # AI judges whether edits are innocent or suspicious
AI_CHANNEL_ANALYSIS_ENABLED=true # AI gives channels an overall fraud-risk score

# A signal with quality_score below this threshold is downweighted in the score:
AI_LOW_QUALITY_THRESHOLD=0.4     # 0.0–1.0, default 0.4
AI_LOW_QUALITY_WEIGHT=0.5        # how much to downweight it (0.5 = count as half a signal)

# Integrity penalty per suspicious edit (0.0 for typos, up to this for clear manipulation):
PENALTY_AI_SUSPICIOUS_EDIT=5.0

# Max integrity points a channel can lose from the overall fraud-risk assessment:
AI_BEHAVIOR_PENALTY_MAX=10.0
```

After changing any of these, **restart Window 1** (Ctrl+C then run the uvicorn command again), then run:

```powershell
python -m scripts.ai_assess --mode channels
```

to recalculate channel scores with the new settings.

---

## 15. Troubleshooting

| Problem | Most likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'dotenv'` (or `telethon`, etc.) | The venv isn't active — you're running global Python | Run `.\.venv\Scripts\Activate.ps1` in that window first; the prompt must show `(.venv)`. Nothing is broken. |
| `Invoke-WebRequest : A parameter cannot be found that matches parameter name 'X'` | In PowerShell, `curl` is an alias for `Invoke-WebRequest`, which has no `-X` | Use `Invoke-RestMethod -Uri <url> -Method Post`, or call real curl as `curl.exe -X POST <url>` |
| `No module named 'backend'` when starting the ingestor/API | You're running from inside the `backend\` folder | Run from the project root: `cd D:\AmirForex\TelegramSignalScore` first, then the `python -m backend.ingestor` / `uvicorn` command |
| Window 1 starts but shows no `Discord notifier initialized` | `DISCORD_BOT_TOKEN` or `DISCORD_CHANNEL_ID` missing or wrong in `.env` | Double-check both values in `.env`; restart Window 1 |
| Window 2 starts but nothing happens when channels post | `TRACKED_CHANNEL_IDS` is empty or has wrong IDs | Re-run `python -m scripts.list_channels`, copy IDs, update `.env`, restart Window 2 |
| Telegram keeps asking for login code | Session file missing or expired | Re-run `python -m scripts.list_channels` to create a fresh session, then restart Window 2 |
| Dashboard at localhost:3000 shows empty table | No channels backfilled yet, or Window 1 not running | Complete Steps 5–8 in §12; make sure Window 1 is running |
| Trust score shows 0 for all channels | No signals have resolved yet | MT5 must be open; run `Invoke-RestMethod -Uri http://localhost:8000/verify/run -Method Post` to force a check |
| Verifier says "MT5 not connected: copy_rates_from returned no data" | Either MT5 is closed/not logged in, **or** `MT5_SYMBOL` doesn't match your broker's exact name (this is the usual cause even when MT5 is open) | Open MT5 and load an M1 XAUUSD chart; then confirm `MT5_SYMBOL` matches **exactly**, including case — MT5 symbol names are case-sensitive (`XAUUSD` ≠ `xauusd`) |
| `MT5_SYMBOL` error / no price data | Symbol name is wrong or wrong case | Open MT5 → Market Watch → right-click → Symbols → copy the **exact** gold name (case-sensitive, e.g. `XAUUSD`) → update `.env` → restart Window 1 |
| Images in channels are not being classified | `ANTHROPIC_API_KEY` missing or no billing credit | Add key and billing at console.anthropic.com; then run `reprocess_images` |
| `Activate.ps1` blocked by PowerShell | Execution policy restriction on your machine | Run this once: `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` |
| `uvicorn: command not found` | Venv not activated | You must run `.\.venv\Scripts\Activate.ps1` before any `uvicorn` or `python -m` command |
| `pip install` error on `MetaTrader5` | Not on Windows, or using 32-bit Python | MT5 package only works on Windows with 64-bit Python 3.11+ |
| Supabase `create_client` import error | Wrong package version or venv not active | Activate venv first; run `pip install supabase==2.10.0` |
| Dashboard shows "env not defined" error | `frontend/.env.local` missing or wrong keys | Create `frontend/.env.local` with `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` |
| Migration fails with "already exists" | Migration was already applied | Check Supabase Table Editor — if the tables are there, ignore the error |
| `ai_assess` prints "ANTHROPIC_API_KEY not set" | Key missing from `.env` | Add `ANTHROPIC_API_KEY=sk-ant-...` to `.env`; no restart needed for scripts |
| AI assessment runs but all scores are the same | Rate limit or very slow responses | Increase delay: `--delay 2.0` |
| Trust score didn't change after `ai_assess --mode channels` | Channel has fewer than 3 resolved signals | Backfill more history or wait for more signals to resolve |
| `signal_quality_assessments` table not found | Migration 003 not applied | SQL Editor → paste `003_ai_intelligence.sql` → Run |
| Discord bot is offline in your server | System not running | Start Window 1 and Window 2; bot only comes online when the system is running |
| Bot can't post in Discord channel | Missing permissions or wrong channel ID | Re-invite bot with Send Messages + Embed Links permissions; re-copy Channel ID with Developer Mode on |
