-- Lead Finder — Postgres schema (Hybrid architecture, owner GO 2026-11-15)
-- Data model: Clay-style one row per lead. Context travels as
-- search_profile_id + profile_version on every record.
-- Sheet is the approval VIEW only; this DB is the system of record.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- A single execution of the whole pipeline
CREATE TABLE IF NOT EXISTS runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  search_profile_id UUID,
  profile_version INT,
  status TEXT NOT NULL DEFAULT 'started',  -- started|discovering|researching|scoring|staged|done|failed
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  notes TEXT
);

-- Versioned, human-approved search profile generated from business context (SF1 output)
CREATE TABLE IF NOT EXISTS search_profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  version INT NOT NULL DEFAULT 1,
  business_context JSONB NOT NULL,       -- raw user-supplied context
  profile JSONB NOT NULL,                -- machine-executable profile (keywords, locations, sources, filters, exclusions)
  rubric JSONB NOT NULL,                 -- fit + timing criteria with weights and evidence requirements
  status TEXT NOT NULL DEFAULT 'draft',  -- draft|approved|superseded
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  approved_at TIMESTAMPTZ,
  UNIQUE (id, version)
);
ALTER TABLE runs ADD CONSTRAINT runs_profile_fk
  FOREIGN KEY (search_profile_id) REFERENCES search_profiles(id);

-- One row per company (canonical lead unit)
CREATE TABLE IF NOT EXISTS companies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  search_profile_id UUID REFERENCES search_profiles(id),
  profile_version INT,
  run_id UUID REFERENCES runs(id),
  name TEXT NOT NULL,
  normalised_name TEXT NOT NULL,
  domain TEXT,
  place_id TEXT,
  registration_no TEXT,
  category TEXT,
  location TEXT,
  website TEXT,
  phone TEXT,
  rating NUMERIC,
  review_count INT,
  source TEXT NOT NULL,                  -- apify_maps|apollo|registry|inbound|manual
  source_ids JSONB NOT NULL DEFAULT '{}',
  raw_payload JSONB,
  status TEXT NOT NULL DEFAULT 'new',    -- new|deduped|researched|scored|staged|approved|rejected|suppressed
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS companies_place_id_uq ON companies (place_id) WHERE place_id IS NOT NULL;
-- Franchise rule (2026-11-15): domain uniqueness is per location, so chain branches sharing a domain stay separate companies.
CREATE UNIQUE INDEX IF NOT EXISTS companies_domain_loc_uq ON companies (lower(domain), coalesce(location,'')) WHERE domain IS NOT NULL;
CREATE INDEX IF NOT EXISTS companies_dedupe_idx ON companies (normalised_name, location);

-- Decision-makers attached to a company
CREATE TABLE IF NOT EXISTS people (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  full_name TEXT NOT NULL,
  title TEXT,
  linkedin_url TEXT,
  email TEXT,
  email_status TEXT,                     -- unknown|masked|revealed|valid|invalid|catch_all
  is_decision_maker BOOLEAN NOT NULL DEFAULT false,
  source TEXT,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS people_linkedin_uq ON people (linkedin_url) WHERE linkedin_url IS NOT NULL;

-- Dated observable triggers (timing layer input)
CREATE TABLE IF NOT EXISTS signals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
  person_id UUID REFERENCES people(id) ON DELETE CASCADE,
  signal_type TEXT NOT NULL,             -- hiring|job_change|funding|expansion|new_post|review_activity|other
  detail TEXT,
  evidence_url TEXT,
  observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  signal_date DATE,
  decay_days INT NOT NULL DEFAULT 14
);

-- Raw fetched evidence behind every research field (anti-hallucination contract)
CREATE TABLE IF NOT EXISTS research_artifacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
  person_id UUID REFERENCES people(id) ON DELETE CASCADE,
  field_name TEXT NOT NULL,
  value JSONB,                           -- {value, evidence_url, evidence_quote, observed_at, confidence} or NULL
  source_url TEXT,
  raw_content TEXT,
  critic_verdict TEXT,                   -- supported|unsupported|unchecked
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Fit and Timing stored separately, components explainable and re-computable
CREATE TABLE IF NOT EXISTS scores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  search_profile_id UUID REFERENCES search_profiles(id),
  profile_version INT,
  fit_score INT,
  fit_components JSONB,                  -- deterministic points per criterion
  llm_judgement INT,                     -- bounded 0-30
  llm_rationale TEXT,
  disqualifiers JSONB NOT NULL DEFAULT '[]',
  timing_score INT,
  timing_components JSONB,
  band TEXT,                             -- A|B|C|not_a_fit|insufficient_data
  scored_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Draft-only outreach (NO send state exists by design)
CREATE TABLE IF NOT EXISTS drafts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  person_id UUID REFERENCES people(id),
  gmail_draft_id TEXT,
  subject TEXT,
  body TEXT,
  angle TEXT,                            -- which verified hook was used
  status TEXT NOT NULL DEFAULT 'draft',  -- draft|approved|discarded
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Human approval is a data state flipped by hand
CREATE TABLE IF NOT EXISTS approvals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  decision TEXT NOT NULL,                -- approved|rejected|hold
  decided_by TEXT,
  decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  note TEXT
);

-- Every paid call recorded before/after it happens (dedupe-before-spend audit)
CREATE TABLE IF NOT EXISTS spend_ledger (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID REFERENCES runs(id),
  company_id UUID REFERENCES companies(id),
  provider TEXT NOT NULL,                -- apify|apollo|tavily|verifier|llm
  action TEXT NOT NULL,                  -- maps_search|email_reveal|research_call|verify
  cost_usd NUMERIC(10,4),
  credits NUMERIC,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Suppression / exclusion ledger (existing clients, do-not-contact, already contacted)
CREATE TABLE IF NOT EXISTS suppressions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  match_type TEXT NOT NULL,              -- domain|place_id|email|name_location
  match_value TEXT NOT NULL,
  reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (match_type, match_value)
);

-- Added 2026-11-15 (SF7): DB-level idempotency for scoring
CREATE UNIQUE INDEX IF NOT EXISTS scores_company_profile_version_uq ON scores(company_id, search_profile_id, profile_version);
