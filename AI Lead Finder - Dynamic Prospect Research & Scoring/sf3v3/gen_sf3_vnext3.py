import json, pathlib
BASE = pathlib.Path(__file__).resolve().parent
BASE.mkdir(parents=True, exist_ok=True)
def J(s): return json.dumps(s)

EXTRACT_SYS = (
"You are a people finder for B2B sales research. You receive a company and raw web evidence. "
"Find the people who own, founded, lead or work at THIS company. Return ONLY a JSON object: "
"{\"people\": [{\"full_name\": string, \"title\": string, \"linkedin_url\": string, \"evidence_url\": string, \"evidence_quote\": string}]}. "
"Every person MUST have an evidence_url copied from the evidence and a short EXACT quote copied from the evidence that names the person together with this company or their role in it. "
"A LinkedIn URL may only be included if it appears in the evidence. Never invent names, titles or URLs. "
"If no person can be tied to this company by the evidence, return an empty list."
)

PICK_SQL = """
SELECT COALESCE(jsonb_agg(p), '[]'::jsonb) AS candidates,
  (SELECT profile->'decision_maker_titles' FROM search_profiles WHERE id = $1::uuid AND version = $2) AS dm_titles
FROM (
  SELECT c.id::text AS company_id, c.name, c.category, c.location, c.website, s.fit_score,
    EXISTS (SELECT 1 FROM people pp WHERE pp.company_id = c.id) AS has_people,
    EXISTS (SELECT 1 FROM research_artifacts ra WHERE ra.company_id = c.id AND ra.field_name = 'people_search_pack') AS searched_before,
    EXISTS (SELECT 1 FROM selection_audit sa WHERE sa.run_id = $3 AND sa.workflow = 'SF5' AND sa.company_id = c.id::text AND sa.selection_reason = 'selected') AS audit_selected
  FROM companies c
  JOIN scores s ON s.company_id = c.id AND s.search_profile_id = $1::uuid AND s.profile_version = $2
  WHERE c.status NOT IN ('approved','rejected')
) p
""".strip()

CAP_CHECK_SQL = "SELECT COALESCE(SUM(cost_usd), 0)::float AS spent FROM cost_ledger WHERE run_id = $1"

STAGE_JS = r"""
const trig = $('When Executed by Another Workflow').item.json;
const pick = $input.first().json || {};
return [{ json: { run_id: trig.run_id || '', search_profile_id: trig.search_profile_id || '', profile_version: trig.profile_version || 1,
  min_fit: trig.min_fit || 30, max_companies: trig.max_companies || 3,
  spend_cap_usd: (trig.spend_cap_usd === undefined || trig.spend_cap_usd === null || trig.spend_cap_usd === '') ? null : Number(trig.spend_cap_usd),
  candidates: pick.candidates || [], dm_titles: Array.isArray(pick.dm_titles) ? pick.dm_titles : [] } }];
""".strip()

