CREATE TABLE IF NOT EXISTS people_reviews (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  person_key text NOT NULL,
  company_id uuid NOT NULL,
  full_name text NOT NULL,
  decision text NOT NULL,
  note text,
  decided_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (person_key, decision)
)
