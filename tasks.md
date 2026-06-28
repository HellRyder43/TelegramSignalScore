# XAUUSD Signal Trust Score — Development Tracker

> **Build order:** Dashboard (mock data) → Core backend → Telegram ingestor → Wire real data → Discord notifications → Image parsing (deferred)
> **Database:** Supabase Cloud (PostgreSQL) | **Frontend:** Next.js 14 + shadcn/ui + Tailwind CSS | **Backend:** Python + FastAPI

---

## Phase 0 — Environment & Credentials _(human tasks — do these before any code runs)_

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
- [x] Responsive layout _(dark mode skipped — white/minimalist only per design preference)_

---

## Phase 3 — Core Backend

> Build and **prove** the verifier before anything else goes live.

- [x] **MT5 price verifier** (`backend/verifier.py`)
  - Connect to local MT5 terminal via `MetaTrader5` package
  - Fetch 1-minute candles from signal post time to `now` (or verification window end)
  - Walk candles forward: first touch of SL → loss; first touch of TP → win
  - Require entry fill: skip candles before price reaches entry level
  - Ambiguity rule: single candle spans both SL and TP → mark as `ambiguous_loss`, flag it
  - Return: outcome (`win` / `loss` / `ambiguous_loss` / `unresolved`), points, candles inspected
  - Graceful failure: if MT5 is closed/disconnected, raise a typed error — never return a silent wrong answer
- [x] **Verifier test suite** (`tests/test_verifier.py`)
  - At least 3 signals with known outcomes (known from live trading history)
  - Test: clean win, clean loss, ambiguous candle, entry never filled, MT5 offline
- [x] **Text signal parser** (`backend/parser.py`)
  - Regex + rule-based: extract direction (BUY/SELL), entry, SL, TP (supports multiple TP levels)
  - Multi-TP: treat TP1 as primary win target; record further targets as extras
  - Return structured `ParsedSignal` with confidence score
- [x] **Trust score calculator** (`backend/scorer.py`)
  - Inputs: verified outcomes, edit/delete counts, screenshot verdicts, sample size, backfill flags
  - Components: win rate component, expectancy component, R:R component, integrity penalty, sample-size dampener
  - Stated and zone-estimated signals weighted separately; backfilled data weighted less
  - Every component exposed individually (for the dashboard breakdown)
  - All weights and thresholds read from `config.py`
- [x] **FastAPI app** (`backend/api/`)
  - `GET /channels` — overview list with current scores
  - `GET /channels/{id}` — detail with score breakdown and signal history
  - `GET /channels/{id}/signals` — paginated signal list with outcomes and edit history
  - `POST /verify/run` — manually trigger verification pass (for testing)
- [x] **Verification scheduler** — background task that re-checks `unresolved` signals every N minutes; marks expired if verification window passes

---

## Phase 4 — Telegram Ingestor

- [x] **Channel picker script** (`scripts/list_channels.py`) — connect as user, print all joined channels + IDs so you can choose which to track
- [x] **Live listener** (`backend/ingestor.py`)
  - Telethon user-client, connects with `api_id` + `api_hash`
  - Event handlers: `NewMessage`, `MessageEdited`, `MessageDeleted`
  - On new message: write to `messages`, classify type, trigger parser
  - On edit: append to `message_edits` (never overwrite); if a signal's levels changed post-post-time → flag as integrity violation
  - On delete: mark in `messages`; if it was a signal → flag as deleted-signal integrity event
- [x] **Backfill** (`scripts/backfill.py`) — pull channel history up to configurable message limit; mark all as `source: backfill` (weighted less in scoring)
- [x] **Message classifier** (`classify_message` in `backend/parser.py`) — routes to: `text_signal` / `zone_image` / `mt5_screenshot` / `non_signal` / `image_deferred`
  - Images with no Anthropic key → `image_deferred`; parseable captions classified as `text_signal` regardless of image

---

## Phase 5 — Wire Dashboard to Real Data

- [x] Replace `mock-data.ts` with real Supabase queries in Next.js server components
  - `frontend/src/lib/supabase/queries.ts` — `getChannels()` and `getChannelDetail(id)`
  - `frontend/src/lib/transforms.ts` — coerces Supabase NUMERIC strings → JS numbers
  - Both pages now import from `queries.ts`; `mock-data.ts` kept but no longer used by pages