RANK_JS = r"""
const ctx = $('Stage Run Context').first().json;
const spent = Number(($('DB - Cap Check (F28)').first().json || {}).spent || 0);
const cands = ctx.candidates || [];
const minFit = ctx.min_fit || 30, maxC = ctx.max_companies || 3, cap = ctx.spend_cap_usd;
const PER = 0.024;
const sorted = [...cands].sort((a, b) => (Number(b.fit_score) - Number(a.fit_score)) || (a.company_id < b.company_id ? -1 : 1));
const eligible = sorted.filter(c => Number(c.fit_score) >= minFit && !c.has_people && !c.searched_before);
let cutoff = minFit;
if (eligible.length > maxC) cutoff = Number(eligible[maxC - 1].fit_score);
const audit = [], jobs = [], capBlockedIds = [];
let rank = 0, proj = spent, firstSkipDone = false;
for (const c of sorted) {
  const fit = Number(c.fit_score);
  let reason, r = null, first = false;
  if (c.has_people || c.searched_before) { reason = 'research_once_skip'; }
  else if (fit < minFit) { reason = 'below_cutoff'; }
  else {
    rank++; r = rank;
    if (rank <= maxC) {
      if (cap !== null && proj + PER > cap) { reason = 'cap_reached'; capBlockedIds.push(c.company_id); if (!firstSkipDone) { first = true; firstSkipDone = true; } }
      else { reason = 'selected'; proj += PER; jobs.push(c); }
    } else { reason = 'cap_reached'; if (!firstSkipDone) { first = true; firstSkipDone = true; } }
  }
  audit.push({ run_id: ctx.run_id || '', workflow: 'SF3', company_id: c.company_id, rank: r, fit_score: fit, cutoff, selection_reason: reason, is_first_skipped: first, audit_selected_sf5: !!c.audit_selected });
}
return [{ json: { run_id: ctx.run_id || '', jobs, audit_rows: audit, cap_blocked_ids: capBlockedIds,
  write_payload: JSON.stringify({ run_id: ctx.run_id || '', audit_rows: audit, cap_blocked_ids: capBlockedIds }) } }];
""".strip()

WRITE_SQL = """
WITH w AS (SELECT $1::jsonb AS j),
ins_audit AS (
  INSERT INTO selection_audit (run_id, workflow, company_id, rank, fit_score, cutoff, selection_reason, is_first_skipped)
  SELECT x->>'run_id', x->>'workflow', x->>'company_id', NULLIF(x->>'rank','')::int, (x->>'fit_score')::numeric, (x->>'cutoff')::numeric, x->>'selection_reason', (x->>'is_first_skipped')::boolean
  FROM w, jsonb_array_elements(w.j->'audit_rows') x
  ON CONFLICT (run_id, workflow, company_id) DO NOTHING RETURNING company_id),
ins_events AS (
  INSERT INTO people_search_events (run_id, company_id, workflow, stage, detail)
  SELECT w.j->>'run_id', (x->>'company_id')::uuid, 'SF3', 'picked', jsonb_build_object('fit_score', (x->>'fit_score')::numeric, 'rank', NULLIF(x->>'rank','')::int, 'sf5_selected', (x->>'audit_selected_sf5')::boolean)
  FROM w, jsonb_array_elements(w.j->'audit_rows') x WHERE x->>'selection_reason' = 'selected' RETURNING id),
ins_cap AS (
  INSERT INTO cost_ledger (run_id, workflow, provider, event_type, units, cost_usd, company_id, idempotency_key)
  SELECT w.j->>'run_id', 'SF3', 'tavily', 'cap_blocked', 0, 0, x, 'sf3:cap:' || (w.j->>'run_id') || ':' || x
  FROM w, jsonb_array_elements_text(w.j->'cap_blocked_ids') x
  ON CONFLICT (idempotency_key) DO NOTHING RETURNING id)
SELECT (SELECT count(*) FROM ins_audit) AS audit_rows, (SELECT count(*) FROM ins_events) AS picked_events, (SELECT count(*) FROM ins_cap) AS cap_blocked_rows
""".strip()

