# Migration Pack — vic154 (n8n Cloud trial) → ကိုယ်ပိုင် self-hosted n8n

ပြင်ဆင်ပြီး — 2026-11-16 · နောက်ဆုံး update — 2026-11-19 (WF00 v-next.12 canonical — SF6d v-next.3 X-Ray stage ချိတ်ပြီး flag OFF; Wonder delta-2 = ENABLE WITH CONDITIONS, အခြေအနေတွေကို အောက်မှာ ကြည့်ပါ; ကျန်တဲ့ owner condition = F9 labelling) · **ဆုံးဖြတ်ချက် နောက်ဆုံးရက်: Nov 25** · trial သက်တမ်းကုန်: **Nov 28** ခန့်

## ပါဝင်တဲ့ ဖိုင်တွေ (workflow JSON ၁၆ ခု — import လုပ်လို့ရတဲ့ အပြည့်)

| ဖိုင် | Workflow |
|---|---|
| wf00-vnext11.json | **WF00 v-next.11 — အဓိက orchestrator (canonical head, 2026-11-18 — SF2 v-next.4 + SF4 v-next.2 ကို ညွှန်တယ်၊ SF6b ပါသည်၊ LinkedIn stage မူရင်း OFF)** |
| sf6b-vnext2-take5.json | **SF6b v-next.2 take 5 — LinkedIn People (Apify, dynamic titles; fail-closed gate)** |
| sf6c-vnext.json | **SF6c v-next — People Fetch (poll + save; SF6b ဒုတိယပိုင်း)** |
| sf1.json | SF1 — Search-Profile Generator |
| sf2-vnext4.json | SF2 v-next.4 — Discovery (Apify + Tavily web + Import) + Cache + atomic claim |
| sf4-vnext2.json | SF4 v-next.2 — Dedupe + Exclusion (empty-batch summary fix) |
| sf7-vnext3.json | SF7 v-next.3 — Scoring |
| sf5-vnext5.json | SF5 v-next.5 — Research + Critic |
| sf3-vnext3.json | SF3 v-next.3 — People Finder (dynamic profile-titles DM) |
| sf6-vnext5.json | **SF6 v-next.5 — Contact Waterfall (Facebook/email/size + Apollo)** |
| sf9-vnext.json | SF9 v-next — Timing Re-Score |
| sf8-vnext8.json | **SF8 v-next.8 — Approval View Sync (lead_key + person_key + whole-sheet sort)** |
| sf8b-vnext2.json | SF8b v-next.2 — Write-Back |
| err-vnext2.json | ERR v-next.2 — error စောင့်ကြည့်သူ |
| retention-vnext.json | RETENTION v-next — လူ data retention |
| sf6-schema-migration.sql | SF6 အတွက် DB column အသစ်တွေ (fresh DB အတွက်ပဲ လိုတယ် — အောက်မှာကြည့်ပါ) |
| sf6b-schema-migration.sql | SF6b အတွက် DB column/index အသစ်တွေ (linkedin_url, people-state columns, people_linkedin_url_uq) + checked_at အဓိပ္ပာယ် မှတ်ချက် |

အရင် version တွေ (wf00-vnext3, sf8-vnext4) ကို `superseded/` folder ထဲ သိမ်းထားတယ် — rollback လိုရင် အဲဒီကယူပါ။
Generator မူရင်းကုဒ်တွေ GitHub မှာ backup ရှိတယ် (repo: n8n-automation-portfolio)။

## ဖေဖေကြီး လုပ်ရမယ့် အဆင့် (self-hosted n8n UI ထဲမှာ၊ ၃၀-၄၅ မိနစ်ခန့်)

