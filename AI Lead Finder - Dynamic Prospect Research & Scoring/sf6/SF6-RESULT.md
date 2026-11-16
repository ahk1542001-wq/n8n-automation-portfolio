# SF6 Contact Stage — Result Record (2026-11-16)

## What was built

**SF6 Contact Waterfall** — a new stage in the Lead Finder chain, called by WF00 between SF3 and SF9. For each scored company (fit ≥ contact_min_fit, not yet contact-enriched, atomically claimed):

1. **Free layer (Tavily):** Facebook-page search + website/contact-page extract. Deterministic parsers store a Facebook page only on a distinctive name-token match, an email only if it appears verbatim in fetched page text, and a company size only if the page states it ("42 employees", "team of 12", "120 rooms"). Nothing is guessed.
2. **Provider layer (Apollo.io, org enrichment only):** when enabled and the company has a real domain and is still missing email or size, one enrich call fills ONLY empty fields — Facebook URL, employee count (size_source='apollo'), phone. People search/email reveal via Apollo is NOT wired; people remain SF3's job.
3. **Guards:** per-run spend cap checked before any paid call (estimate $0.026/company with provider, $0.016 without); every charge written to cost_ledger with idempotency keys (`sf6:search:` / `sf6:extract:` / `sf6:apollo:` per run+company); selection_audit rows for the pick; contact claim goes stale after 1 hour.

**Sheet (SF8):** Lead Review gained Phone / Facebook / Email / Size columns and a Yangon → Mandalay → Bangkok → other ordering within each publish batch; a People tab shows each published company's people (name, position, LinkedIn, phone, email). Phones are written apostrophe-prefixed because the Sheets node parses a leading '+' as a formula (proven by micro-test; 32 poisoned `#ERROR!` cells from the first attempt were repaired in place).

## Final versions (promoted 2026-11-16)

| Piece | Version | ID |
|---|---|---|
| SF6 Contact Waterfall | **v-next.5 (fill guards)** | `Zsyn7ll08Pwnlev4` |
| SF8 Approval View Sync | **v-next.7 (lead_key + person_key)** | `LLC5d5PKOS2zT5hi` |
| SF8b Write-Back | v-next.2 (unchanged) | `NiEtMVkvLJFO3kG6` |
| WF00 Orchestrator (canonical head) | **v-next.6** | `m8PTjpUO9Ku574U0` |
| Rollback head | WF00 v-next.3 | `dqdCOOVFUWzdBwPU` |
| Live fallback | WF00 v8 | `JjlZzT2Ao5jnnfDs` |

WF00 v-next.6 chain: … SF3 → **SF6 v-next.5** → SF9 → **SF8 v-next.7** → Close. Stage Context defaults: contact_min_fit 30, max_contact_companies 10, contact_provider_enabled **true** (enabled because FIX-1 passed).

## Wonder review (REV execution 569) — READY WITH CONDITIONS, all gates closed

### FIX-1(a) Apollo positive path — PROVEN in situ (after two real defects were found and fixed)

- **Defect 1 — `new URL` in a Code node.** SF6 v-next → v-next.3 reported provider_used=0 on every live run while a standalone Apollo test workflow returned real org data. A branch-capture diagnostic clone proved the items reached the provider gate with `domain=""`: the `domainOf()` helper used the `URL` global, which does not exist in n8n's Code-node sandbox, so it threw and returned '' for every website. Fixed in **v-next.4** with pure string parsing (no URL global). Harness: shopify.com ✓, grab.com ✓, bare domain ✓, facebook.com host excluded ✓.
- **Defect 2 — item-level fill guard.** In the v-next.4 proof run, company a3's preset size ('9999') was overwritten by Apollo's value (7100): the Save SQL trusted the item's view of the world, not the database's. Fixed in **v-next.5**: facebook_url / email / company_size (+ their source columns) are now filled **only when the DB value is empty**, enforced in SQL in both Save branches (phone was already DB-guarded). pglast-validated.
- **Proof run (SF6 v-next.5, execution 598, run f8000000-…-f4, 3 synthetic companies, deleted after):**
  - a1 (shopify.com, all empty): fb = facebook.com/gadgetflow, size = 7600 (apollo), phone = +1 613-241-2828 — exactly Apollo's record, matching an independent micro-workflow read of the same domain.
  - a2 (grab.com, phone preset '+66 2 000 0000'): fb = facebook.com/Grab, size = 13000 (apollo), **preset phone NOT overwritten**.
  - a3 (agoda.com, email + size presets): **both presets intact** (size stayed '9999'/website), fb left empty (Apollo has no FB for Agoda).
  - cost_ledger for the run: search 3, extract 3, apollo 3 — exact reconciliation (3 picked, 3 with websites, 3 org-present responses).

### FIX-1(b) Parser fixture test — PASSED 8/8

The live Parse Contacts JS was run in a Node harness: verbatim email lands with source; stated size lands ("42 employees", "team of 12"); Facebook page matched on name; blank text leaves everything blank; noreply@ skipped; placeholders skipped.

### FIX-2 Lead Review single composite key — DONE (SF8 v-next.7)