BUILD_JOBS_JS = r"""
const rank = $('Rank + Audit + Cap (F35)').first().json || {};
const jobs = rank.jobs || [];
if (!jobs.length) {
  const trig = $('When Executed by Another Workflow').item.json;
  return [{ json: { empty_run: true, stage: 'SF3', reason: 'no_companies_selected', fit_threshold: trig.min_fit || 30, search_profile_id: trig.search_profile_id || '', profile_version: trig.profile_version || 1, run_id: trig.run_id || '' } }];
}
return jobs.map(c => {
  const loc = (c.location || '').trim();
  const qLinkedin = (c.name + ' ' + loc + ' LinkedIn owner founder').trim();
  let domain = '';
  try { domain = (c.website || '').replace(/^https?:\/\//, '').replace(/^www\./, '').split('/')[0]; } catch (e) { domain = ''; }
  const realDomain = domain && domain.indexOf('facebook.com') === -1 && domain.indexOf('.') > -1;
  const qWeb = realDomain ? (c.name + ' ' + domain + ' team about owner founder').trim() : (c.name + ' ' + loc + ' about team owner founder').trim();
  let urls = [];
  if (realDomain) {
    const base = 'https://' + domain;
    urls = [base, base + '/about', base + '/team', base + '/contact'];
  } else if (c.website) { urls = [c.website]; }
  return { json: { company_id: c.company_id, name: c.name, category: c.category || '', location: loc, website: c.website || '', run_id: rank.run_id || '',
    mcp_linkedin: JSON.stringify({ query: qLinkedin, search_depth: 'basic', max_results: 5 }),
    mcp_web: JSON.stringify({ query: qWeb, search_depth: 'basic', max_results: 5 }),
    mcp_extract: JSON.stringify({ urls, extract_depth: 'basic', format: 'text' }) } };
});
""".strip()

REATTACH_JS = r"""
const jobs = $('Build Jobs').all().map(i => i.json);
return $input.all().map((item, idx) => {
  const job = jobs[idx] || {};
  let t = '';
  try { t = typeof item.json === 'string' ? item.json : JSON.stringify(item.json); } catch (e) { t = String(item.json); }
  return { json: { company_id: job.company_id, name: job.name, search1_text: t, mcp_input: job.mcp_web || '{}' } };
});
""".strip()

REATTACH2_JS = r"""
const jobs = $('Build Jobs').all().map(i => i.json);
const first = $('Reattach').all().map(i => i.json);
return $input.all().map((item, idx) => {
  const job = jobs[idx] || {};
  let t2 = '';
  try { t2 = typeof item.json === 'string' ? item.json : JSON.stringify(item.json); } catch (e) { t2 = String(item.json); }
  let extract = job.mcp_extract || '{"urls": []}';
  try { const p = JSON.parse(extract); if (!p.urls || !p.urls.length) extract = JSON.stringify({ urls: ['https://example.com'], extract_depth: 'basic', format: 'text' }); } catch (e) {}
  return { json: { company_id: job.company_id, name: job.name, search1_text: (first[idx] || {}).search1_text || '', search2_text: t2, mcp_input: extract } };
});
""".strip()

PACK_JS = r"""
const jobs = $('Build Jobs').all().map(i => i.json);
const searches = $('Reattach 2').all().map(i => i.json);
return $input.all().map((item, idx) => {
  const job = jobs[idx] || {};
  const s = searches[idx] || {};
  let siteText = '', sitePages = 0;
  try {
    let ej = item.json;
    if (typeof ej === 'string') ej = JSON.parse(ej);
    const results = (ej && ej.results) || [];
    sitePages = results.length;
    siteText = results.map(r => (r.raw_content || r.content || '')).filter(Boolean).join('\n');
  } catch (e) { siteText = ''; sitePages = 0; }
  let corpus = 'LINKEDIN SEARCH RESULTS:\n' + (s.search1_text || '') + '\n\nWEBSITE AND TEAM SEARCH RESULTS:\n' + (s.search2_text || '') + '\n\nCOMPANY SITE PAGES:\n' + siteText;
  if (corpus.length > 12000) corpus = corpus.slice(0, 12000);
  const userMsg = 'Company: ' + job.name + '\nCategory: ' + job.category + '\nLocation: ' + job.location + '\nWebsite: ' + job.website + '\n\nWEB EVIDENCE:\n' + corpus;
  return { json: { company_id: job.company_id, run_id: job.run_id, name: job.name, corpus, site_pages: sitePages,
    extract_payload: { model: 'muse-spark-1.3', temperature: 0.1, messages: [ { role: 'system', content: EXTRACT_SYS }, { role: 'user', content: userMsg } ] } } };
});
""".strip().replace('EXTRACT_SYS', J(EXTRACT_SYS))

