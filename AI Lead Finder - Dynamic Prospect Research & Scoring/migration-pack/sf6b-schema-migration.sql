-- SF6b LinkedIn people layer — schema (applied live 2026-11-17, leadfinder project)
-- companies: LinkedIn URL + people-search state machine columns
ALTER TABLE companies ADD COLUMN IF NOT EXISTS linkedin_url text;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS linkedin_people_checked_at timestamptz;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS linkedin_people_claimed_at timestamptz;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS linkedin_people_claim_run_id text;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS linkedin_people_next_check_at timestamptz;
-- people: phone (SF6) + canonical LinkedIn URL uniqueness (SF6b, Wonder blocker)
ALTER TABLE people ADD COLUMN IF NOT EXISTS phone text;
CREATE UNIQUE INDEX IF NOT EXISTS people_linkedin_url_uq
  ON people (linkedin_url) WHERE linkedin_url IS NOT NULL;
-- Semantics (Wonder final verify 2026-11-17, ruling F-B):
-- linkedin_people_checked_at = "a LinkedIn people attempt was reconciled for this company"
-- (searched, no-page, or ambiguous) — it is NOT proof people were searched.
-- Re-eligibility is governed by linkedin_people_next_check_at (+90 days for no-page/ambiguous).
