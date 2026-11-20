# Email

## Message

From: Victor Job <owner@example.com>  
Subject: Wonder SF6b FINAL VERIFY - promotion ruling (2026-11-17)  
Sent: Tue, 17 Nov 2026 22:59:18 -0800  
Sent (UTC): 2026-11-18T06:59:18.000Z  
Sent (Asia/Bangkok): 2026-11-18T13:59:18.000+07:00  
Gmail message: 1a1ed73e7181de4c  
Thread: 1a1ed73e7181de4c  
Message-ID: CAHBDfCYhXkrYzf1Son-CbM24vbX=ASGy+fGyzXDQzU-j__wLeA@mail.gmail.com  
Body coverage: full  
Body format: text  

## Attachments

No attachments.

## Body

VERDICT: DO NOT PROMOTE - Although the Tavily same-run guard works in the sequential test, v-next.3 adds a hardcoded category-noun regex in breach of the dynamic-derivation rule, so the build as submitted is not fit to become the canonical head.

CONDITION-2 STATUS: SATISFIED - 'DB - Tavily Run Guard' checks cost_ledger for 'sf2:tavily:guard:' + run_id, 'DB - Tavily Guard Mark' writes the 0-unit/0-cost marker before any search with ON CONFLICT DO NOTHING, and the true branch returns {success: true, count: 0, candidates: [], engine: 'tavily', already_discovered: true} with no search. Live evidence: fresh run ...0096 routed fresh, wrote the marker, built 10 pairs, ran Tavily MCP and returned 99 candidates after the disclosed profile-flow bug was fixed by reading $('DB - Load Search Profile').item.json.profile explicitly; repeat of run_id ...0097 routed 'already', Tavily MCP did not run, and no new charge was made. That is the sequential WF00-rerun case Condition 2 asked for.

RISKS:
- Direct standing-rule breach in Change 2: hotels, cafes, restaurants, shops, salons, spas, places, stays, bars, gyms, eateries, attractions is a hardcoded English category list, not derived from the run's profile/business context. It is already brittle on its own evidence: 'Best Cafe in Yangon' leaks because the list has plural 'cafes' not singular 'cafe', and 'Best Facials near me in Yangon' leaks because 'facials' is unlisted; any vertical outside the list is unprotected, and no evidence shows the target 'best boutique hotels' case is now caught or that legitimate 'Best...' businesses are not dropped.
- Condition 3 is not closed: the rebuilt FYF-only 40-company F9 pack is only the instrument. No tavily_web precision by fit band has been quantified yet, and "scoring remains the absorber" is asserted, not evidenced.
- Marker-first empty-success contract is unproven at the caller: if a first attempt dies mid-search, that run_id can never rediscover and will return success:true/count:0. No evidence shows WF00 v-next.11 distinguishes already_discovered:true from a genuine zero and does not close the run 'done' with discovery silently lost.
- Guard is check-then-mark, not an atomic claim: two concurrent executions with the same run_id could both pass the EXISTS check, the loser's ON CONFLICT DO NOTHING insert still proceeds down the chain, and both could spend. Only sequential rerun was tested.
- Apify byte-identity is unproven: an intermediate patch touched its Build JS, was reverted, and the credential was corrected, but only connection-graph and credential read-back are cited - no node-code diff against v-next.2 and no live Apify-path execution on v-next.3 (id i1iwMUJDFOwQrNKF).

CONDITIONS:
1. Remove the widened hardcoded noun list - revert the Tavily mapper to the v-next.2 filter or derive listicle category terms dynamically from the run's profile - and show the filter working, including singular/plural forms, on a hotel profile and on a profile whose category is outside the current list.
2. Make the guard an atomic claim (search proceeds only on successful marker insertion) or evidence that same-run_id WF00 executions cannot overlap; then run WF00 v-next.11 end-to-end fresh plus same-run_id rerun, showing no second MCP run, no second charge, and explicit WF00 handling of already_discovered:true, including the mid-search-failure case.
3. Prove the Apify path is unchanged - node-code diff against SF2 v-next.2 or a live Apify smoke on v-next.3 with the corrected credential.
4. Keep prior Condition 3 open until the F9 40-company labelling actually reports tavily_web precision by fit band; the pack rebuild alone does not close it.

