# SF6b Pre-Enablement Tests — Wonder Final Verify Findings 1–4

Run: 2026-11-17 evening (Bangkok), after the SF6b promotion. Purpose: clear the
pre-enablement debt recorded in `t3/wonder-sf6b-finalverify.md` — these tests
had to pass BEFORE any search profile sets `linkedin_people_enabled = true`.
Finding 5 was closed at promotion (fail-closed gate). Finding 6 was done at
promotion (cost split). Finding 7 was noted-only.

**Verdict: Findings 1–4 all PASS. Finding 4 required a code fix (schema-drift
guard), which was built, applied live, and re-tested. The LinkedIn stage may
now be enabled per-profile, subject to the promotion conditions (human review
of verbatim headline + dm_matched_title + dm_profile_version before any use).**

---

## Finding 2 — slug-branch fixtures: PASS

RESOLVE_JS (SF6b) is a pure function of (name tokens, Tavily slug_text,
website site_text, stored linkedin_url). Tested two ways:

**Offline Node harness** on the live Parse/Resolve JS, 7 fabricated cases:
- t1 candidates exist but none token-verify → `none` ✓
- t2 stored URL verifies, no contradiction → `stored_verified` ✓
- t3 stored URL fails verification (unrelated company) → `slug_conflict` ✓
- t4 stored URL verifies but search passes a different slug only → `slug_conflict` ✓
- t5 website-extract slug is the exact flat-name form, search has the separator
  variant → website slug wins (`resolved yomabank`) ✓
- t6 "KBZ Bank" with candidates kbz-bank + kbzbank → `resolved kbz-bank`.
  NOTE: the flat variant `kbzbank` can never pass verifySlug for this name —
  its only distinctive token "kbz" is 3 chars and the flat-inclusion rule needs
  a ≥4-char distinctive token. The exact flat-name preference therefore only
  ever chooses among slugs that already passed verification. Fail-closed and
  consistent with Q4; this also explains why live KBZ resolution stores
  `kbz-bank`. Accepted as correct behaviour, no change.
- t7 website slug is the sole passer (all search candidates fail) → resolved
  via the website slug ✓

Website "outranking" semantics, stated precisely: the company's own website
candidates enter the pool FIRST, but a second distinct passing slug still
yields `ambiguous` (Q4 unchanged). The website link's power is pool inclusion
+ the exact flat-name preference, not an override.

**Live driver run 8** (fixture profile f9000000…0001, DRIVER2 → SF6b take 5):
- L1 "Shopify" with stored URL → `stored_verified`, entered the Apify batch,
  URL in DB unchanged afterwards, checked_at set, event `searched`.
- L2 "Acme Widgets Yangon" with stored URL = linkedin.com/company/microsoft →
  `slug_conflict` event, checked_at set, next_check_at +90 days, URL never
  overwritten, no Apify spend for it.
- Ledger reconciled exactly: Tavily 2 × $0.008 + Apify $0.005 start +
  2 × $0.01 charged = $0.041 = summary total_stage_cost_usd. Cost-split fields
  (slug_search / apify_run / total) present in the summary (Finding 6 evidence).

## Finding 4 — schema drift: GAP FOUND → GUARD BUILT → PASS

**Gap (code inspection):** SF6c's Company Rollup set `act = 1` for every batch
company unconditionally and derived `searched_zero` from valid-item counts
only. A dataset of 100% schema-invalid items produced only the Parse sentinel,
so every company would have been marked checked as `searched_zero` — exactly
the failure Wonder flagged.

**Guard (generator + live SF6c `<sf6c-workflow-id>`, 5 ops + 1 param op):**
- Parse People: `run_counts` gains `raw_total` and `schema_total_failure`
  (raw_total > 0 AND valid == 0), carried on every item incl. the sentinel.
- Company Rollup: on schema_total_failure it emits `act = 0, drift = 1` rows
  with detail outcome `schema_drift` (+ dropped_schema count); normal rows now
  also carry dropped_schema in their event detail.
- MARK_CHECKED_SQL v2 (shared namespace in gen_sf6b_vnext2.py): a $6 drift
  flag releases the company's claim (only when claim_run_id matches this run),
  writes the event, and records the $0.005 Apify start charge — WITHOUT setting
  checked_at. The event insert fires when either the mark or the release
  updated a row.