- Root defect (found on People first): the Sheets appendOrUpdate node, given a batch where multiple rows share the first matching column's value, overwrites/appends wrongly. People was fixed in v-next.6 with `person_key`; Lead Review got the same treatment in v-next.7 with `lead_key = run_id|company_id` as the ONLY matching column.
- Sheet migration done in place: `lead_key` header added (column R) and backfilled for all 282 existing rows before the first v7 publish.
- **Verification:** re-publish of run 51ae0039 (45 companies) — row count stable, **45/45 rows content-identical to the DB across all 18 columns, 0 mismatches**, Decision/Note cells untouched. The publish also restored one company (Aung Nan Taw Store) that the old v-next.5 defect had silently dropped; one exact-duplicate legacy row (Aung Tagon) was removed. Sheet now: 282 data rows, no duplicate keys, no missing keys.
- SF8b regression re-run against the 18-column layout: PASSED (decision + note written back correctly; test approval row and cells cleaned up after).

### FIX-3 Promoted-composition E2E — PASSED (with one composition defect found and fixed)

- **Cap-block test (SF6 v-next.5, run f8000000-…-f5, cap $0.01 < estimate):** charges = 0, estimates = 0; one `cap_blocked` ledger row per picked company (sum = the blocked estimate); the 3 picked companies stayed claimed under that run with contact_enriched_at NULL (claims go stale after 1h and the companies remain eligible — no spend, no loss).
- **E2E #1 (WF00 v-next.5, run b20550e7):** all stages completed (SF6 enriched 6; audit 48; cost rows 19; SF6 ledger reconciles: search 6 = picked, extract 0 = no-website pool, apollo 0 = no domains) BUT the run stayed 'started': with zero newly inserted companies, SF8's Load returned 0 rows and its internal chain starved, so WF00's Close Run never executed. **Fixed in WF00 v-next.6** (`alwaysOutputData: true` on the SF9 and SF8 call nodes). Run b20550e7's status was corrected to 'done' manually with the reason recorded in its notes.
- **E2E #2 (WF00 v-next.6, run 67149902):** status **done**, finished_at set, under the exact conditions that starved E2E #1 (cache-hit discovery, 0 inserts). SF6's pick was empty by then (the FYF-Yangon fit≥30 unenriched pool was exhausted by the earlier runs) and the stage exited cleanly.
- **Ordering note (FIX-3a):** city ordering is **per publish batch** — each batch is written Yangon → Mandalay → Bangkok → other, but appendOrUpdate never re-sorts rows already in the sheet, so the sheet as a whole is in append order. Recorded for the owner's acceptance (Wonder allowed this alternative).

## Documented anomalies and known cosmetic items (no backfills, per Wonder Q1)

1. **Run-A ledger gap (SF6 v-next.2, run f7000000-…-002):** the summary reported extract/apollo activity but cost_ledger held only the search rows. Accepted by Wonder as a documented, superseded anomaly. No ledger rows were backfilled. (The v-next.3 integer-flag + Merge-pairing fixes made every later run reconcile exactly; the Apollo branch's real root cause turned out to be Defect 1 above, found during FIX-1.)
2. **Empty-pick ledger label:** when SF6's pick is empty, the shared false-path node writes ONE `cap_blocked` cost_ledger row with a blank company_id (cost = the $0.016 base estimate). The stage summary distinguishes the cases (`empty_run` vs `cap_blocked` flags); the ledger event name alone does not. Cosmetic; not worth a version bump.
3. **Blocked-estimate constant:** true cap blocks record $0.016/company in the cap_blocked rows even when the provider-aware estimate ($0.026) drove the gate decision. The gate arithmetic itself uses the correct provider-aware figure.
4. **people.phone is blank by design for now (FIX-4):** the column exists and the People tab shows it, but no workflow writes it — SF3 does not collect phone numbers and Apollo people data is not wired. The company Phone on Lead Review is the working contact route. Owner acceptance to be recorded.
5. **Decision-maker yield stays low:** SF3 found 1 person across the two WF00 smoke/E2E runs (a Social Media Executive, not an owner). This is the known SF3 limitation, unchanged by SF6.

## Cleanup performed

- 22 test/superseded workflows archived (SF6 v-next…v-next.4, SF8 v-next.5/.6, WF00 v-next.4/.5, both drivers, both probes, DIAG, 3 MICROs, 6 Apollo tests). 28 workflows remain visible: the v8 fallback stack, the v-next.3 rollback stack, the promoted v-next.6 stack, RETENTION, REV, ERR Capture, Wonder Bridge, F555.
- FIX-1 synthetic companies + their scores deleted (ledger/audit rows of the synthetic runs kept as the labelled audit trail). Scratch tables `micro_results` and `probe_errors` dropped. 10 synthetic/driver test runs closed. The diagnostic ProbeLog tab was removed from the v-next Sheet copy.
- Migration pack updated per FIX-5 (WF00 v-next.6 + SF6 v-next.5 + SF8 v-next.7 exports, sf6-schema-migration.sql, RUNBOOK with the Apollo credential step, sheet key columns + backfill warning, Stage Context defaults, rollback instructions).
