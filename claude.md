# CLAUDE.md — XAUUSD Telegram Signal Trust Score System

Project context and conventions for Claude Code. Human setup (accounts, credentials, installs) is done separately and documented in `IMPLEMENTATION.md` — assume those exist and read their values from `.env`.

## What we're building

A local-first tool that monitors the Telegram signal channels I've joined, verifies each signal against real XAUUSD price data, scores how trustworthy each channel is, and alerts me on Discord in real time. A dashboard surfaces the per-channel **Trust Score (0–100)** and the evidence behind it.

**Scope:** XAUUSD only. Single user (me). Runs on my Windows machine with MT5 always open.

## Why it exists

Signal channels routinely exaggerate performance — editing results after the fact, posting cherry-picked screenshots, deleting losers. The point of this system is to replace their claims with **independently verified** outcomes, so I can tell which channels are actually worth following. Honesty of measurement is the whole product; if the system can't be trusted, it's worthless.

## How it works (pipeline)

1. **Ingest** — a Telegram user-client listens to my joined channels and records every message, **including edits and deletes** (the tampering signal). It also backfills history.
2. **Parse** — turn each message into a structured signal. Text via parsing rules; images via the Claude vision API.
3. **Notify** — the moment a forward signal is parsed, send a Discord alert (see Notifications).
4. **Verify** — for each signal, pull XAUUSD 1-minute candles from my MT5 terminal covering the time after it posted, and determine the real outcome (which of SL/TP was hit first, and by how many points).
5. **Score** — aggregate verified outcomes plus integrity metrics into a per-channel Trust Score and verdict.
6. **Present** — a dashboard shows the table of channels and a detail view with the evidence.

## Message types to handle

The system must distinguish four kinds of post; this distinction drives parsing, verification, and scoring:

- **Text signal** — e.g. "BUY 2650, SL 2645, TP 2660". Fully verifiable.
- **Chart + zone image** — a chart screenshot with a colored entry zone and a buy/sell instruction. Vision estimates the zone bounds as an entry range; SL/TP come from accompanying text if present, otherwise are estimated conservatively. These are **zone-estimated** signals and must be kept visibly separate from signals with stated levels — never let estimates inflate a channel's stated-signal record.
- **MT5 profit screenshot** — a closed-trade screenshot showing a win. This is a _claim about a past trade_, not a forward signal. Vision extracts the open/close prices and times; the system cross-checks them against price data to mark the claim **confirmed**, **contradicted** (price never went there → fabricated, a serious red flag), or **unverifiable**. **A screenshot only ever shows a winner, sometimes the losses**.
- **Non-signal** — commentary, hype, charts with no levels. Logged for transparency, not scored.

## Verification principles

- Price truth comes from **my MT5 terminal** (the `MetaTrader5` package), 1-minute candles. This reflects the prices I'd actually trade; outcomes may differ from other brokers and that's intentional.
- An outcome is decided by **first touch**: walking candles forward from the post time, whichever of stop-loss or take-profit is reached first. Require the entry to actually fill before counting a result.
- Be honest about uncertainty: when a single candle spans both SL and TP, the intra-candle order is unknown — resolve conservatively (assume the loss) and record that it was ambiguous.
- Outcomes are scored in **points** (raw XAUUSD price difference); fix the exact definition in config.
- Unresolved signals are re-checked on a schedule until they resolve or a time window expires.

## Trust Score principles

The score is a means to an honest judgment, not a vanity metric. Build it so that:

- **Verified outcomes drive it** — win rate, points, risk/reward, expectancy, all from independently verified results, not the channel's claims.
- **Sample size matters** — a high win rate over a handful of signals is not skill; small samples must not earn high scores.
- **Integrity is weighted heavily** — editing levels after price has already moved past them, deleting losers, and contradicted screenshots are strong negative signals and should be able to cap an otherwise good score.
- **Estimated and backfilled data count for less** — zone-estimated signals and history captured before live listening are less certain than live, stated signals; weight and label them accordingly.
- **The score must be explainable** — every number should trace back to its inputs in the dashboard. No black box. Prefer a transparent, tunable formula over something opaque.
- Map the final score to a plain verdict (roughly: avoid / observe / use with caution / trusted), with the thresholds configurable.

## Notifications (Discord)

- Alert me on Discord **the moment a forward signal is parsed**, before verification (verification finishes too late to be actionable).
- **All tracked channels alert**, with no score filter — but each alert shows the channel's current Trust Score and verdict so I can judge it at a glance. Color the alert by verdict.
- **Only forward signals alert** (text and zone). Profit screenshots and backfilled history do **not** alert.
- Send via a **Discord bot** (richer than a webhook: supports threaded follow-ups and, later, buttons). Keep the sending logic behind a small interface so another channel (Telegram, email) could be added without touching the pipeline.
- **Follow-ups** for the same signal post as threaded replies under the original alert: fire one if the source message is later **edited** (show old → new levels — this is my real-time tampering tripwire) or **deleted**, and optionally when it finally resolves (win/loss + points).
- De-dupe so a message never alerts twice; an edit is a follow-up, not a new alert. A notification failure must never crash ingestion or parsing.

## Dashboard

- A sortable table: one row per channel with Trust Score, verdict, verified win rate, sample size, total points, average risk/reward, edited/deleted counts, screenshot confirmed/contradicted, and last signal time.
- A channel detail view: the score broken down by factor (so I can see _why_); separate tabs for stated-text signals, zone-estimated signals, screenshots, and non-signal posts; full signal history with each signal's parsed levels, verified outcome, and an **edit-history timeline** (original → each edit, timestamped); and a flags panel for red flags.
- A clear disclaimer: scores reflect past, broker-specific verification only and are not trading advice.

## Conventions & guardrails

- **Stack:** Python for ingestion/verification/scoring/API; the Claude vision API for images; Supabase to start; Next.js + shadcn/ui for the dashboard. Choose specific libraries and structure as you see fit, but keep modules small and independently testable.
- **Build the price verifier first and prove it** against signals with known outcomes before building anything else. It's the riskiest component; everything downstream depends on it being correct.
- **Preserve full message history** — never overwrite a message or its edits; the audit trail is load-bearing for fraud detection.
- **Keep the data streams separated** in storage and scoring: stated vs. estimated, live vs. backfilled, forward-signal vs. screenshot-claim. Don't pool them blindly.
- **Secrets** live only in `.env` (already gitignored); the Telegram session file is as sensitive as a password. Never commit either. Never print secrets.
- **Fail safe:** verification needs MT5 open and connected — handle its absence gracefully with retries and a heads-up, never silent wrong answers.
- **Configurable, not hard-coded:** symbol name, verification window, point definition, score weights and thresholds all belong in config so I can tune them.
- Read `IMPLEMENTATION.md` for what the human (me) has set up and which credentials exist.

## Decisions still open (raise these when relevant)

- Per-channel verification window (some channels run multi-day swings).
- Multi-target signals: treat first target as the win by default; track further targets as extra.
- Mid-trade management messages ("move SL to breakeven", "close half") — out of scope for v1.
- The buffer used when estimating SL/TP for zone-only signals — start conservative, tune against confirmed cases.
