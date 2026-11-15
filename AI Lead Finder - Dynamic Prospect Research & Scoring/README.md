# AI Lead Finder — Dynamic Prospect Research & Scoring System

A production lead-finding system built on n8n + Postgres. You describe your
own business in plain words; the system derives who to look for, where to
look, and how to score fit. Nothing about the target market is hardcoded —
the same code has run end-to-end for a B2B professional-services context and
for a local retail/services context, driven only by a different business
context at runtime.

## How it works

1. **SF1 — Search Profile Generator.** An LLM turns the business context into
   a versioned search profile: target description, sources, search queries,
   and a scoring rubric (deterministic fit criteria summing to 70 points,
   plus a bounded LLM judgement of at most 30). A human approves the profile
   before anything runs.
2. **SF2 — Discovery.** Google Maps places via Apify, run sequentially inside
   the free-plan concurrency limits, hard-bounded per run by the profile's
   own query set.
3. **SF4 — Dedupe + Exclusion.** One deterministic SQL statement checks the
   suppression ledger and existing companies before any company is inserted
   and before any downstream spend. Domain matches require the same location,
   so chain branches in different cities stay separate companies.
4. **SF7 — Scoring.** Deterministic criteria first, then a bounded,
   evidence-cited LLM judgement. Fit and timing are separate scores. A lead
   with too little data scores zero judgement points, never a guess.
5. **SF5 — Research + Critic.** For top-fit leads only: Tavily research with
   evidence-bound extraction (every field carries a source URL, a quote, and
   a confidence), then a critic pass that drops any fact it cannot support.
   Research also emits buying signals (funding, hiring, expansion) and found
   people.
6. **SF3 v2 — Decision-Maker Finder.** Two searches per company (LinkedIn
   intent + web/team intent). A person is saved only if their evidence quote
   appears word-for-word in the search results. Search-once gating means a
   company is never paid for twice.
7. **SF9 — Timing Re-Score.** One deterministic SQL recomputes every timing
   score from live signals inside each signal type's own decay window.
8. **SF8 / SF8b — Human Approval.** Ranked leads are published to a Google
   Sheet (a human view, never the database). A person marks decisions in the
   Sheet; SF8b writes them back to Postgres idempotently.
9. **ERR — Failure Handler.** Any failed run flips its run record to failed
   with the failing workflow, node, and message. Every run is a full
   observability record in the `runs` table.

**WF00** is the orchestrator that runs the stages in order with an approval
gate, per-run spend caps at every paid stage, and a spend ledger. The system
never sends anything: outreach drafts are a separate workflow, created only
after a human approval.

## Files

- `db/schema.sql` — the 11-table Postgres schema (runs, search_profiles,
  companies, people, signals, research_artifacts, scores, drafts, approvals,
  spend_ledger, suppressions). Row Level Security enabled, no public policies.
- `wf00/gen_wf00_v7.py` — orchestrator generator (n8n Workflow SDK code),
  with `example-context.json` as the replaceable business-context input.
- `sf1/` … `sf9/`, `err/` — one generator per sub-workflow.
- `sf4/sf4.sql` — the dedupe/exclusion statement, kept readable on its own.
- `LEAD-DISCOVERY-ARCHITECTURE.md` — the research and design record.

## Build and verification

Built in small, individually tested slices (Matt Pocock process: plan,
grill, small steps, two-axis review), then verified end-to-end on live runs
against a real database — final rehearsal: 75 discovered, 21 new companies
inserted and scored, 3 researched, 144 timing scores recomputed, 144 rows
published to the approval view, run closed clean. An independent final review
(Muse Wonder) returned "ready with conditions"; the one real bug it found
(franchise dedupe) was fixed and re-proven the same day.

## Setup notes

Generators emit n8n Workflow SDK code; credentials (Postgres, Google,
Tavily, Apify, LLM endpoint) are attached inside your own n8n instance and
are not part of this backup. Requires: n8n, Postgres (Supabase works),
Tavily, Apify, and any OpenAI-compatible chat endpoint.