1. **Credential ၇ ခု အရင်ဆောက်** (နာမည်တွေ ဒီအတိုင်း အတိအကျ ပေးပါ):
   - `Postgres` — Supabase leadfinder (pooler host, user `postgres.kcnlkyjthkqppnjrizoh`, SSL Require + CA cert)
   - `Google Sheets` — Google Sheets OAuth2 (job154 account)
   - `Gmail` — Gmail OAuth2 (job154 account)
   - `Meta Model API` — Header Auth (Authorization: Bearer …)
   - `Tavily MCP` — MCP OAuth (Tavily)
   - `Apify` — Header Auth (Apify token) — SF2 Places လမ်းကြောင်းအတွက်
   - **`Apollo` — Header Auth အသစ်**: credential ရဲ့ **Name အကွက်မှာ `X-Api-Key`** လို့ ရိုက်ပါ (ဒါက label မဟုတ်ဘူး၊ header နာမည်ပါ), Value မှာ Apollo API key ထည့်ပါ။ SF6 ရဲ့ Apollo node မှာ ဒီ credential ကို ပြန်ရွေးပေးရမယ်။
2. **Workflow ၁၃ ခုကို Import** (Workflows → Import from File) — အစဉ်အတိုင်း: sf1, sf4, sf2, sf7, sf5, sf3, **sf6**, sf9, sf8, sf8b, err, retention, နောက်ဆုံး **wf00-vnext8** (sf6b, sf6c ကို wf00 မတိုင်ခင် import ပါ)။
3. Import ပြီးရင် workflow တစ်ခုချင်းစီမှာ **credential တွေ ပြန်ချိတ်**ပါ (node တွေပေါ်မှာ credential အမှား အနီပြနေရင် အဆင့် ၁ က နာမည်တူ credential ကို ရွေးပေးပါ)။ SF6 ရဲ့ `Apollo - Org Enrich` node မှာ Apollo credential (အဆင့် ၁ နောက်ဆုံး) ကို ရွေးဖို့ မမေ့ပါနဲ့။
4. **အရေးကြီး ပြန်ချိန်ရမယ့် အချက်တွေ:**
   - WF00 v-next.8 ရဲ့ settings မှာ errorWorkflow = **ERR v-next.2** (import အသစ်မှာ ID ပြောင်းသွားလို့)
   - SF5 v-next.5 ရဲ့ settings မှာ errorWorkflow = error capture workflow (လိုချင်ရင် ERR Capture ကို သပ်သပ် ပြန်ဆောက်ရမယ် — မဖြစ်မနေ မလိုပါ)
   - SF8 v-next.8 / SF8b v-next.2 ထဲက Sheet ID က vic154 ဘက်က **v-next copy Sheet** (`1dF2mdjUFc6D0jFTvhxbby6DJxWo4T6Fw0UrWEHI20JM`) ကို ညွှန်ထားတယ် — self-hosted ဘက်က Google account နဲ့ အဲဒီ Sheet ကို ဝင်သုံးခွင့် ရှိရမယ်၊ မရှိရင် Sheet အသစ် မိတ္တူပွားပြီး ID အသစ် ပြန်ထည့်ရမယ်။
   - **Sheet ပုံစံ (SF8 v-next.8 အတွက် မဖြစ်မနေ):** Lead Review tab မှာ column ၁၈ ခု ရှိရမယ် — run_id, company_id, Company, Category, Location, Website, Phone, Facebook, Email, Size, Rating, Reviews, Fit, Timing, Band, Decision, Note, **lead_key** (နောက်ဆုံး column R)။ People tab မှာ column ၈ ခု — company_id, Company, Person, Position, LinkedIn, Phone, Email, **person_key**။ **SF8 v-next.8 အသစ် (2026-11-17):** Lead Review မှာ helper column နောက်ထပ် ၂ ခု ထပ်လိုတယ် — column S = **city_rank**, column T = **fit_num** (header ပဲ ထည့်ထားရင် ရပြီ၊ တန်ဖိုးတွေကို SF8 က run တိုင်း ပြန်ရေးတယ်)။ SF8 ရဲ့ sort အဆင့်က Sheets API sortRange ကို သုံးပြီး tab ရဲ့ **sheetId (gid)** နဲ့ ခေါ်တယ် — vic154 copy မှာ Lead Review gid = 0။ Sheet အသစ်မှာ ဆိုရင် အဲဒီ tab ရဲ့ gid အစစ်ကို ကြည့်ပြီး SF8 v-next.8 ရဲ့ 'HTTP - Sort Range (Sort)' node ထဲက sheetId ကို ပြင်ရမယ်။ Sheet အဟောင်းကို ဆက်သုံးမယ်ဆိုရင် lead_key column အသစ်ထည့်ပြီး row တစ်ခုချင်းစီမှာ `run_id|company_id` ပုံစံနဲ့ key တွေ အရင် backfill လုပ်ရမယ် (မလုပ်ရင် ပထမဆုံး publish မှာ row တွေ ထပ်ကုန်မယ်)။
   - WF00 v-next.8 ရဲ့ **Business Context node** ထဲမှာ စမ်းသပ်တုန်းက သုံးခဲ့တဲ့ FYF-Yangon test context ဝင်နေတယ် — တကယ် run မလုပ်ခင် ကိုယ့်လုပ်ငန်း context အစစ်နဲ့ အစားထိုးပါ။ Stage Context မူရင်းတန်ဖိုးတွေ: contact_min_fit = 30, max_contact_companies = 10, **contact_provider_enabled = true** (Apollo သက်သေပြ စမ်းသပ်မှု အောင်ပြီးသား — 2026-11-16)။ SF6b အတွက်: **linkedin_people_enabled = false (မူရင်း)** — Wonder pre-enablement စမ်းသပ်ချက် ၄ ခု (Finding 1–4) **2026-11-17 ည PASS အကုန်** (မှတ်တမ်း: SF6B-PREENABLEMENT-TESTS.md) — ဒါကြောင့် profile တစ်ခုကို true ပြောင်းလို့ ရပြီ၊ ဒါပေမယ့် save ဖြစ်လာတဲ့ လူတိုင်းကို People tab မှာ headline + dm_matched_title ကို လူကိုယ်တိုင် စစ်ပြီးမှ သုံးပါ။ **သတိ: sf6c-vnext.json မှာ schema-drift guard ပါပြီးသား (2026-11-17 ည refresh) — dataset အားလုံး invalid ဖြစ်ရင် checked မဖြစ်ဘဲ schema_drift event + claim release ဖြစ်တယ်။**