- [x] Supabase Realtime subscription on `channels` table → overview table updates live without refresh
  - `frontend/src/components/channels-realtime.tsx` — client component wrapping the table
  - `supabase/migrations/002_enable_realtime.sql` — enables Realtime publication (run in SQL Editor)
- [ ] Run full end-to-end: Telegram message → parsed signal → verified outcome → updated Trust Score → dashboard reflects it
- [ ] Stress test: backfill a channel with 50+ messages, confirm scores are correct

---

## Phase 6 — Discord Notifications

- [x] **Discord bot** (`backend/notifier/discord_bot.py`)
  - `Notifier` base class with `close()` default no-op; `DiscordNotifier` fully implemented
  - REST-only (no gateway): `discord.Client.login()` then `fetch_channel()` / `send()`
- [x] **Signal alert embed**
  - Embed: channel name, BUY/SELL direction, Entry/Zone, SL, TP1-3, Trust Score + verdict in footer
  - Embed color matches verdict (green/amber/orange/red)
  - Fires immediately on signal parse via `_on_new_message`; before verification
- [x] **Threaded follow-ups** (Discord threads on the original alert message)
  - Edit follow-up: "⚠️ Signal levels changed" with before/after code blocks + timestamp
  - Delete follow-up: "🗑️ Signal deleted"
  - Resolution follow-up: "✅ Win +X pts" / "❌ Loss" / "⚠️ Ambiguous loss" — fired from verification loop
  - Thread ID persisted to `discord_alerts.discord_thread_id` on first follow-up
- [x] **De-dupe guard** — `discord_alerts` checked before each signal alert; signal never fires twice
- [x] Notification failures are caught and logged — never crash ingestion or verification

---

## Phase 7 — Image Parsing

- [x] `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` already in `config.py`; set the key in `.env`
- [x] **Image classifier** (`backend/vision/classifier.py`) — classifies image as `chart_zone` / `mt5_screenshot` / `other` using Claude vision
- [x] **Chart zone parser** (`backend/vision/chart_parser.py`) — extracts direction, entry zone bounds, SL, TP; returns `ParsedSignal(signal_type="zone_estimated")`; validates zone width and directional sanity
- [x] **MT5 screenshot parser** (`backend/vision/screenshot_parser.py`) — extracts direction, open/close price, open/close time; returns `ScreenshotData`
- [x] **Screenshot cross-checker** (`backend/vision/screenshot_checker.py`) — pulls MT5 M1 candles; if open price never traded → `contradicted`; both prices reached → `confirmed`; otherwise → `unverifiable`
- [x] Screenshots feed `channels.screenshot_confirmed / screenshot_contradicted` for integrity score only; no `signal_outcomes` row created for screenshots
- [x] **Reprocess script** (`scripts/reprocess_images.py`) — reprocesses all `image_deferred` messages; fetches media from Telegram, classifies, parses, inserts signals/claims
- [x] Ingestor updated: vision-classifies images before DB insert; handles `zone_image` and `mt5_screenshot` paths inline

---

## Decisions to Revisit

| Topic                           | Decision needed                            | Default assumption                               |
| ------------------------------- | ------------------------------------------ | ------------------------------------------------ |
| Per-channel verification window | Some channels run multi-day swings         | 48 hours; configurable per channel               |
| Multi-TP signals                | How to count a partial win                 | TP1 = win; further targets tracked as bonus      |
| Zone SL/TP buffer               | How much buffer when estimating from image | Conservative (tight); tune after confirmed cases |
| Mid-trade management messages   | "Move SL to BE", "close half"              | Out of scope for v1 — log as non-signal          |
| MT5 always-on strategy          | Service vs. Task Scheduler vs. manual      | Decide before Phase 5 go-live                    |

---

## Progress Summary

| Phase                     | Status                                     |
| ------------------------- | ------------------------------------------ |
| 0 — Credentials           | 🔲 Not started                             |
| 1 — Foundation            | ✅ Complete                                |
| 2 — Dashboard (mock)      | ✅ Complete                                |
| 3 — Core backend          | ✅ Complete                                |
| 4 — Telegram ingestor     | ✅ Complete                                |
| 5 — Wire real data        | ✅ Complete (e2e test pending credentials) |
| 6 — Discord notifications | ✅ Complete                                |
| 7 — Image parsing         | ✅ Complete (activate by setting ANTHROPIC_API_KEY in .env) |
