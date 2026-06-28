-- ─── AI Intelligence Layer — Migration 003 ───────────────────────────────────
-- Run in Supabase SQL Editor after 001_initial_schema.sql and 002_enable_realtime.sql.

-- ─── Feature 1: track how each signal was parsed ─────────────────────────────
ALTER TABLE signals
    ADD COLUMN IF NOT EXISTS parse_method TEXT NOT NULL DEFAULT 'regex'
        CHECK (parse_method IN ('regex', 'ai_fallback', 'vision'));

-- Back-fill existing zone_estimated signals as vision-parsed
UPDATE signals SET parse_method = 'vision'
WHERE signal_type = 'zone_estimated' AND parse_method = 'regex';

-- ─── Feature 2: signal quality assessments ───────────────────────────────────
CREATE TABLE IF NOT EXISTS signal_quality_assessments (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id        UUID NOT NULL UNIQUE REFERENCES signals(id) ON DELETE CASCADE,
    quality_score    NUMERIC(4,3) NOT NULL CHECK (quality_score BETWEEN 0 AND 1),
    is_retrospective BOOLEAN NOT NULL DEFAULT FALSE,
    flags            TEXT[] NOT NULL DEFAULT '{}',
    explanation      TEXT,
    assessed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS sqa_signal_id ON signal_quality_assessments (signal_id);
CREATE INDEX IF NOT EXISTS sqa_retrospective ON signal_quality_assessments (is_retrospective)
    WHERE is_retrospective = TRUE;

ALTER TABLE signal_quality_assessments ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon read signal_quality_assessments"
    ON signal_quality_assessments FOR SELECT USING (true);

-- ─── Feature 3: AI edit intent analysis ──────────────────────────────────────
ALTER TABLE message_edits
    ADD COLUMN IF NOT EXISTS ai_intent TEXT
        CHECK (ai_intent IN (
            'typo_correction', 'info_addition',
            'level_adjustment', 'suspicious_adjustment'
        )),
    ADD COLUMN IF NOT EXISTS ai_suspicion_score NUMERIC(4,3)
        CHECK (ai_suspicion_score IS NULL OR
               (ai_suspicion_score >= 0 AND ai_suspicion_score <= 1)),
    ADD COLUMN IF NOT EXISTS ai_intent_notes TEXT,
    ADD COLUMN IF NOT EXISTS ai_assessed_at TIMESTAMPTZ;

-- ─── Feature 4: channel AI behavior assessments ───────────────────────────────
CREATE TABLE IF NOT EXISTS channel_ai_assessments (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id                UUID NOT NULL UNIQUE
                                  REFERENCES channels(id) ON DELETE CASCADE,
    fraud_risk_score          NUMERIC(4,3) NOT NULL
                                  CHECK (fraud_risk_score BETWEEN 0 AND 1),
    timing_score              NUMERIC(4,3) NOT NULL
                                  CHECK (timing_score BETWEEN 0 AND 1),
    edit_manipulation_score   NUMERIC(4,3) NOT NULL
                                  CHECK (edit_manipulation_score BETWEEN 0 AND 1),
    delete_manipulation_score NUMERIC(4,3) NOT NULL
                                  CHECK (delete_manipulation_score BETWEEN 0 AND 1),
    key_findings              TEXT NOT NULL,
    signals_analyzed          INTEGER NOT NULL DEFAULT 0,
    assessed_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE channel_ai_assessments ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon read channel_ai_assessments"
    ON channel_ai_assessments FOR SELECT USING (true);

-- ─── score_breakdowns: AI contribution columns ───────────────────────────────
ALTER TABLE score_breakdowns
    ADD COLUMN IF NOT EXISTS retrospective_signal_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS low_quality_signal_count   INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS suspicious_edit_count      INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS ai_behavior_penalty        NUMERIC(6,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS quality_weight_adjustment  NUMERIC(6,2) NOT NULL DEFAULT 0;
