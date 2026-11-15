# Lead Discovery Architecture — dynamic, context-driven

Owner-approved framing (2026-11-15): **nothing about "who to find" is hardcoded.**
The user of the system supplies their own business context; the system derives
who to look for, where to look, and how to judge fit — from that context.
This generalises the pattern Victor already built inside a SaaS product
(LinkedIn-message intake + location/keyword discovery, scored against the
company's own service context, tested and approved there).

**Design target:** the best currently-available architecture for a
sales-lead system, chosen on evidence across all leading platforms and
practitioner builds — not a copy of any single employer's or vendor's style.
Still standing from before: (a) dynamic — any user's runtime business
context drives sourcing, research and scoring, including local businesses
by location + keyword, not only LinkedIn-first B2B; (b) all-in-one — one
system, intake → sourcing → research → scoring → approval → draft.
A deep-research + brainstorm round (best-sales-lead-architecture,
2026-11-15) decides the final shape; do not lock the design to any single
vendor's pattern before it lands.

## Build structure — sub-flows are mandatory (owner, 2026-11-15 01:24)

The system is built as an orchestrator + n8n sub-workflows (Execute
Workflow), never one giant canvas — the owner explicitly required
sub-flows so the build stays readable:

- **WF00 Orchestrator** — context form intake → calls sub-flows → ranked
  staging → approval gate → hands off to WF02/WF03
- **SF1 Search-Profile Generator** — context → strict-JSON profile +
  rubric (human reviews the profile before discovery runs)
- **SF2 Discovery — Maps/Places** (location + keyword)
- **SF3 Discovery — Apollo/LinkedIn**
- **SF4 Dedupe + Exclusion**
- **SF5 Per-Person Research + Critic** (structured fields, cited claims)
- **SF6 Contact Waterfall** (credit-gated: score first, reveal after)
- **SF7 Scoring** — Fit score + Timing score as separate outputs

Build lane: side chat "Lead Finder Build"
(chat_id b7b99ea7-b5cd-4c2f-a78a-b5552466d4bd), created 2026-11-15 at the
owner's request. Deep-research breakdown behind this structure:
~/workspace/research_notes/lead-finding-architecture-20261114-1817/report.md

## Inputs — the business context (supplied by the user)

- What the business sells / its services
- Who its customer is (in the user's own words)
- Locations / service areas
- Exclusions: existing clients, do-not-contact, already-contacted
- Optional: price range / deal size (drives the buy-ability judgement)

## Stage 0 — Context → search profile (AI-derived)

An LLM pass converts the business context into a concrete search profile:
keywords/business types, locations, which sources to use, and a scoring
rubric generated from the context. Change the context → the profile,
the sources, and the rubric all change. Nothing is fixed per industry.

## Stage 1 — Discovery (sources chosen by the context)

- **Google Maps / Places** — location + keyword; the local-business route
  (the route Victor's earlier build used, incl. Maps extraction by location)
- **Apollo** — company + decision-maker search for B2B firm targets
- **LinkedIn / Sales Navigator** — named decision-makers, growth signals
- **Official registries** — e.g. SEC IAPD for US RIAs, SEBI list for India;
  complete, free, filterable by size/location
- **Industry lists & rankings** — awards, conference lists, associations
- **Inbound** — page messages / form submissions arrive as leads too
  (the intake route of Victor's SaaS build)

## Stage 2 — Dedupe + exclusion check (before any spend)

New finds are checked against the existing list (Sheet/CRM), the exclusion
list, and existing clients. Duplicates never reach enrichment.

## Stage 3 — Profile check & free enrichment

- Business profile examined: Maps listing (category, rating, review count,
  website, photos), website content, public signals
- Apollo **free** endpoints: organisation enrichment by domain + people
  search (decision-maker titles, emails masked) — costs nothing
- Website visit for contact/about pages

## Stage 4 — Founder / decision-maker identification

The contact person is the founder or a named decision-maker (managing
partner, head of operations) — found via Apollo people search, the
business website, and LinkedIn. A lead without an identifiable
decision-maker scores low on reachability.

## Stage 5 — Buy-ability scoring vs the business context

- Scored **against the supplied business context** (the rubric from Stage 0),
  evidence-only: the scorer may only use facts found in Stages 1–4 and
  must say so when evidence is missing — never invent figures
- Free signals first (rating, reviews, has-website, category/location match)
- Output per lead: score + written reasons a human can disagree with
- **Credit gate:** paid actions (e.g. Apollo email reveal) happen ONLY for
  leads above the score threshold with a decision-maker attached

## Stage 6 — Ranked staging → human approval gate

Ranked list lands in a Sheet/CRM for human review. Nothing is contacted
automatically. A human approves a lead → outreach draft (draft only) →
follow-up discipline. This is where the existing demo workflows
(01 scoring · 02 outreach draft on approval · 03 follow-up & call notes)
take over.

## Professional reference patterns (researched 2026-11-15)

| Reference | Pattern borrowed |
|---|---|
| GitHub Mfrostbutter/n8n-workflow-templates — Apollo Lead Enrichment | Maps scrape → dedupe → free Apollo enrich → ICP score → credit-gated email reveal, monthly cap |
| n8n #11086 — Olostep Maps + decision-maker extraction | City + business type form → Maps → website scrape extracts CEO/Founder names → Sheet |
| n8n #8406 — B2B leads, any city & business type | Form inputs → AI builds the Places API query → AI agent reads websites for contacts |
| n8n #12710 — Attio enrichment | Parallel research branches (news, LinkedIn, leadership) + an LLM **critic** agent that verifies claims before output |

## Worked instances of this architecture

Two production instances were built and proven end-to-end on this design:
(1) a B2B professional-services context, where Stage 1 sources are business
registries and directories and the rubric scores firm fit for a software
platform; and (2) a local retail/services context, where Stage 1 is Google
Maps discovery and the rubric scores local businesses for an automation
service. Same code, same tables — only the runtime business context differs.

## Recommended architecture — best-of research + brainstorm (2026-11-15)

Source: internal research notes (2026-11-14/15).
(No vendor wins every layer; the autonomous AI-SDR shape was evaluated and
rejected — Anthropic's own ~15× token cost, weakest quality control.)

**HYBRID, three parts:**
- **Control plane = (B) deterministic orchestrator + sub-workflows**
  (our WF00 + SF1–SF7 shape). Cheapest, replayable, most QC choke-points,
  generalises to local (Maps) and B2B (Apollo) alike.
- **Data model = (A) Clay-style one row per lead, state in Postgres**
  (runs, search_profiles, companies, people, signals, research_artifacts,
  scores, drafts, approvals, spend_ledger). Google Sheets = the human
  approval VIEW only, never the database. CRM receives approved leads
  only. Context travels as search_profile_id + version on every record.
- **Agents = (C) fan-out ONLY inside SF5 deep research, and only for
  high-fit leads** — parallel research workers + a critic, nowhere else.

Layer best-of (documented mechanics): intake = versioned structured
search_profile, human-approved before sourcing (Breeze/Clay pattern);
discovery = multi-source router (Places gives NO emails; LinkedIn is not
a safe programmatic source — ToS/ban risk); fit = deterministic rubric
first (free signals, threshold gate, reasons stored) + bounded LLM
judgement; timing = SEPARATE score from dated observable triggers with
decay (intent data is a signal, never proof); verification = fail-closed
hop before drafting (one provider's "verified" flag is not trustworthy —
practitioner re-checks of Apollo "Verified" leads found 19% valid /
60% catch-all); drafting = only from verified fields, facts cited.
Cost model for this shape (estimates from sourced unit prices):
~$3–12 per 100 leads discovered→ranked; ~$10–35 per 100 for the fully
researched + verified + drafted subset. Credits/verification dominate;
LLM tokens are cents.
