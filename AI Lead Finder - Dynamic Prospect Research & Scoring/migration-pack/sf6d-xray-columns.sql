-- SF6d X-Ray stage — companies columns (idempotent; applied live 2026-11-19 via one-off workflow KRd0ZU6PpzY7TFyk, exec 1027)
ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS xray_people_checked_at timestamptz,
  ADD COLUMN IF NOT EXISTS xray_people_claimed_at timestamptz,
  ADD COLUMN IF NOT EXISTS xray_people_claim_run_id text,
  ADD COLUMN IF NOT EXISTS xray_people_next_check_at timestamptz;

-- SF6d v-next.2 (Wonder C1): selection_audit may record listicle exclusions.
ALTER TABLE selection_audit DROP CONSTRAINT IF EXISTS selection_audit_selection_reason_check;
ALTER TABLE selection_audit ADD CONSTRAINT selection_audit_selection_reason_check
  CHECK (selection_reason = ANY (ARRAY['selected'::text, 'cap_reached'::text, 'below_cutoff'::text, 'research_once_skip'::text, 'listicle_excluded'::text]));
