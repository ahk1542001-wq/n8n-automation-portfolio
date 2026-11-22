# AI Lead Finder — Dynamic Prospect Research & Scoring System

A production lead-finding system built on n8n + Postgres. You describe your
own business in plain words; the system derives who to look for, where to
look, and how to score fit. Nothing about the target market is hardcoded —
the same code has run end-to-end for a B2B professional-services context and
for a local retail/services context, driven only by a different business
context at runtime.

## Current state (2026-11-22)

Canonical live heads: WF00 v-next.14 (orchestrator), SF0 v-next.13 (the
business-context planner, promoted 2026-11-21 after a golden-set campaign
scored 28/30 with zero unsafe plans), SF2 v-next.5, SF4 v-next.3,
SF7 v-next.5, SF5 v-next.7, SF6 v-next.6, SF6d v-next.3, SF9, SF8 v-next.10,
SF10 v-next.9 (outreach drafts). The full workflow exports live in
`migration-pack/`.

The system has run end to end on live data: a plan created from a plain
language business description, approved by the owner, then discovery,
dedupe, scoring, research and human approval publishing, with every cost
written to a spend ledger. Discovery is multi-source: Google Maps places,
Tavily web search and Tavily social (Facebook and TikTok), plus a manual
import path, all behind a 24 hour discovery cache. SF2 and SF4 were hardened
on 2026-11-21 against malformed unicode in provider data (lone surrogate
pairs in scraped text are stripped at each stage's data chokepoint before
any database write). Outreach stays drafts only; nothing is ever sent
automatically.

## How it works

1. **SF1 — Search Profile Generator.** An LLM turns the business context into
   a versioned search profile: target description, sources, search queries,
   and a scoring rubric (deterministic fit criteria summing to 70 points,
   plus a bounded LLM judgement of at most 30). A human approves the profile
   before anything runs.
2. **SF2 — Discovery.** Google Maps places, Tavily web search and Tavily
   social sources, hard-bounded per run by the profile's own query set and
   served through a 24 hour discovery cache.
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

## Current state (November 2026)

The build is complete and verified end to end. The live chain is WF00
v-next.14 orchestrating SF2 discovery (Google Maps plus Facebook and TikTok
social discovery, with social results quarantined until their classification
and location are verified), SF4 dedupe, SF7 scoring (now including evidenced
company-size fit), SF5 research, SF6 enrichment, SF6d people finding
(LinkedIn X-ray search via Tavily: no LinkedIn login and no platform
scraping), SF9 timing re-score and SF8 human approval publishing.

A separate planner, SF0, drafts new search profiles with an LLM and
validates every draft against a frozen registry before a human sees it.
Approving a profile is owner-only and enforced inside the workflow. The
planner passed a 30-case golden campaign (27 of 30 valid on the first pass)
with zero unsafe outputs across 12 adversarial cases. Outreach is SF10:
drafts only, written to a review sheet, never sent. Design and stage gates
were reviewed by a second model (Muse Wonder) throughout the build.

**Update, 21 November 2026:** the planner is now SF0 v-next.13, promoted to
planner head after a full review cycle. This version adds a deterministic
clarify gate (when the business context is too thin to score safely, the
system asks the owner short structured questions before spending anything)
and makes company-size fit and exclusion handling deterministic in code
rather than trusting the model's draft. It passed a frozen 50-case
evaluation (30 realistic, 20 adversarial) at 28 of 30 with zero unsafe
drafts saved; every saved draft was re-validated and every model call was
provenance-checked. The complete current workflow set, exactly as exported
from the live system, is in the `migration-pack/` folder of this case.