5. RETENTION v-next ကို **Publish** လုပ်ပါ (လစဉ် schedule အတွက်)။ ကျန်တာတွေ inactive ပဲ ထားပါ (WF00 က လက်နဲ့ စ run ရတဲ့ စနစ်ပါ)။
6. ပြီးရင် ကျွန်တော့်ကို ပြောပါ — smoke test (manual import လမ်းကြောင်း၊ spend cap $0.5) နဲ့ အတည်ပြု စစ်ပေးမယ်။

## Database

Database က Supabase ပေါ်မှာပဲ ဆက်ရှိတယ် — migration က n8n ဘက်ပဲ ရွှေ့တာ၊ data မရွှေ့ရဘူး။ **လက်ရှိ live DB မှာ SF6 column တွေ ထည့်ပြီးသားမို့ `sf6-schema-migration.sql` ကို run စရာ မလိုဘူး** — DB အသစ် ပြန်ဆောက်မှသာ လိုမယ်။ F3 (DB password လဲတာ) နဲ့ F20 (role အသစ်) က သပ်သပ် အဆင့်တွေ ဖြစ်တယ်။

## မအောင်မြင်ရင် ပြန်သွားရန်

vic154 trial က Nov 28 အထိ ရှိသေးတယ် — migration စမ်းနေတုန်း vic154 ဘက်က stack ကို လုံးဝ မဖျက်ဘူး၊ မပိတ်ဘူး။ vic154 ပေါ်မှာ rollback head အဖြစ် **WF00 v-next.7** (SF6b မပါ; superseded/ ထဲမှာ JSON ရှိတယ်) နဲ့ SF6b take 4 (archive လုပ်ထားတယ် — လိုရင် unarchive ပြန်လုပ်ပါ) နဲ့ live fallback **WF00 v8** ကို မထိဘဲ ထားထားတယ်။ self-hosted ဘက် smoke test အောင်မှ vic154 ကို နောက်ဆုံး စွန့်မယ်။

