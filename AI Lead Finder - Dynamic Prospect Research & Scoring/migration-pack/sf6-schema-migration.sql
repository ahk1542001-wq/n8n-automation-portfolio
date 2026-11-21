-- SF6 contact-stage schema migration (applied to the live Supabase DB on 2026-11-16).
-- Only needed for a FRESH database; the live leadfinder DB already has these columns.
-- Idempotent: safe to re-run.
ALTER TABLE companies ADD COLUMN IF NOT EXISTS facebook_url text;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS email text;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS email_source text;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS company_size text;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS size_source text;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS contact_enriched_at timestamptz;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS contact_claimed_at timestamptz;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS contact_claim_run_id text;
ALTER TABLE people ADD COLUMN IF NOT EXISTS phone text;
