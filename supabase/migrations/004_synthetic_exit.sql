-- 004_synthetic_exit.sql
-- Record HOW each outcome was determined, so estimated (synthetic time-horizon)
-- results stay distinct from real first-touch SL/TP verification — in scoring
-- and in the dashboard. Existing rows default to 'first_touch'.

ALTER TABLE signal_outcomes
    ADD COLUMN IF NOT EXISTS method TEXT NOT NULL DEFAULT 'first_touch';

ALTER TABLE signal_outcomes
    DROP CONSTRAINT IF EXISTS signal_outcomes_method_check;

ALTER TABLE signal_outcomes
    ADD CONSTRAINT signal_outcomes_method_check
    CHECK (method IN ('first_touch', 'synthetic_horizon'));