## ⭐ စည်းကမ်း — SF8 publish crash (Wonder condition, 2026-11-18)

SF8 က Sheet ထဲ row တွေ publish ပြီးမှ sort အဆင့်မှာ crash တတ်တယ် (trial instance memory ဖိအားကြောင့်)။ **Sheet ထဲမှာ အဲ့ run ရဲ့ row တွေ ရောက်နေတာ အတည်ပြုပြီးရင် publish က landed လို့ သတ်မှတ်ပါ — WF00 ကို လုံးဝ ပြန် မ run ပါနဲ့။** ပြန် run ရင် discovery ခ ထပ်ကုန်နိုင်တယ်။ Sort က cosmetic ပဲ ဖြစ်ပြီး data မဆုံးရှုံးဘူး။ (SF2 v-next.4 ကစပြီး discovery cache + atomic claim ပါလာတော့ rerun ကုန်ကျစရိတ် အများစု ပိတ်သွားပြီ — ဒါပေမဲ့ စည်းကမ်းက ဆက်ရှိတယ်။)

## Update — 2026-11-18 (WF00 v-next.11 — Tavily discovery + SF4 fix; Wonder PROMOTE WITH CONDITIONS)

- **SF2 v-next.4**: Apify လမ်းကြောင်းအပြင် Tavily web discovery ပါလာတယ် (profile ရဲ့ query တွေကနေ web search လုပ်ပြီး candidate ထုတ်တယ်)။ Discovery cache (F29 ပုံစံတူ) — run အသစ်နဲ့ ပြန် run ရင်လည်း TTL အတွင်း ရှာဖွေခ ထပ်မကုန်ဘူး။ Same-run guard က atomic claim ဖြစ်သွားပြီ — claim မရရင် already_discovered + ရှိပြီးသား company အရေအတွက်နဲ့ ပြန်တယ်၊ silent zero မဟုတ်တော့ဘူး။ Listicle filter က profile ရဲ့ ကိုယ်ပိုင် query keyword တွေကနေ dynamic ထုတ်တယ် (hardcode လုံးဝ မရှိဘူး)။
- **SF4 v-next.2**: candidate 0 ခု batch မှာ SF4 က ဘာမှ ပြန်မပေးဘဲ WF00 တစ်ခုလုံး တိတ်တိတ်ရပ်သွားတဲ့ bug ကို ပြင်ထားတယ် (alwaysOutputData + summary guard)။ Wonder ရဲ့ condition test က ဒီ bug ကို ဖမ်းမိခဲ့တာ။
- **Canonical head = WF00 v-next.11** (SF2 → v-next.4, SF4 → v-next.2; ကျန်တဲ့ stage အားလုံး အရင်အတိုင်း)။ Rollback = WF00 v-next.10 (superseded/ ထဲမှာ)။
- သက်သေ: FYF full run (company 147), hotel profile full run (company 61), WF00 rerun မှာ cache hit (ရှာဖွေခ $0), empty-candidate run မှာ pool 147 ခုလုံး ဆက်အလုပ်လုပ်ပြီး run ပုံမှန်ပိတ်တယ်, canonical smoke မှာ dedupe 22 duplicates ကို DB/Sheet နဲ့ reconcile လုပ်ပြီး။
- **ကျန်တဲ့ Wonder condition တစ်ခုတည်း = F9 labelling** — F9 pack (FYF Yangon company 40) ကို ဖေဖေကြီး ကိုယ်တိုင် စစ်ပြီး label ထိုးပေးမှ precision ကို တိုင်းလို့ရမယ်။ အဲဒါ မပြီးမချင်း "အသုံးတည့်တဲ့ lead ဘယ်နှခု" ဆိုတဲ့ ကိန်းကို မပြောဘူး။
- ⚠️ Apify free plan ရဲ့ $5 ကုန်သွားပြီ (2026-11-18) — Maps discovery နဲ့ SF6b LinkedIn stage က Apify ပြန်မရမချင်း ရပ်နေတယ်။ Tavily လမ်းကြောင်းက အလုပ်ဖြစ်တယ်။

