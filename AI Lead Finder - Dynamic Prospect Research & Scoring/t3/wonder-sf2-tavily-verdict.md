# Email

## Message

From: Victor Job <owner@example.com>  
Subject: Wonder SF6b FINAL VERIFY - promotion ruling (2026-11-17)  
Sent: Tue, 17 Nov 2026 22:33:20 -0800  
Sent (UTC): 2026-11-18T06:33:20.000Z  
Sent (Asia/Bangkok): 2026-11-18T13:33:20.000+07:00  
Gmail message: 1a1ed5c210ad9a6a  
Thread: 1a1ed5c210ad9a6a  
Message-ID: CAHBDfCZy4B=wmNbrAFBuf01si5n_Bm1BAWMtQatJQuEiidy47A@mail.gmail.com  
Body coverage: full  
Body format: text  

## Attachments

No attachments.

## Body

VERDICT: PROMOTE WITH CONDITIONS - the Tavily path is proven live as a Maps replacement, but the canonical swap needs explicit default-branch/second-profile proof and a retry guard, because large Tavily runs now routinely hit the pre-existing SF8 failure while discovery is uncached.

SPEC: PASS - Owner chose option (1) and it was built and verified, not just designed. Standalone FYF-Yangon test: 10 searches, 91 candidates, spread across all 8 profile categories (8-13 each) plus 15 from tavily_research queries, ledger row written, success=true. Full WF00 test-head runs: companies 22 -> 138, all Yangon per profile locations ['Yangon'], people 1 -> 12, Approval Sheet publish landed at 398 rows. Weakness not softened: this is one profile only, precision is visibly below Maps, and only 2/138 scored fit >=50 against 105 in 30-49 - the "107 usable >=30" figure is not an audited precision claim, since admitted junk lands in the low 30s. That limits the quality claim, not the build-and-verify spec.

STANDARDS: PASS - Dynamic derivation holds in substance: discovery_source is read from the trigger/run item (the silent fall-through bug from reading post-load $json was caught and fixed), queries, categories and location come from the profile, and profiles without the flag keep Maps. Honest nulls are exemplary: phone/rating stay null, source is labelled 'tavily_web', same candidate contract as Maps. Scoring and drafts-only behaviour are untouched; filters and the control-character sanitiser (fixing the real NUL-byte SF4 crash, re-verified) are deterministic. Two borderline points flagged: (a) the aggregator-domain list and listicle regex are hardcoded, but they are profile-agnostic page-type exclusions, not hardcoded ICPs/titles - the real risk is drift and excluding a legitimate business whose only presence is, e.g., LinkedIn; (b) no discovery cache is a genuine dedupe-before-spend deviation for repeat discovery spend - SF4 dedupe and ~$0.006/search (ledgered correctly as 'charge' with idempotency key 'sf2:tavily:'+run_id) mitigate it downstream, they do not eliminate it. Hence the conditions below.

SF3 FIX: SOUND - ON CONFLICT (linkedin_url) WHERE linkedin_url IS NOT NULL DO NOTHING exactly matches the global partial index people_linkedin_url_uq and closes the cross-company gap the same-company NOT EXISTS guard missed; the previously dying run proceeding past SF3 is live proof. Caveat: DO NOTHING silently drops the second-company association for that person with no logging - acceptable as a crash fix, a completeness loss to log in follow-up, not a flaw in the fix itself.

SF8 ISSUE: NON-BLOCKING for this promotion - SF8 is unchanged and predates SF2 v-next.2, the publish verifiably lands in the Sheet before the sort crash on both large (398-row) and small runs, and the failing step is cosmetic ordering with no data loss shown. Not softened: Tavily makes ~80+ row publishes the normal case, so canonical WF00 runs will routinely report failure at SF8, and an operator retry would re-spend on uncached Tavily discovery. That blocks calling large runs operationally clean; it does not block promoting the SF2 code.

CONDITIONS:
1. Pre-swap evidence pack on the test head: (a) a profile without discovery_source='tavily' demonstrably enters the Apify branch (branch-level execution evidence suffices - Apify credit is exhausted), closing the exact silent fall-through bug class; (b) one standalone Tavily test on a second, non-FYF profile with different location/categories, proving dynamic derivation beyond a single Yangon context.
2. At rollout, a binding SF8 rule: if SF8 fails at the sort step after Sheet rows are verified present, the publish is treated as landed and WF00 must NOT be rerun - until a Tavily query cache or same-run_id discovery guard (Maps-branch parity) is added in the next SF2 revision.
3. Report tavily_web precision separately by fit band, with a sampled audit of the 30-49 band, before the 107 >=30 figure is used as a validated usable-leads number.

