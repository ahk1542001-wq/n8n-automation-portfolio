# SF6b offline matcher test — 2026-11-17 (Wonder design condition)

Harness: the LIVE Parse People JS + TOKEN_JS extracted verbatim from gen_sf6b_vnext2.py,
run in Node with stubbed $ / $input. Dataset: 13 real people from the proven Apify test
run (execution 717, 2026-11-17) — 3 Shopify + 10 KBZ Bank, headlines verbatim.

## FYF profile titles (real, SF1-generated): ["Owner","Founder","Co-Founder","Managing Director","Proprietor"]
- Saved: 0 / 13. All correct:
  - Andrea Nigro (Shopify SERP result, headline "CEO & Co-Founder - Digital & Brand Strategist",
    actor isDecisionMaker=true) matched title Co-Founder but was DROPPED by the association
    gate (headline never names Shopify) — the proven false-match case, caught.
  - HAN WIN HLAING ("CEO at KBZ LIFE Insurance") dropped non_dm — correct under FYF titles
    (no "CEO" in the FYF array; SF1 must emit it if wanted — Wonder Q1 ruling).

## B2B titles: ["CEO","Chief Executive Officer","General Manager","Managing Director","President"]
- Saved: 2 / 13, both correct with matched title recorded:
  - HAN WIN HLAING — CEO (association token "kbz")
  - Ebrahim Keekeebhai — General Manager (association "kbz"/"bank")
- All other 11 dropped with correct reasons (non_dm / association_unverified).

Conclusion: classification is 100% profile-driven; the actor's isDecisionMaker flag
played no part (fixture carried it; Parse never reads it for the flag).