PARSE_JS = r"""
const packs = $('Pack Evidence').all().map(i => i.json);
const stageCtx = $('Stage Run Context').first().json;
const dmTitles = (Array.isArray(stageCtx.dm_titles) ? stageCtx.dm_titles : []).map(t => ({ raw: String(t), norm: normPhrase(String(t)) })).filter(t => t.norm);
function normPhrase(s) { return String(s || '').toLowerCase().replace(/[^a-z0-9\u1000-\u109F]+/g, ' ').replace(/\s+/g, ' ').trim(); }
function norm(s) { return String(s || '').toLowerCase().replace(/\s+/g, ' ').trim(); }
function matchTitle(title) {
  const tN = ' ' + normPhrase(title || '') + ' ';
  for (const t of dmTitles) { if (tN.includes(' ' + t.norm + ' ')) return t.raw; }
  return '';
}
return $input.all().map((item, idx) => {
  const pack = packs[idx] || {};
  const corpusN = norm(pack.corpus || '');
  let content = '';
  try { content = item.json.choices[0].message.content || ''; } catch (e) {}
  content = content.replace(/```json/g, '').replace(/```/g, '').trim();
  let parsed = {};
  try { parsed = JSON.parse(content); } catch (e) { parsed = {}; }
  const seen = {};
  const people = [];
  for (const p of (parsed.people || [])) {
    if (!p || !p.full_name || !p.evidence_url || !p.evidence_quote) continue;
    const quoteN = norm(p.evidence_quote);
    if (!quoteN || corpusN.indexOf(quoteN) === -1) continue;
    const key = norm(p.full_name);
    if (seen[key]) continue;
    seen[key] = 1;
    const title = String(p.title || '');
    let li = String(p.linkedin_url || '');
    if (li.indexOf('linkedin.com') === -1) li = '';
    const matchedTitle = matchTitle(title);
    people.push({ full_name: String(p.full_name), title, linkedin_url: li,
      is_decision_maker: !!matchedTitle,
      dm_matched_title: matchedTitle || null, dm_profile_version: stageCtx.profile_version || null,
      evidence_url: String(p.evidence_url), evidence_quote: String(p.evidence_quote) });
  }
  const payload = { company_id: pack.company_id, run_id: pack.run_id || '', corpus: (pack.corpus || '').slice(0, 4000), people, site_pages: pack.site_pages || 0 };
  return { json: { payload: JSON.stringify(payload), company_id: pack.company_id, people_found: people.length, site_pages: pack.site_pages || 0 } };
});
""".strip()

