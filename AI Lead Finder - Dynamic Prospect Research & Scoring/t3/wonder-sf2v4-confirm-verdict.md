# Email

## Message

From: Victor Job <owner@example.com>  
Subject: Wonder SF6b FINAL VERIFY - promotion ruling (2026-11-17)  
Sent: Wed, 18 Nov 2026 02:00:03 -0600  
Sent (UTC): 2026-11-18T08:00:03.000Z  
Sent (Asia/Bangkok): 2026-11-18T15:00:03.000+07:00  
Gmail message: 1a1edab84a1989a4  
Thread: 1a1edab84a1989a4  
Message-ID: CAHBDfCYjnrLkckzvuZA73QS=mVNpkBmC6tcfURrvrwpY=JO00A@mail.gmail.com  
Body coverage: full  
Body format: text  

## Attachments

No attachments.

## Body

VERDICT: DO NOT PROMOTE - The claim-lost path is still proven only at SF2 level, not through WF00 where an empty candidate set could drop the existing pool.

CONDITION 2: OPEN - Proof B (WF00 971 / SF2 972, cache-hit: 95 returned, no MCP, no claim, cache_hit_zero ledger, dedupe 9 inserted / 86 duplicates, scoring 9 scored / 138 skipped, Lead Review 446->455, People 21->21, run 'done') closes the cache-hit rerun, and Proof C closes the cleanup (hotel run 5ba9ce4d marked 'failed' with finished_at, no rerun of the landed +47 publish). But Proof A is SF2 execution 968 alone: seeded claim on f9227b2c, cache-miss, return {count: 0, candidates: [], already_discovered: true, existing_companies: 81}, no MCP. The statement that SF4 then receives zero while SF5/SF3/SF6 process the 81 from the database is asserted, not executed - there is no WF00 execution, no downstream SF4/SF5/SF3/SF6 execution, and no run summary on the claim-lost / empty-candidates branch, and Proof B cannot substitute because it took the opposite branch (95 candidates returned).

CONDITIONS: 1) One live WF00 v-next.11 claim-lost execution (cache-miss, claim already held, existing_companies > 0) showing SF2's zero-candidate return, zero discovery spend, downstream SF5/SF3/SF6 actually picking up the existing pool under their pick-dedupe, formal run closure, and no duplicate Sheet/People rows. 2) Condition 4 unchanged: owner labels on the FYF-only 40-company pack; no precision figure claimed until labelled.

