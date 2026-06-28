-- Enable Supabase Realtime for the channels table.
-- This allows the dashboard overview to update live when trust scores change.
--
-- Apply via: Supabase SQL Editor → paste → Run
-- Run after 001_initial_schema.sql.

ALTER PUBLICATION supabase_realtime ADD TABLE channels;