- Return summaries: counts now read from any Parse item (incl. sentinel) and
  expose `schema_drift: true/false`.

**Live test** (DRIVER3 → SF6c, run …0009): a garbage Apify dataset (items
pushed via API; the clean=true fetch view returned 1 item, 100% invalid) was
injected via SF6c's dataset_id override against a real SUCCEEDED run ID, with
fixture company L3 claimed by the test run. Result:
- summary: `schema_drift: true`, dropped_schema 1, people_saved 0, success true
- L3: checked_at NULL ✓, claim released ✓
- event: `schema_drift` with dropped_schema=1 ✓
- ledger: $0.005 start charge recorded (the run did start — honest accounting) ✓

Accidental extra evidence: a mis-seeded rerun pointed the drift path at a
company claimed by a DIFFERENT run — the release correctly did not fire
(claim-ownership check works).

Migration pack `sf6c-vnext.json` refreshed from the live workflow (guard
verified present in the exported Parse JS).

## Finding 3 — SF6c failure reconciliation: PASS

**Give-up test** (DRIVER3 → SF6c, run …0010): SF6c was pointed at a
nonexistent Apify run ID with fixture company L4 claimed by the test run.
SF6c polled (404s do not kill the loop) and gave up after the 8-minute window:
- summary: `success: false, apify_failed: true`
- L4: checked_at NULL ✓, claim released ✓
- event: `apify_failed` ✓
- ledger: an apify usage charge row written ($0 — the fake run reported no
  usage; FAIL_SQL writes the run's Apify-reported usageTotalUsd on the first
  batch company)

**Orphan accounting (the E6 incident run):** Apify run `<apify-run-id>`
(abandoned when SF6c looped pre-fix) reports usageTotalUsd **$0.21**. The
ledger captured $0.021 for that run (2 × $0.008 slug + $0.005 start). **Gap:
≈ $0.189 of profile charges were never ledgered**, because no SF6c execution
ever reconciled that run. Bounds and recovery, stated honestly:
- The gap is bounded by the pre-claim affordability estimate (the batch was
  capped before the claim).
- The reconciliation hook exists and was used for this very check: SF6b
  persists the Apify run ID in the ledger (`sf6b:run:<run_id>:<apify_run_id>`)
  before polling, so any abandoned run's true cost is recoverable from Apify
  at any time.
- The give-up path (proven above) writes the usage row for runs SF6c does see
  fail; the residual gap is only post-give-up accrual on runs abandoned
  entirely. A periodic sweep of persisted-but-unreconciled run IDs is future
  work, NOT built; it is not required by the finding, which asked for the
  accounting to be demonstrated.

## Finding 1 — monitored positive-path WF00 run: PASS

WF00 v-next.9 TEST head (copy of canonical v-next.8; FYF context verbatim +
`linkedin_people_enabled: true`, spend cap $3.0, max 12 companies) run once,
monitored, execution 815 → run `19b5f979-6e0a-45a7-9a35-3401d72df570`,
status **done**. Two seeded resolvable companies rode the real FYF profile:
- KBZ Bank → slug resolved, `linkedin_url` stored =
  https://www.linkedin.com/company/kbz-bank, checked_at set, event `searched`
- Yoma Bank → resolved, stored = …/company/yoma-bank-limited, checked, `searched`
- **6 decision-makers saved** through the full WF00 → SF6b → SF6c path
  (2 KBZ + 4 Yoma), each passing the dynamic FYF-titles phrase match +
  association gate; no other company in the batch produced a save.
- Rest of batch behaved as designed: ambiguous_slug ×4, no_linkedin_page ×2.
- Run ledger total **$0.251** (cap $3.0). SF6b did not block the chain;
  SF9 + SF8 completed; run closed 'done'.
- The seeded companies and their 6 people were deleted after verification
  (labelled fixture data); the run's events/ledger/audit trail remains.

## State after these tests

- Pre-enablement debt: **CLEARED** (Findings 1–4 pass; 5 and 6 closed at
  promotion; 7 noted).
- Canonical head unchanged: WF00 v-next.8 (LinkedIn stage default OFF).
  Enabling remains a per-profile decision (`linkedin_people_enabled = true`
  in that profile's run context), with human review of every save.
- SF6c now carries the schema-drift guard (live + generator + migration pack).
- All test helpers archived; fixture data deleted; ProbeLog tab removed
  (approval Sheet = Lead Review + People only).