SAVE_SQL = """
WITH p AS (SELECT $1::jsonb AS j),
pack AS (INSERT INTO research_artifacts (company_id, field_name, value, source_url, raw_content, critic_verdict)
  SELECT (j->>'company_id')::uuid, 'people_search_pack', jsonb_build_object('people_found', jsonb_array_length(j->'people'), 'site_pages', COALESCE((j->>'site_pages')::int, 0)), NULL, j->>'corpus', 'deterministic_quote_check' FROM p RETURNING id),
pi AS (INSERT INTO people (company_id, full_name, title, linkedin_url, is_decision_maker, source, raw_payload, source_url, evidence_quote, fetched_at)
  SELECT (j->>'company_id')::uuid, x->>'full_name', NULLIF(x->>'title',''), NULLIF(x->>'linkedin_url',''), COALESCE((x->>'is_decision_maker')::boolean, false), 'tavily_people_search', x, NULLIF(x->>'evidence_url',''), NULLIF(x->>'evidence_quote',''), now()
  FROM p, jsonb_array_elements(j->'people') x
  WHERE NOT EXISTS (SELECT 1 FROM people pp WHERE pp.company_id = (j->>'company_id')::uuid AND lower(pp.full_name) = lower(x->>'full_name'))
  RETURNING id),
sp AS (INSERT INTO spend_ledger (run_id, company_id, provider, action, credits)
  SELECT NULLIF(j->>'run_id','')::uuid, (j->>'company_id')::uuid, 'tavily', 'people_search', 3 FROM p RETURNING id),
cl1 AS (INSERT INTO cost_ledger (run_id, workflow, provider, event_type, units, cost_usd, company_id, idempotency_key)
  SELECT NULLIF(j->>'run_id',''), 'SF3', 'tavily', 'charge', 3, 0.024, j->>'company_id', 'sf3:tavily:' || (j->>'run_id') || ':' || (j->>'company_id') FROM p
  ON CONFLICT (idempotency_key) DO NOTHING RETURNING id),
cl2 AS (INSERT INTO cost_ledger (run_id, workflow, provider, event_type, units, cost_usd, company_id, idempotency_key)
  SELECT NULLIF(j->>'run_id',''), 'SF3', 'llm', 'charge', 1, NULL, j->>'company_id', 'sf3:llm:' || (j->>'run_id') || ':' || (j->>'company_id') FROM p
  ON CONFLICT (idempotency_key) DO NOTHING RETURNING id),
ev1 AS (INSERT INTO people_search_events (run_id, company_id, workflow, stage, detail)
  SELECT NULLIF(j->>'run_id',''), (j->>'company_id')::uuid, 'SF3', 'searched', jsonb_build_object('tavily_searches', 2, 'tavily_extract', true) FROM p RETURNING id),
ev2 AS (INSERT INTO people_search_events (run_id, company_id, workflow, stage, detail)
  SELECT NULLIF(j->>'run_id',''), (j->>'company_id')::uuid, 'SF3', 'site_fetched', jsonb_build_object('pages', COALESCE((j->>'site_pages')::int, 0)) FROM p RETURNING id),
ev3 AS (INSERT INTO people_search_events (run_id, company_id, workflow, stage, detail)
  SELECT NULLIF(j->>'run_id',''), (j->>'company_id')::uuid, 'SF3', 'people_saved', jsonb_build_object('count', (SELECT count(*) FROM pi)) FROM p RETURNING id)
SELECT (SELECT count(*) FROM pi) AS people_saved
""".strip()

RET_JS = r"""
const saves = $input.all().map(i => i.json);
const packs = $('Parse + Validate').all().map(i => i.json);
return [{ json: { success: true, companies_processed: saves.length,
  people_extracted: packs.reduce((a, s) => a + (s.people_found || 0), 0),
  people_saved: saves.reduce((a, s) => a + (Number(s.people_saved) || 0), 0),
  site_pages_fetched: packs.reduce((a, s) => a + (s.site_pages || 0), 0) } }];
""".strip()

AUDIT_CHECK_JS_D10 = r"""
const first = ($input.first() && $input.first().json) || {};
const failed = !!(first.error || first.message);
const trig = $('When Executed by Another Workflow').item.json || {};
const body = 'SF3 v-next.2 (D10 isolation): the F34/F35 selection-audit + funnel-events write FAILED for run ' + (trig.run_id || '') + '. People search continues - the write is isolated so its failure cannot block the search - but this run has no selection audit trail or picked events until the write is repaired.\nError: ' + String(first.message || first.error || 'unknown').slice(0, 400);
return [{ json: { audit_failed: failed, sendTo: 'victor.job154@gmail.com', subject: 'SF3 audit write failed - run ' + (trig.run_id || ''), body: body } }];
""".strip()

ENDCHECK_JS_D10 = r"""
const summary = ($('Return').first() && $('Return').first().json) || {};
const chk = ($('Audit Write Check (D10)').first() && $('Audit Write Check (D10)').first().json) || {};
return [{ json: Object.assign({}, summary, { audit_failed: !!chk.audit_failed, sendTo: chk.sendTo || 'victor.job154@gmail.com', subject: chk.subject || '', body: chk.body || '' }) }];
""".strip()

