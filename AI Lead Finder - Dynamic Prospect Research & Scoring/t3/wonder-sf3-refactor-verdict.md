# Wonder verdict — SF3 v-next.3 dynamic DM classification (2026-11-17)

VERDICT: PROMOTE - Profile-only DM classification is proven offline and live: 'Operations Manager' and an LLM-claimed 'Barista' are not DM, empty profile titles classify nobody, and on the live Shopify run Lutke ('CEO') is DM with dm_matched_title='CEO' while Finkelstein ('President') is not DM under the fixture profile, despite the old regex flagging both 'manager' and 'president'.

REMAINING FINDINGS:
- BLOCKER: None. The hardcoded-regex path is dead ('Operations Manager' -> NOT DM; live 'President' -> is_decision_maker=FALSE), the LLM claim path is dead (is_decision_maker=true with title 'Barista' -> NOT DM), and fail-closed behaviour is shown (empty profile titles -> nobody DM).
- SHOULD-FIX: None. The unchanged verbatim evidence gate is still exercised (quote absent from corpus -> person dropped entirely), and the baseline control attributes the earlier failure to test setup, not the refactor (unchanged v-next.2 reproduced the identical missing runs-table FK error; v-next.3 completed cleanly after the runs row was seeded).
- NICE-TO-HAVE: The packet quotes dm_matched_title='CEO' for the live positive case but not the dm_profile_version value or the null matched-title for Finkelstein, and the harness reports no positive multi-word case for 'General Manager' from its profile list [CEO, General Manager, Founder, Owner]; neither gap undermines the classification proof, given the 'Operations Manager' negative exercises contiguous-phrase over-matching and the matcher reuses the previously approved SF6c normalisation.

CONDITIONS: NONE