## Update — 2026-11-17 ညနေ (SF3 dynamic DM + WF00 v-next.9)

- SF3 v-next.3: hardcoded DM regex နဲ့ LLM ရဲ့ is_decision_maker claim ကို ဖယ်ပြီး၊ profile ရဲ့ decision_maker_titles နဲ့ deterministic phrase-match ပဲ သုံးတော့တယ် (fail-closed; dm_matched_title + dm_profile_version မှတ်တယ်)။ Wonder verdict = PROMOTE, conditions NONE။
- Canonical head = WF00 v-next.9 (SF3 call က v-next.3 ကို ညွှန်တယ်; ကျန်တာ v-next.8 အတိုင်း)။ Rollback = WF00 v-next.8။
- Pack: wf00-vnext9.json + sf3-vnext3.json အသစ်; wf00-vnext8.json + sf3-vnext2.json ကို superseded/ ထဲ ရွှေ့ထားတယ်။

## Update — 2026-11-19 (WF00 v-next.12 + SF6d X-Ray + SF8c; Wonder delta-2 ENABLE WITH CONDITIONS)

- **Canonical head = WF00 v-next.12** (wf00-vnext12.json)။ Rollback = WF00 v-next.11 (wf00-vnext11.json)။ Stage အသစ်တွေ: SF6d v-next.3 (sf6d-vnext3.json — X-Ray people stage, Tavily သုံး, Apify/LinkedIn login မလို), SF8 v-next.9 (sf8-vnext9.json — publish stage; People tab မှာ Source + Evidence column ပါလာပြီ), SF8c v-next (sf8c-vnext.json — People review write-back)။
- **DB migration အသစ်တွေ (import မလုပ်ခင် run ရမယ်):** sf6d-xray-columns.sql (xray claim/check column တွေ), sf6d-quarantine-columns.sql (companies.quarantined_at + quarantine_reason), people-reviews-table.sql (SF8c အတွက်)။
- **SF6d အလုပ်လုပ်ပုံ:** WF00 ထဲမှာ SF6b ပြီးရင် လာတယ်။ Context ထဲက `xray_people_enabled` နဲ့ ထိန်းတယ် (canonical မှာ **false**)။ Pick SQL ကိုယ်တိုင်ကလည်း flag ကို စစ်တယ် (fail-closed နှစ်ထပ်) + `quarantined_at IS NULL` ကိုပါ စစ်တယ်။ ကုမ္ပဏီတစ်ခုကို LinkedIn X-ray ရှာခ $0.006, Facebook page ရှာခ $0.006 (FB မရှိတဲ့ ကုမ္ပဏီတွေပဲ)။ ရှာပြီးရင် နောက် ရက် ၉၀ ကြာမှ ပြန်ရှာတယ်။
- **C9 quarantine:** scored pool ထဲက လုပ်ငန်းမဟုတ်တဲ့ row ၆၄ ခုကို DB ထဲမှာ quarantine လုပ်ထားတယ် (reason code နဲ့တကွ)။ အသစ်ဝင်လာတဲ့ ကုမ္ပဏီတွေက quarantine မဖြစ်သေးတဲ့ အနေအထားနဲ့ ဝင်လာတာမို့ — **အသစ် discovery run ပြီးရင် row အသစ်တွေကို အရင် census စစ်/quarantine လုပ်ပြီးမှ SF6d ကို ON ပါ** (Wonder condition 5)။ လက်တွေ့ လုပ်ပုံ: discovery run ကို SF6d OFF နဲ့ သွား → row အသစ် စစ် → နောက် run မှ SF6d ON။
- **⭐ Wonder delta-2 စည်းကမ်းတွေ (ENABLE WITH CONDITIONS, 2026-11-19):** (1) SF6d က save လုပ်တဲ့ လူတိုင်း + ဖြည့်တဲ့ Facebook page တိုင်းကို Muse က evidence နဲ့ ၁၀၀% ပြန်စစ်ရမယ် — တစ်ခုခု မှားရင် flag ကို ချက်ချင်း ပြန်ပိတ်ပြီး Wonder ကို အကြောင်းကြားရမယ်။ (2) Scope = FYF-Yangon pilot ပဲ; SF6b ဆက် OFF; hotel profile ကို production မသုံးရ; profile/geography အသစ် မချဲ့ရ (C13 အကြွေး မဆပ်ရသေး)။ (3) Borderline anchor (brand page/aggregator) အောက်က save တွေကို သီးသန့် ခွဲပြီး report လုပ်ရမယ်။ (4) SF8c ကို people အသစ် publish ဖြစ်တိုင်း run ရမယ်; ပထမဆုံး တကယ့် rejection ကို DB အထိ စစ်ရမယ်; reject လုပ်ပြီးသား လူ ပြန်ပေါ်လာရင် defect လို့ သတ်မှတ်တယ်။ (6) spend cap ကို လက်တွေ့ကျတဲ့ အဆင့်မှာ ထားပါ ($0.005 လို အရမ်းနည်းရင် SF5 က ရပ်ပြီး run ကြိုးစားနိုင်တယ် — မပြင်ရသေး)။ (7) SF6d code ကို တစ်ခုခု ပြောင်းရင် C12 သက်သေ ပျက်တယ် — ပြန်စမ်း + Wonder ပြန် review လိုတယ်။
- **SF8c (People review write-back):** People tab မှာ Decision/Note column (K/L) ထည့်ထားတယ်။ လူ reject လုပ်ချင်ရင် People tab မှာ အဲ့ဒီ row ရဲ့ Decision မှာ `rejected` လို့ ရေးပြီး Muse ကို ပြောပါ — Muse က SF8c ကို run ပေးမယ် (SF8c က sub-workflow မို့ သူ့ဘာသာ လက်နဲ့ run လို့ မရဘူး, WF00 ကလည်း မခေါ်ဘူး)။ DB က tavily_xray လူကို ဖျက်ပြီး people_reviews + audit event မှတ်တယ်။ Approve/hold ဆို မှတ်တမ်းပဲ။
- PROBE SF6d workflow (cfCEbLXRUKcDQAcg) ကို DB စစ်ဆေးရေး ကိရိယာအဖြစ် ဆက်ထားထားတယ် — sf6d/probe_run.py က သူ့ကို သုံးပြီး SQL run ပေးတယ်။


## SF0 Planner (2026-11-20, Wonder REV 2218 ratified)
- Notes NEVER mint allowlist tokens. Minting sources: authorised structured fields + registry vocabulary + FUNC stopwords only. (Permanent supersession of the original R5 wording; design amendment in DESIGN-v2.2-delta.md.)
- Planner model = muse-wonder-1.0 (SF0 only); all other tiers muse-spark-1.3 via WF00 context. C4 closed for the frozen tuple (27/30 golden, 0 unsafe). QUERY_DUP is a known accepted defect (11 instances, 4 fixtures, safe failures only).