ENDPASS_JS_D10 = r"""
return $input.all();
""".strip()

FINALRET_JS_D10 = r"""
return [{ json: ($('Return').first() || {}).json || {} }];
""".strip()

out = []
out.append("import { workflow, node, trigger, sticky, expr, ifElse } from '@n8n/workflow-sdk';")
out.append(f"const aboutNote = sticky({J('SF3 v-next - People Finder (F35 + F34 audit + F28 ledger/cap). Changes vs v3: (1) pick returns ALL scored companies; a Rank + Audit + Cap node classifies each (selected / cap_reached / below_cutoff / research_once_skip, SF5-selected flagged) and writes selection_audit rows (workflow SF3) + people_search_events picked rows + cap_blocked ledger rows in one statement; a spend cap (optional spend_cap_usd input, $0.024/company = 3 Tavily credits at $0.008) blocks before any paid node. (2) NEW yield lever: Tavily EXTRACT of the company site (home/about/team/contact) merged into the evidence corpus - owners are usually named there, not in search snippets. (3) Every saved person carries source_url + evidence_quote + fetched_at (people columns added at F35; retention columns land at F21). (4) cost_ledger rows per company (tavily 3 units $0.024, llm 1 unit cost NULL) beside the legacy spend_ledger row (3 credits). Deterministic verbatim quote check unchanged. No emails guessed; no outreach created.')}, [], {{ color: 5 }});")
out.append("""
const subTrigger = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger',
  version: 1.1,
  config: {
    name: 'When Executed by Another Workflow',
    parameters: {
      workflowInputs: { values: [
        { name: 'search_profile_id', type: 'string' },
        { name: 'profile_version', type: 'number' },
        { name: 'run_id', type: 'string' },
        { name: 'max_companies', type: 'number' },
        { name: 'min_fit', type: 'number' },
        { name: 'spend_cap_usd', type: 'number' }
      ] }
    },
    position: [40, 400]
  },
  output: [{ search_profile_id: 'uuid', profile_version: 1, run_id: '', max_companies: 3, min_fit: 30, spend_cap_usd: 0 }]
});""")
out.append(f"""
const pickNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Pick Companies',
    position: [320, 400],
    parameters: {{
      operation: 'executeQuery',
      query: {J(PICK_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.search_profile_id, $json.profile_version || 1, $json.run_id || \\'\\' ] }}}}') }}
    }}
  }},
  output: [{{ candidates: [] }}]
}});""")
out.append(f"""
const stageNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Stage Run Context',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(STAGE_JS)} }},
    position: [600, 400]
  }},
  output: [{{ run_id: '', candidates: [] }}]
}});""")
out.append(f"""
const capCheckNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Cap Check (F28)',
    position: [880, 400],
    parameters: {{
      operation: 'executeQuery',
      query: {J(CAP_CHECK_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.run_id ] }}}}') }}
    }},
    executeOnce: true
  }},
  output: [{{ spent: 0 }}]
}});""")
out.append(f"""
const rankNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Rank + Audit + Cap (F35)',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(RANK_JS)} }},
    position: [1160, 400]
  }},
  output: [{{ jobs: [], audit_rows: [], write_payload: '{{}}' }}]
}});""")
out.append(f"""
const writeNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Write Audit + Events (F34/F35)',
    position: [1440, 400],
    onError: 'continueRegularOutput',
    parameters: {{
      operation: 'executeQuery',
      query: {J(WRITE_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.write_payload ] }}}}') }}
    }}
  }},
  output: [{{ audit_rows: 0, picked_events: 0, cap_blocked_rows: 0 }}]
}});""")
out.append(f"""
const auditCheckNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Audit Write Check (D10)',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(AUDIT_CHECK_JS_D10)} }},
    position: [1560, 400]
  }},
  output: [{{ audit_failed: false }}]
}});
const jobsNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Build Jobs',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(BUILD_JOBS_JS)} }},
    position: [1720, 400]
  }},
  output: [{{ company_id: 'uuid', mcp_linkedin: '{{}}', mcp_web: '{{}}', mcp_extract: '{{}}' }}]
}});""")
out.append("""
const hasJobs = ifElse({
  version: 2.2,
  config: {
    name: 'Has Jobs?',
    position: [1860, 400],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ !$json.empty_run }}'), operator: { type: 'boolean', operation: 'true' } }],
        combinator: 'and'
      }
    }
  }
});""")
out.append("""
const emptyReturn = node({
  type: 'n8n-nodes-base.set',
  version: 3.4,
  config: {
    name: 'Return - Empty Run Summary',
    position: [2000, 560],
    parameters: {
      mode: 'manual',
      includeOtherFields: false,
      assignments: { assignments: [
        { id: 'a1', name: 'success', value: true, type: 'boolean' },
        { id: 'a2', name: 'companies_processed', value: 0, type: 'number' },
        { id: 'a3', name: 'people_extracted', value: 0, type: 'number' },
        { id: 'a4', name: 'people_saved', value: 0, type: 'number' },
        { id: 'a5', name: 'site_pages_fetched', value: 0, type: 'number' }
      ] }
    }
  },
  output: [{ success: true, companies_processed: 0, people_saved: 0 }]
});""")
mcp_params = {
    'serverTransport': 'httpStreamable',
    'endpointUrl': 'https://mcp.tavily.com/mcp/',
    'authentication': 'mcpOAuth2Api',
    'inputMode': 'json',
    'options': { 'timeout': 120000, 'convertToBinary': False }
}
def mcp_node(var, name, pos, tool, field):
    p = dict(mcp_params)
    p['tool'] = { '__rl': True, 'mode': 'list', 'value': tool, 'cachedResultName': tool }
    return f"""
const {var} = node({{
  type: '@n8n/n8n-nodes-langchain.mcpClient',
  version: 1.1,
  config: {{
    name: {J(name)},
    position: [{pos}, 400],
    parameters: {{ {', '.join(f'{k}: {J(v)}' for k, v in p.items())}, jsonInput: expr('{{{{ $json.{field} }}}}') }}
  }},
  output: [{{}}]
}});"""

