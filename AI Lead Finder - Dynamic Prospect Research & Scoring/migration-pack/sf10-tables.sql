CREATE TABLE IF NOT EXISTS outreach_drafts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id text, profile_id uuid, company_id uuid NOT NULL,
  person_id uuid, person_key text, channel text NOT NULL,
  addressee text NOT NULL, targeting_reason text,
  language text NOT NULL, step int NOT NULL DEFAULT 1,
  subject text, body text NOT NULL,
  evidence_quote text, evidence_source_url text, evidence_observed_at timestamptz,
  status text NOT NULL DEFAULT 'pending_audit',
  audited_by text, audited_at timestamptz, audit_result text,
  signoff_by text, signoff_at timestamptz,
  export_key text UNIQUE, exported_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, step)
);
CREATE TABLE IF NOT EXISTS outreach_failures (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id text, profile_id uuid, company_id uuid,
  reason_codes text[], body_text text, output_hash text,
  cost_usd numeric NOT NULL DEFAULT 0,
  review_status text NOT NULL DEFAULT 'open',
  reviewed_by text, reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS outreach_suppression (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL, person_key text,
  reason text NOT NULL, created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, person_key, reason)
);
SELECT json_agg(row_to_json(t)) FROM (
  SELECT table_name FROM information_schema.tables
  WHERE table_name LIKE 'outreach%') t;
