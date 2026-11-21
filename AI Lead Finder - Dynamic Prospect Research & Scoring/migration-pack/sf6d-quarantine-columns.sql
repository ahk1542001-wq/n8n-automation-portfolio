-- SF6d C9 (Wonder delta verdict, 2026-11-19): pool quarantine.
-- Non-business rows (listicles, article/category/directory/homepage/locator/
-- query-phrase rows) are quarantined in the DB, not merely excluded at pick,
-- so they stop re-surfacing in every SF6d batch. SF6d pick (v-next.3+)
-- enforces: AND c.quarantined_at IS NULL.
-- Idempotent.
ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS quarantined_at timestamptz,
  ADD COLUMN IF NOT EXISTS quarantine_reason text;