out.append(mcp_node('mcpSearch1', 'Tavily MCP - Search LinkedIn', 2000, 'tavily_search', 'mcp_linkedin'))
out.append(f"""
const reattachNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Reattach',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(REATTACH_JS)} }},
    position: [2280, 400]
  }},
  output: [{{ company_id: 'uuid', search1_text: '', mcp_input: '{{}}' }}]
}});""")
out.append(mcp_node('mcpSearch2', 'Tavily MCP - Search Web', 2560, 'tavily_search', 'mcp_input'))
out.append(f"""
const reattach2Node = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Reattach 2',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(REATTACH2_JS)} }},
    position: [2840, 400]
  }},
  output: [{{ company_id: 'uuid', search1_text: '', search2_text: '', mcp_input: '{{}}' }}]
}});""")
out.append(mcp_node('mcpExtract', 'Tavily MCP - Extract Site', 3120, 'tavily_extract', 'mcp_input'))
out.append(f"""
const packNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Pack Evidence',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(PACK_JS)} }},
    position: [3400, 400]
  }},
  output: [{{ company_id: 'uuid', corpus: '', site_pages: 0, extract_payload: {{}} }}]
}});""")
out.append(f"""
const extractNode = node({{
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {{
    name: 'LLM - People Extractor',
    position: [3680, 400],
    parameters: {{
      method: 'POST',
      url: 'https://api.meta.ai/v1/chat/completions',
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendBody: true,
      contentType: 'json',
      specifyBody: 'json',
      jsonBody: expr('{{{{ JSON.stringify($json.extract_payload) }}}}'),
      options: {{ timeout: 120000 }}
    }}
  }},
  output: [{{ choices: [{{ message: {{ content: '{{"people": []}}' }} }}] }}]
}});""")
out.append(f"""
const parseNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Parse + Validate',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(PARSE_JS)} }},
    position: [3960, 400]
  }},
  output: [{{ payload: '{{}}', people_found: 0, site_pages: 0 }}]
}});""")
out.append(f"""
const saveNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Save People',
    position: [4240, 400],
    parameters: {{
      operation: 'executeQuery',
      query: {J(SAVE_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.payload ] }}}}') }}
    }}
  }},
  output: [{{ people_saved: 0 }}]
}});""")
out.append(f"""
const retNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Return',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(RET_JS)} }},
    position: [4520, 400]
  }},
  output: [{{ success: true, companies_processed: 0, people_saved: 0, site_pages_fetched: 0 }}]
}});""")
out.append(f"""
const endCheck = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Audit Alert Gate (D10)',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(ENDCHECK_JS_D10)} }},
    position: [4700, 400]
  }},
  output: [{{ success: true, audit_failed: false }}]
}});
const endIf = ifElse({{
  version: 2.2,
  config: {{
    name: 'Audit Failed? (end)',
    position: [4880, 400],
    parameters: {{
      conditions: {{
        options: {{ caseSensitive: true, typeValidation: 'loose' }},
        conditions: [{{ leftValue: expr('{{{{ $json.audit_failed }}}}'), operator: {{ type: 'boolean', operation: 'true' }} }}],
        combinator: 'and'
      }}
    }}
  }}
}});
const alertDraft = node({{
  type: 'n8n-nodes-base.gmail', version: 2.1,
  config: {{
    name: 'Gmail - Audit Alert Draft (D10, NEVER SENDS)',
    parameters: {{ resource: 'draft', operation: 'create', sendTo: expr('{{{{ $json.sendTo }}}}'), subject: expr('{{{{ $json.subject }}}}'), emailType: 'text', message: expr('{{{{ $json.body }}}}'), options: {{}} }},
    credentials: {{ gmailOAuth2: newCredential('Gmail') }}, position: [5060, 320]
  }},
  output: [{{ id: 'draft-id' }}]
}});
const endPass = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Audit OK Pass (end)',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(ENDPASS_JS_D10)} }},
    position: [5060, 480]
  }},
  output: [{{ success: true }}]
}});
const finalReturn = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Return - Final (D10)',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(FINALRET_JS_D10)} }},
    position: [5240, 400]
  }},
  output: [{{ success: true, companies_processed: 0, people_saved: 0, site_pages_fetched: 0 }}]
}});
""")
out.append("""
export default workflow('leadfinder-sf3-vnext3', 'SF3 v-next.3 - People Finder (dynamic DM titles) + Site Extract + Audit + Cap + Isolation (F35+D10)')
  .add(aboutNote)
  .add(subTrigger)
  .to(pickNode)
  .to(stageNode)
  .to(capCheckNode)
  .to(rankNode)
  .to(writeNode)
  .to(auditCheckNode)
  .to(jobsNode)
  .to(hasJobs
    .onTrue(mcpSearch1
  .to(reattachNode)
  .to(mcpSearch2)
  .to(reattach2Node)
  .to(mcpExtract)
  .to(packNode)
  .to(extractNode)
  .to(parseNode)
  .to(saveNode)
  .to(retNode)
  .to(endCheck)
  .to(endIf
    .onTrue(alertDraft.to(finalReturn))
    .onFalse(endPass.to(finalReturn))))
    .onFalse(emptyReturn)
  );""")
code = '\n'.join(out) + '\n'
(BASE/'sf3vnext3.ts').write_text(code)
json.dump({"code": code, "name": "SF3 v-next.3 - People Finder (dynamic DM titles) + Site Extract + Audit + Cap + Isolation (F35+D10)"}, open(BASE/'create-sf3vnext3.json','w'))
print('sf3 v-next.2 generated', len(code))
