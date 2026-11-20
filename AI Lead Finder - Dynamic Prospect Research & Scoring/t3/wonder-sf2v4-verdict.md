# Email

## Message

From: Victor Job <owner@example.com>  
Subject: Wonder SF6b FINAL VERIFY - promotion ruling (2026-11-17)  
Sent: Wed, 18 Nov 2026 01:39:12 -0600  
Sent (UTC): 2026-11-18T07:39:12.000Z  
Sent (Asia/Bangkok): 2026-11-18T14:39:12.000+07:00  
Gmail message: 1a1ed986d8219eb8  
Thread: 1a1ed986d8219eb8  
Message-ID: CAHBDfCb9ZxeN+oNP1Ay0tEmAUg7kTNgQrN+6KuN7BV1X-VkuJw@mail.gmail.com  
Body coverage: full  
Body format: text  

## Attachments

No attachments.

## Body

VERDICT: DO NOT PROMOTE - Conditions 1 and 3 are closed, but Condition 2 is proven only inside SF2 rather than in WF00—whose sole full run never formally closed—and Condition 4's owner-labelled precision proof remains absent.

CONDITION 1: CLOSED - The hardcoded category-noun pattern is absent from the shipped code, and the replacement derives its keyword set dynamically from all of the run's pair queries, using tokens over two characters, excluding location tokens and generic stopwords, with singular/plural tolerance. On the hotel profile this reduced output from 61 candidates in v-next.2 to 23 under the profile-union rule, with zero best/top titles and real properties ranked first; the unrelated FYF vocabulary also produced 95 candidates without any hardcoded category list. This closes the hardcoded-list condition, although the disclosed residual remains real: aggregators and content pages without best/top wording can still pass and must be absorbed by scoring.

CONDITION 2: OPEN - The atomic-claim subpart is proven: one Postgres CTE performs INSERT ... ON CONFLICT DO NOTHING RETURNING and selects `claimed` in the same statement, the search hangs only off `claimed=true`, and the claim-lost test on run `...0097` did not run MCP. The new Tavily F29 cache is also proven at SF2 level: a fresh run produced and cached 95 candidates, while a second run with a new run_id hit the cache, skipped both claim and MCP, and wrote a `cache_hit_zero` ledger row. But WF00 handling of `already_discovered` is not proven: promotion would leave WF00 as v-next.10 except for the SF2 pointer, no WF00 consumption of that flag is shown, the claim-lost live case had `existing_companies: 0` rather than demonstrating recovery with existing companies, and no deliberate WF00 rerun was performed. The sole WF00 hotel run verified the work landed—Sheet rows 398 to 445, sort completed, People rows added—but its SF8 tail hung, the execution still shows running, and the WF00 run record was never closed. SF2-level substitution and disclosure do not close a WF00-level gate.

CONDITION 3: CLOSED - The node-parameter diff across all 24 shared nodes between live SF2 v-next.2 and v-next.4 shows only `Build Tavily Pairs` differing, namely the previously disclosed explicit-profile-reference fix; the Apify branch, its F29 cache chain, manual import, profile load, engine gate, and MCP node are otherwise unchanged. The live `discovery_source='places'` test took the gate's false branch, executed Apify, reached a usage-exhaustion rather than authentication error, and left the Tavily branch untouched. That proves the Apify path is unchanged and correctly routed, though it does not prove a successful Apify harvest while quota is exhausted.

CONDITION 4: OPEN - The rebuilt FYF-only 40-company pack exists, but the owner has not labelled it, no precision by fit band has been produced, and the earlier `107 usable` figure remains unvalidated. Not claiming a figure is the honest position, but it is not closure of the precision condition.

CONDITIONS:
- Prove or implement WF00-level handling on a healthy instance, without rerunning the landed hotel publish: a cache-miss/claim-lost run with `already_discovered: true` and `existing_companies > 0` must cause no MCP or downstream spend, must not be silently closed as a genuine zero, and must surface the existing set; a deliberate WF00 rerun with a new run_id and same profile must show cache hit, no claim/MCP spend, dedupe preventing duplicate downstream spend and duplicate Sheet/People rows, and a formally closed run record; clean up the hung SF8 execution and unclosed hotel run record.
- Owner completes the FYF-only 40-company labels and precision by fit band is reported from those labels; the `107 usable` figure remains unclaimed until then.

