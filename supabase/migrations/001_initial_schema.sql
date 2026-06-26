-- ─── XAUUSD Signal Trust Score — Initial Schema ──────────────────────────────
-- Run against your Supabase project via the SQL editor or Supabase CLI.
-- All timestamps are TIMESTAMPTZ (UTC). IDs are UUID v4.
-- Never DELETE rows; mark them deleted with boolean flags.

-- ─── channels ─────────────────────────────────────────────────────────────────
CREATE TABLE channels (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id             BIGINT UNIQUE NOT NULL,
    name                    TEXT NOT NULL,
    username                TEXT,
    member_count            INTEGER,

    -- Computed by scorer.py; stored for dashboard reads
    trust_score             INTEGER NOT NULL DEFAULT 0,
    verdict                 TEXT NOT NULL DEFAULT 'observe'
                                CHECK (verdict IN ('avoid', 'observe', 'caution', 'trusted')),

    -- Aggregate stats (denormalized for fast table queries; recomputed by scorer)
    verified_win_rate       NUMERIC(5,4),       -- 0.0000 – 1.0000
    sample_size             INTEGER NOT NULL DEFAULT 0,
    total_points            NUMERIC(10,2) NOT NULL DEFAULT 0,
    avg_risk_reward         NUMERIC(6,2),
    edit_count              INTEGER NOT NULL DEFAULT 0,
    delete_count            INTEGER NOT NULL DEFAULT 0,
    screenshot_confirmed    INTEGER NOT NULL DEFAULT 0,
    screenshot_contradicted INTEGER NOT NULL DEFAULT 0,
    last_signal_at          TIMESTAMPTZ,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── messages ─────────────────────────────────────────────────────────────────
-- Immutable raw record of every message received. Never overwrite.
CREATE TABLE messages (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id              UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    telegram_message_id     BIGINT NOT NULL,
    content                 TEXT,
    message_type            TEXT NOT NULL
                                CHECK (message_type IN (
                                    'text_signal', 'zone_image', 'mt5_screenshot',
                                    'non_signal', 'image_deferred'
                                )),
    source                  TEXT NOT NULL DEFAULT 'live'
                                CHECK (source IN ('live', 'backfill')),
    is_deleted              BOOLEAN NOT NULL DEFAULT FALSE,
    posted_at               TIMESTAMPTZ NOT NULL,
    ingested_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (channel_id, telegram_message_id)
);

CREATE INDEX messages_channel_posted ON messages (channel_id, posted_at DESC);
CREATE INDEX messages_type ON messages (message_type);

-- ─── message_edits ────────────────────────────────────────────────────────────
-- Full audit trail. One row per edit event. Never update or delete rows.
CREATE TABLE message_edits (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id          UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    channel_id          UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    edit_number         INTEGER NOT NULL,       -- 1 = first edit, 2 = second, …
    content_before      TEXT NOT NULL,
    content_after       TEXT NOT NULL,
    edited_at           TIMESTAMPTZ NOT NULL,
    -- TRUE when levels changed after price had already moved past them
    is_post_move_edit   BOOLEAN NOT NULL DEFAULT FALSE,

    UNIQUE (message_id, edit_number)
);

CREATE INDEX message_edits_message ON message_edits (message_id);

-- ─── signals ──────────────────────────────────────────────────────────────────
-- Parsed forward signals (text-stated or zone-estimated).
-- Kept separate from screenshots and non-signals.
CREATE TABLE signals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id      UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    message_id      UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,

    signal_type     TEXT NOT NULL CHECK (signal_type IN ('text', 'zone_estimated')),
    source          TEXT NOT NULL CHECK (source IN ('live', 'backfill')),
    direction       TEXT NOT NULL CHECK (direction IN ('BUY', 'SELL')),

    -- Exact entry for text signals; NULL for zone_estimated
    entry           NUMERIC(10,2),
    -- Zone bounds for zone_estimated signals; NULL for text
    entry_low       NUMERIC(10,2),
    entry_high      NUMERIC(10,2),

    stop_loss       NUMERIC(10,2),
    take_profit_1   NUMERIC(10,2),
    take_profit_2   NUMERIC(10,2),
    take_profit_3   NUMERIC(10,2),

    raw_text           TEXT NOT NULL,
    parsed_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    posted_at          TIMESTAMPTZ NOT NULL,
    confidence         NUMERIC(4,3) NOT NULL DEFAULT 0,  -- 0.000 – 1.000
    resolution_status  TEXT NOT NULL DEFAULT 'unresolved'
                           CHECK (resolution_status IN ('unresolved', 'win', 'loss', 'ambiguous_loss'))
);

CREATE INDEX signals_channel_posted ON signals (channel_id, posted_at DESC);
CREATE INDEX signals_unresolved ON signals (channel_id)
    WHERE resolution_status = 'unresolved';

-- ─── signal_outcomes ──────────────────────────────────────────────────────────
-- MT5-verified result for each signal. One row per signal (1:1 after resolution).
CREATE TABLE signal_outcomes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id       UUID NOT NULL UNIQUE REFERENCES signals(id) ON DELETE CASCADE,

    outcome         TEXT NOT NULL
                        CHECK (outcome IN ('win', 'loss', 'ambiguous_loss', 'unresolved')),
    points          NUMERIC(10,2),      -- signed: positive = win, negative = loss
    candles_walked  INTEGER,            -- how many M1 candles were inspected
    verified_at     TIMESTAMPTZ,
    is_ambiguous    BOOLEAN NOT NULL DEFAULT FALSE,
    notes           TEXT
);

