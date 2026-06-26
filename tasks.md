# XAUUSD Signal Trust Score — Development Tracker

> **Build order:** Dashboard (mock data) → Core backend → Telegram ingestor → Wire real data → Discord notifications → Image parsing (deferred)
> **Database:** Supabase Cloud (PostgreSQL) | **Frontend:** Next.js 14 + shadcn/ui + Tailwind CSS | **Backend:** Python + FastAPI

---

## Phase 0 — Environment & Credentials *(human tasks — do these before any code runs)*

- [ ] **MT5** — install from RoboForex, log in (demo or live), open an M1 XAUUSD chart and scroll back to cache history. Note the **exact** symbol name (e.g. `XAUUSD.r`) — this goes into `.env` as `MT5_SYMBOL`
- [ ] **Telegram** — go to [my.telegram.org](https://my.telegram.org), create an app, copy `api_id` and `api_hash`
- [ ] **Discord** — create a server, create a bot application at [discord.com/developers](https://discord.com/developers), invite the bot with Send Messages + Embed Links + Threads permissions, copy bot token and channel ID
- [ ] **Supabase** — create a free project at [supabase.com](https://supabase.com), copy Project URL, anon key, and service role key
- [ ] **`.env` file** — paste all credentials into `.env` once Claude generates `.env.example`

---

## Phase 1 — Project Foundation

- [x] Scaffold directory structure
  - `backend/` — Python FastAPI app (verifier, parser, scorer, ingestor, notifier)
  - `frontend/` — Next.js dashboard
  - `scripts/` — one-off utilities (backfill, DB seed, channel picker)
  - `tests/` — verifier and scorer unit tests
- [x] Generate `.env.example` with all required keys and comments
- [x] Design Supabase schema and apply migrations
  - `channels` — tracked Telegram channels + computed Trust Score
  - `messages` — every raw message (immutable; includes non-signals)
  - `message_edits` — full edit history per message (original + each revision, timestamped)
  - `signals` — parsed forward signals (text-stated vs. zone-estimated flag)
  - `signal_outcomes` — MT5-verified results (SL hit / TP hit / ambiguous / unresolved)
  - `screenshot_claims` — MT5 profit screenshots + cross-check verdict
  - `discord_alerts` — sent alert message IDs for de-duplication
  - `score_breakdowns` — per-channel score breakdown snapshot (for explainable dashboard)
- [x] Python backend — create venv, `requirements.txt`, install:
  - `fastapi`, `uvicorn`, `MetaTrader5`, `telethon`, `supabase`, `discord.py`, `python-dotenv`, `pydantic`
- [x] Next.js frontend — init with App Router, install shadcn/ui, configure Supabase client (`@supabase/supabase-js`, `@supabase/ssr`)
- [x] `config.py` — all tunable constants: symbol, verification window, point definition, score weights, verdict thresholds

---

## Phase 2 — Dashboard (Mock Data)

> Goal: full UI working and looking correct before any real data flows in.

- [x] **Channel overview page** (`/`)
  - Sortable table: Trust Score, Verdict badge, Verified Win Rate, Sample Size, Total Points, Avg R:R, Edits, Deletes, Last Signal
  - Color-coded verdict column (Avoid → red, Observe → orange, Caution → yellow, Trusted → green)
  - Click row → channel detail
- [x] **Channel detail page** (`/channel/[id]`)
  - Score breakdown panel: each scoring factor with its contribution (explainable, not a black box)
  - Red flags panel: contradicted screenshots, post-move edits, deleted losers
  - Tabbed signal history: **Stated-text signals** | **Zone-estimated signals** | **Screenshots** | **Non-signals**
  - Per-signal rows: parsed levels, outcome badge, points P&L
  - Edit history timeline: original text → each edit with timestamp diff
- [x] **Mock data layer** — `frontend/lib/mock-data.ts` with realistic static data matching the Supabase schema exactly (so swapping real data in later requires zero UI changes)
- [x] shadcn/ui DataTable with column sorting, column visibility toggle
- [x] Verdict badges and Trust Score progress bar / gauge component
- [x] Disclaimer footer ("Scores reflect past broker-specific verification only — not trading advice")
- [x] Responsive layout *(dark mode skipped — white/minimalist only per design preference)*

---

## Phase 3 — Core Backend

> Build and **prove** the verifier before anything else goes live.

- [ ] **MT5 price verifier** (`backend/verifier.py`)
  - Connect to local MT5 terminal via `MetaTrader5` package
  - Fetch 1-minute candles from signal post time to `now` (or verification window end)
  - Walk candles forward: first touch of SL → loss; first touch of TP → win
  - Require entry fill: skip candles before price reaches entry level
  - Ambiguity rule: single candle spans both SL and TP → mark as `ambiguous_loss`, flag it
  - Return: outcome (`win` / `loss` / `ambiguous_loss` / `unresolved`), points, candles inspected
  - Graceful failure: if MT5 is closed/disconnected, raise a typed error — never return a silent wrong answer
- [ ] **Verifier test suite** (`tests/test_verifier.py`)
  - At least 3 signals with known outcomes (known from live trading history)
  - Test: clean win, clean loss, ambiguous candle, entry never filled, MT5 offline
- [ ] **Text signal parser** (`backend/parser.py`)
  - Regex + rule-based: extract direction (BUY/SELL), entry, SL, TP (supports multiple TP levels)
  - Multi-TP: treat TP1 as primary win target; record further targets as extras
  - Return structured `ParsedSignal` with confidence score
- [ ] **Trust score calculator** (`backend/scorer.py`)
  - Inputs: verified outcomes, edit/delete counts, screenshot verdicts, sample size, backfill flags
  - Components: win rate component, expectancy component, R:R component, integrity penalty, sample-size dampener
  - Stated and zone-estimated signals weighted separately; backfilled data weighted less
  - Every component exposed individually (for the dashboard breakdown)
  - All weights and thresholds read from `config.py`
- [ ] **FastAPI app** (`backend/api/`)
  - `GET /channels` — overview list with current scores
  - `GET /channels/{id}` — detail with score breakdown and signal history
  - `GET /channels/{id}/signals` — paginated signal list with outcomes and edit history
  - `POST /verify/run` — manually trigger verification pass (for testing)
- [ ] **Verification scheduler** — background task that re-checks `unresolved` signals every N minutes; marks expired if verification window passes

---

## Phase 4 — Telegram Ingestor

- [ ] **Channel picker script** (`scripts/list_channels.py`) — connect as user, print all joined channels + IDs so you can choose which to track
- [ ] **Live listener** (`backend/ingestor.py`)
  - Telethon user-client, connects with `api_id` + `api_hash`
  - Event handlers: `NewMessage`, `MessageEdited`, `MessageDeleted`
  - On new message: write to `messages`, classify type, trigger parser
  - On edit: append to `message_edits` (never overwrite); if a signal's levels changed post-post-time → flag as integrity violation
  - On delete: mark in `messages`; if it was a signal → flag as deleted-signal integrity event
- [ ] **Backfill** (`scripts/backfill.py`) — pull channel history up to configurable message limit; mark all as `source: backfill` (weighted less in scoring)
- [ ] **Message classifier** — route each message to: `text_signal` / `image` / `mt5_screenshot` / `non_signal`
  - Images: if no Anthropic key is present, log as `image_deferred` and skip (don't crash)

---

## Phase 5 — Wire Dashboard to Real Data

- [ ] Replace `mock-data.ts` with real Supabase queries in Next.js server components
- [ ] Supabase Realtime subscription on `channels` table → overview table updates live without refresh
- [ ] Run full end-to-end: Telegram message → parsed signal → verified outcome → updated Trust Score → dashboard reflects it
- [ ] Stress test: backfill a channel with 50+ messages, confirm scores are correct

---

## Phase 6 — Discord Notifications

- [ ] **Discord bot** (`backend/notifier/discord_bot.py`)
  - Notification interface: `Notifier` base class with `send_signal_alert()`, `send_edit_followup()`, `send_delete_followup()`, `send_resolution_followup()` — so other channels can be added later without touching the pipeline
  - `DiscordNotifier` implements the interface
- [ ] **Signal alert embed**
  - Fields: Channel name, Direction (BUY/SELL), Entry / SL / TP, Current Trust Score + verdict
  - Color: embed color matches verdict (red / orange / yellow / green)
  - Fires immediately on signal parse (before verification)
- [ ] **Threaded follow-ups** (posted as replies to the original alert thread)
  - Edit follow-up: "⚠️ Levels changed" — shows old → new diff with timestamp
  - Delete follow-up: "🗑️ Message deleted"
  - Resolution follow-up (optional): "✅ Win +X pts" or "❌ Loss −X pts"
- [ ] **De-dupe guard** — check `discord_alerts` table before sending; if message ID already has an alert, send as follow-up instead
- [ ] Notification failures are caught and logged — never crash ingestion

---

## Phase 7 — Image Parsing *(deferred — needs Anthropic API key)*

- [ ] Add `ANTHROPIC_API_KEY` to `.env` and `config.py`
- [ ] **Image classifier** (`backend/vision/classifier.py`) — Claude vision API call to classify image as `chart_zone` / `mt5_screenshot` / `other`
- [ ] **Chart zone parser** — extract entry zone bounds (price range), SL estimate, TP estimate; return `ParsedSignal` with `signal_type: zone_estimated`; zone-estimated signals stored and scored separately from stated-level signals
- [ ] **MT5 screenshot parser** — extract open price, close price, open time, close time from profit screenshot
- [ ] **Screenshot cross-checker** — pull MT5 candles for the claimed period; if price never reached the stated open/close → mark `contradicted` (fabricated trade — strong red flag); if verifiable → `confirmed`; else → `unverifiable`
- [ ] Confirmed screenshots feed the **integrity score only** — never the win rate (as per CLAUDE.md: screenshots always show wins, never losses)
- [ ] Re-process backlogged `image_deferred` messages once key is added

---

## Decisions to Revisit

| Topic | Decision needed | Default assumption |
|---|---|---|
| Per-channel verification window | Some channels run multi-day swings | 48 hours; configurable per channel |
| Multi-TP signals | How to count a partial win | TP1 = win; further targets tracked as bonus |
| Zone SL/TP buffer | How much buffer when estimating from image | Conservative (tight); tune after confirmed cases |
| Mid-trade management messages | "Move SL to BE", "close half" | Out of scope for v1 — log as non-signal |
| MT5 always-on strategy | Service vs. Task Scheduler vs. manual | Decide before Phase 5 go-live |

---

## Progress Summary

| Phase | Status |
|---|---|
| 0 — Credentials | 🔲 Not started |
| 1 — Foundation | ✅ Complete |
| 2 — Dashboard (mock) | ✅ Complete |
| 3 — Core backend | 🔲 Not started |
| 4 — Telegram ingestor | 🔲 Not started |
| 5 — Wire real data | 🔲 Not started |
| 6 — Discord notifications | 🔲 Not started |
| 7 — Image parsing | ⏸️ Deferred (no API key) |