-- Keep signals.resolution_status in sync with signal_outcomes.outcome
CREATE OR REPLACE FUNCTION sync_resolution_status()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    UPDATE signals SET resolution_status = NEW.outcome WHERE id = NEW.signal_id;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_sync_resolution_status
AFTER INSERT OR UPDATE OF outcome ON signal_outcomes
FOR EACH ROW EXECUTE FUNCTION sync_resolution_status();

-- ─── screenshot_claims ────────────────────────────────────────────────────────
-- MT5 profit screenshots posted by a channel. Cross-checked for fabrication.
-- Confirmed screenshots feed integrity scoring ONLY — never win rate.
CREATE TABLE screenshot_claims (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id          UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    message_id          UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,

    claimed_direction   TEXT CHECK (claimed_direction IN ('BUY', 'SELL')),
    claimed_open        NUMERIC(10,2),
    claimed_close       NUMERIC(10,2),
    claimed_profit_pts  NUMERIC(10,2),
    claimed_open_time   TIMESTAMPTZ,
    claimed_close_time  TIMESTAMPTZ,

    verdict             TEXT NOT NULL DEFAULT 'unverifiable'
                            CHECK (verdict IN ('confirmed', 'contradicted', 'unverifiable')),
    posted_at           TIMESTAMPTZ NOT NULL,
    notes               TEXT
);

-- ─── score_breakdowns ─────────────────────────────────────────────────────────
-- Per-channel score breakdown, recomputed by scorer.py. Stored for dashboard reads.
CREATE TABLE score_breakdowns (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id              UUID NOT NULL UNIQUE REFERENCES channels(id) ON DELETE CASCADE,

    win_rate_component      NUMERIC(6,2) NOT NULL DEFAULT 0,    -- 0–40
    rr_component            NUMERIC(6,2) NOT NULL DEFAULT 0,    -- 0–25
    expectancy_component    NUMERIC(6,2) NOT NULL DEFAULT 0,    -- 0–20
    raw_performance         NUMERIC(6,2) NOT NULL DEFAULT 0,
    sample_weight           NUMERIC(5,4) NOT NULL DEFAULT 0,    -- 0.0–1.0
    adjusted_performance    NUMERIC(6,2) NOT NULL DEFAULT 0,
    integrity_score         NUMERIC(6,2) NOT NULL DEFAULT 25,   -- 0–25
    final_score             NUMERIC(6,2) NOT NULL DEFAULT 0,

    -- Detail fields (snapshot of inputs used in this computation)
    win_rate_pct            NUMERIC(6,2),
    total_verified          INTEGER NOT NULL DEFAULT 0,
    wins                    INTEGER NOT NULL DEFAULT 0,
    losses                  INTEGER NOT NULL DEFAULT 0,
    ambiguous               INTEGER NOT NULL DEFAULT 0,
    avg_points_per_trade    NUMERIC(10,2),
    avg_risk_reward         NUMERIC(6,2),
    edit_count              INTEGER NOT NULL DEFAULT 0,
    post_move_edit_count    INTEGER NOT NULL DEFAULT 0,
    delete_signal_count     INTEGER NOT NULL DEFAULT 0,
    contradicted_screenshot_count INTEGER NOT NULL DEFAULT 0,
    backfill_signal_count   INTEGER NOT NULL DEFAULT 0,
    live_signal_count       INTEGER NOT NULL DEFAULT 0,

    computed_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── discord_alerts ───────────────────────────────────────────────────────────
-- Sent Discord message IDs for de-duplication. One row per notification sent.
CREATE TABLE discord_alerts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id           UUID REFERENCES signals(id) ON DELETE SET NULL,
    message_id          UUID REFERENCES messages(id) ON DELETE SET NULL,
    discord_message_id  TEXT NOT NULL,
    discord_thread_id   TEXT,   -- populated after the first follow-up creates a thread
    alert_type          TEXT NOT NULL
                            CHECK (alert_type IN ('signal', 'edit', 'delete', 'resolution')),
    sent_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX discord_alerts_signal ON discord_alerts (signal_id);
CREATE INDEX discord_alerts_message ON discord_alerts (message_id);

-- ─── Row-level security (RLS) ─────────────────────────────────────────────────
-- The backend uses the service role key (bypasses RLS).
-- The frontend uses the anon key; enable RLS + read-only policies below.

ALTER TABLE channels ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE message_edits ENABLE ROW LEVEL SECURITY;
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE signal_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE screenshot_claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE score_breakdowns ENABLE ROW LEVEL SECURITY;
ALTER TABLE discord_alerts ENABLE ROW LEVEL SECURITY;

-- Allow anon key to read everything (dashboard is single-user; tighten if needed)
CREATE POLICY "anon read channels"         ON channels         FOR SELECT USING (true);
CREATE POLICY "anon read messages"         ON messages         FOR SELECT USING (true);
CREATE POLICY "anon read message_edits"    ON message_edits    FOR SELECT USING (true);
CREATE POLICY "anon read signals"          ON signals          FOR SELECT USING (true);
CREATE POLICY "anon read signal_outcomes"  ON signal_outcomes  FOR SELECT USING (true);
CREATE POLICY "anon read screenshot_claims" ON screenshot_claims FOR SELECT USING (true);
CREATE POLICY "anon read score_breakdowns" ON score_breakdowns  FOR SELECT USING (true);
CREATE POLICY "anon read discord_alerts"   ON discord_alerts    FOR SELECT USING (true);
