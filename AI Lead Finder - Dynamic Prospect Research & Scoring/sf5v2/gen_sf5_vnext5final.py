import json, pathlib
BASE = pathlib.Path(__file__).resolve().parent
def J(s): return json.dumps(s)

RESEARCH_SYS = (
"You are a research extractor. You receive a company and raw web evidence. "
"Extract ONLY facts the evidence explicitly supports. Return ONLY a JSON object: "
"{\"summary\": string, \"facts\": [{\"field\": string, \"value\": string, \"evidence_url\": string, \"evidence_quote\": string, \"confidence\": number}], "
"\"signals\": [{\"signal_type\": \"hiring|expansion|new_post|review_activity|other\", \"detail\": string, \"evidence_url\": string}], "
"\"people\": [{\"full_name\": string, \"title\": string, \"evidence_url\": string}]}. "
"Every fact, signal and person MUST include an evidence_url copied from the evidence; every fact MUST include a short exact evidence_quote. "
"If the evidence does not support something, leave it out. Never guess or invent contact details, names or numbers."
)
CRITIC_SYS = (
"You are a strict fact-checker. You receive raw evidence and extracted facts. For each fact, decide whether the evidence text directly supports it. "
"Return ONLY JSON: {\"verdicts\": [{\"field\": string, \"supported\": true}]}. "
"If the evidence_quote is not present in, or clearly supported by, the evidence text, supported must be false."
)

BUILD_JOBS_JS = r"""
const trig = $('When Executed by Another Workflow').item.json;
const picks = ($('Rank + Audit (F34)').first().json.picks || []);
if (!picks.length) {
  return [{ json: { empty_run: true, stage: 'SF5', reason: 'no_companies_met_fit_threshold', fit_threshold: trig.min_fit || 36, search_profile_id: trig.search_profile_id || '', profile_version: trig.profile_version || 1, run_id: trig.run_id || '' } }];
}
return picks.map(c => {
  const q = (c.name + ' ' + (c.category || '') + ' ' + (c.location || '')).trim();
  return { json: { company_id: c.company_id, name: c.name, category: c.category || '', location: c.location || '', website: c.website || '', run_id: trig.run_id || '', spend_cap_usd: (trig.spend_cap_usd === undefined || trig.spend_cap_usd === null || trig.spend_cap_usd === '' ? null : Number(trig.spend_cap_usd)), mcp_input: JSON.stringify({ query: q, search_depth: 'basic', max_results: 5 }) } };
});
""".strip()

PACK_JS = r"""
const jobs = $('Build Jobs').all().map(i => i.json);
return $input.all().map((item, idx) => {
  const job = jobs[idx] || {};
  let text = '';
  try { text = typeof item.json === 'string' ? item.json : JSON.stringify(item.json); } catch (e) { text = String(item.json); }
  if (text.length > 7000) text = text.slice(0, 7000);
  const userMsg = 'Company: ' + job.name + '\nCategory: ' + job.category + '\nLocation: ' + job.location + '\nWebsite: ' + job.website + '\n\nWEB EVIDENCE:\n' + text;
  return { json: { company_id: job.company_id, run_id: job.run_id, name: job.name, corpus: text,
    research_payload: { model: 'muse-spark-1.3', temperature: 0.1, messages: [ { role: 'system', content: RESEARCH_SYS }, { role: 'user', content: userMsg } ] } } };
});
""".strip().replace('RESEARCH_SYS', J(RESEARCH_SYS))

PARSE_JS = r"""
const packs = $('Pack Evidence').all().map(i => i.json);
const TYPES = { hiring: 1, job_change: 1, funding: 1, expansion: 1, new_post: 1, review_activity: 1, other: 1 };
return $input.all().map((item, idx) => {
  const pack = packs[idx] || {};
  let content = '';
  try { content = item.json.choices[0].message.content || ''; } catch (e) {}
  content = content.replace(/```json/g, '').replace(/```/g, '').trim();
  let parsed = {};
  try { parsed = JSON.parse(content); } catch (e) { parsed = {}; }
  const facts = (parsed.facts || []).filter(f => f && f.field && f.value && f.evidence_url && f.evidence_quote)
    .map(f => ({ field: String(f.field), value: String(f.value), evidence_url: String(f.evidence_url), evidence_quote: String(f.evidence_quote), confidence: Number(f.confidence) || 0.5 }));
  const signals = (parsed.signals || []).filter(s => s && s.detail && s.evidence_url)
    .map(s => ({ signal_type: TYPES[s.signal_type] ? s.signal_type : 'other', detail: String(s.detail), evidence_url: String(s.evidence_url) }));
  const people = (parsed.people || []).filter(p => p && p.full_name && p.evidence_url)
    .map(p => ({ full_name: String(p.full_name), title: String(p.title || ''), evidence_url: String(p.evidence_url) }));
  const criticMsg = 'EVIDENCE:\n' + (pack.corpus || '') + '\n\nFACTS TO CHECK:\n' + JSON.stringify(facts.map(f => ({ field: f.field, value: f.value, evidence_quote: f.evidence_quote })), null, 1);
  return { json: { company_id: pack.company_id, run_id: pack.run_id, summary: String(parsed.summary || ''), facts, signals, people, corpus: pack.corpus || '',
    critic_payload: { model: 'muse-spark-1.3', temperature: 0, messages: [ { role: 'system', content: CRITIC_SYS }, { role: 'user', content: criticMsg } ] } } };
});
""".strip().replace('CRITIC_SYS', J(CRITIC_SYS))

CAP_CHECK_SQL = """
SELECT COALESCE(SUM(cost_usd), 0)::float AS spent_usd FROM cost_ledger WHERE run_id = $1
""".strip()

CAP_GATE_JS = r"""
// COST_RATES_V1 (from F15 cost reconstruction, 2026-11-16):
// tavily: $25 face / 3,125 credits = $0.008 per credit (credits were a free claim; face value used).
// llm (Meta Model API muse-spark-1.3): rate UNKNOWN -> excluded from estimates, ledgered with cost_usd NULL (rate_missing).
// apify: free plan, unmetered -> rate unknown (ledgered in SF2 v-next when built).
const TAVILY_CREDIT_USD = 0.008;
const EST_NEXT_USD = TAVILY_CREDIT_USD; // one basic Tavily search per company
const spent = Number(($('DB - Cap Check (F28)').first().json || {}).spent_usd || 0);
// NOTE: the Cap Check Postgres node REPLACES the item stream with its result row,
// so the job items are reattached from 'Build Jobs' here (order + count preserved).
const jobItems = $('Build Jobs').all().map(i => i.json);
return jobItems.map(j => {
  if (j.empty_run) return { json: Object.assign({}, j, { cap_blocked: false, spent_usd: spent }) };
  const cap = (j.spend_cap_usd === undefined ? null : j.spend_cap_usd);
  const blocked = cap !== null && (spent + EST_NEXT_USD) > cap;
  return { json: Object.assign({}, j, { cap_blocked: blocked, spent_usd: spent, est_next_usd: EST_NEXT_USD }) };
});
""".strip()

CAP_BLOCKED_SQL = """
INSERT INTO cost_ledger (run_id, workflow, provider, event_type, units, cost_usd, company_id, idempotency_key)
VALUES ($1, 'SF5 v-next.4', 'tavily', 'cap_blocked', 1, 0.008, $2, 'sf5:cap:' || $1 || ':' || $2)
ON CONFLICT (idempotency_key) DO NOTHING
""".strip()

GATE_JS = r"""
function normText(s) {
  return String(s || '').normalize('NFKC')
    .replace(/[\u2018\u2019]/g, "'").replace(/[\u201C\u201D]/g, '"')
    .replace(/\s+/g, ' ').trim();
}
function sectionsOf(corpus) {
  const map = {};
  let parsed = null;
  try { parsed = JSON.parse(corpus); } catch (e) {}
  const results = parsed && ((parsed.structuredContent && parsed.structuredContent.results) || parsed.results);
  if (Array.isArray(results)) {
    for (const r of results) if (r && r.url) map[r.url] = String(r.content || r.raw_content || '');
    return map;
  }
  const re = /\[([^\]]+)\]\s*\n/g; let m; const idx = [];
  while ((m = re.exec(corpus)) !== null) idx.push({ url: m[1], at: m.index, from: re.lastIndex });
  if (idx.length) {
    idx.forEach((s, i) => { map[s.url] = corpus.slice(s.from, i + 1 < idx.length ? idx[i + 1].at : corpus.length); });
    return map;
  }
  return { '': corpus };
}
function findSection(map, url) {
  if (map[url] !== undefined) return map[url];
  const alt = url.endsWith('/') ? url.slice(0, -1) : url + '/';
  if (map[alt] !== undefined) return map[alt];
  return undefined;
}
return $input.all().map(item => {
  const j = item.json;
  const map = sectionsOf(j.corpus || '');
  const verified = [], failures = [];
  for (const f of (j.facts || [])) {
    const sec = findSection(map, f.evidence_url);
    if (sec === undefined) { failures.push(Object.assign({}, f, { verification_failure: 'url_unresolved' })); continue; }
    if (!normText(sec).includes(normText(f.evidence_quote))) { failures.push(Object.assign({}, f, { verification_failure: 'quote_not_verbatim' })); continue; }
    verified.push(Object.assign({}, f, { quote_verified: true }));
  }
  const criticMsg = 'EVIDENCE:\n' + (j.corpus || '') + '\n\nFACTS TO CHECK:\n' + JSON.stringify(verified.map(f => ({ field: f.field, value: f.value, evidence_quote: f.evidence_quote })), null, 1);
  return { json: Object.assign({}, j, { facts: verified, gate_failures: failures,
    critic_payload: { model: 'muse-spark-1.3', temperature: 0, messages: [ { role: 'system', content: CRITIC_SYS }, { role: 'user', content: criticMsg } ] } }) };
});
""".strip().replace('CRITIC_SYS', J(CRITIC_SYS))

SAVE_JS = r"""
const extracts = $('Verify Gate (F24)').all().map(i => i.json);
return $input.all().map((item, idx) => {
  const ex = extracts[idx] || { facts: [], signals: [], people: [], corpus: '', summary: '' };
  let content = '';
  try { content = item.json.choices[0].message.content || ''; } catch (e) {}
  content = content.replace(/```json/g, '').replace(/```/g, '').trim();
  let verdicts = [];
  try { verdicts = JSON.parse(content).verdicts || []; } catch (e) {}
  const ok = {};
  for (const v of verdicts) if (v && v.field) ok[v.field] = v.supported === true;
  const facts = (ex.facts || []).filter(f => ok[f.field]);
  const payload = { company_id: ex.company_id, run_id: ex.run_id || '', summary: ex.summary || '', corpus: (ex.corpus || '').slice(0, 4000), facts, gate_failures: ex.gate_failures || [], signals: ex.signals || [], people: ex.people || [] };
  return { json: { payload: JSON.stringify(payload), company_id: ex.company_id, facts_kept: facts.length, facts_dropped: (ex.facts || []).length - facts.length } };
});
""".strip()

RET_JS = r"""
const saves = $input.all().map(i => i.json);
return [{ json: { success: true, researched: saves.length,
  facts_saved: saves.reduce((a, s) => a + (s.facts_saved || 0), 0),
  signals_saved: saves.reduce((a, s) => a + (s.signals_saved || 0), 0),
  people_saved: saves.reduce((a, s) => a + (s.people_saved || 0), 0) } }];
""".strip()

PICK_SQL = """
SELECT COALESCE(jsonb_agg(cand ORDER BY fit_score DESC, company_id ASC), '[]'::jsonb) AS candidates
FROM (
  SELECT c.id::text AS company_id, c.name, c.category, c.location, c.website, s.fit_score,
         EXISTS (SELECT 1 FROM research_artifacts ra WHERE ra.company_id = c.id) AS has_research
  FROM companies c
  JOIN scores s ON s.company_id = c.id AND s.search_profile_id = $1::uuid AND s.profile_version = $2
  WHERE c.status NOT IN ('approved','rejected')
) cand
""".strip()


CLAIM_SQL = "UPDATE companies SET research_claimed_at = now(), research_claim_run_id = $1 WHERE id = $2::uuid AND research_claimed_at IS NULL RETURNING id::text AS claimed_company_id"
FILTER_JS = r"""
const claimed = new Set($input.all().map(i => String(i.json.claimed_company_id || '')).filter(Boolean));
const jobs = $('Cap Gate (F28)').all().map(i => i.json).filter(j => !j.empty_run && !j.cap_blocked && claimed.has(String(j.company_id)));
if (!jobs.length) return [{ json: { _claim_none: true, empty_run: true, stage: 'SF5', researched: 0, facts_saved: 0, signals_saved: 0, people_saved: 0 } }];
return jobs.map(j => ({ json: { ...j, _claim_none: false } }));
""".strip()

RANK_JS = r"""
const trig = $('When Executed by Another Workflow').item.json;
const minFit = Number(trig.min_fit || 36), maxR = Number(trig.max_research || 3), runId = trig.run_id || '';
const cands = ($input.first().json.candidates || []);
const researchable = cands.filter(c => !c.has_research && Number(c.fit_score) >= minFit);
const cutoff = researchable.length > maxR ? Number(researchable[maxR - 1].fit_score) : minFit;
let rank = 0;
const audit = cands.map(c => {
  let reason, r = null, first = false;
  if (c.has_research) reason = 'research_once_skip';
  else if (Number(c.fit_score) < minFit) reason = 'below_cutoff';
  else { rank++; r = rank; if (rank <= maxR) reason = 'selected'; else { reason = 'cap_reached'; if (rank === maxR + 1) first = true; } }
  return { run_id: runId, workflow: 'SF5 v-next.4', company_id: c.company_id, rank: r, fit_score: Number(c.fit_score), cutoff, selection_reason: reason, is_first_skipped: first };
});
const picks = researchable.slice(0, maxR).map(c => ({ company_id: c.company_id, name: c.name, category: c.category, location: c.location, website: c.website, fit_score: c.fit_score }));
return [{ json: { picks, audit_payload: JSON.stringify(audit), audit_count: audit.length } }];
""".strip()

AUDIT_SQL = """
INSERT INTO selection_audit (run_id, workflow, company_id, rank, fit_score, cutoff, selection_reason, is_first_skipped)
SELECT x->>'run_id', x->>'workflow', x->>'company_id', NULLIF(x->>'rank', '')::int, (x->>'fit_score')::numeric, (x->>'cutoff')::numeric, x->>'selection_reason', (x->>'is_first_skipped')::boolean
FROM jsonb_array_elements($1::jsonb) x
ON CONFLICT (run_id, workflow, company_id) DO NOTHING
""".strip()


SAVE_SQL = """
WITH p AS (SELECT $1::jsonb AS j),
pack AS (INSERT INTO research_artifacts (company_id, field_name, value, source_url, raw_content, critic_verdict)
  SELECT (j->>'company_id')::uuid, 'research_pack', jsonb_build_object('summary', j->>'summary'), NULL, j->>'corpus', 'unchecked' FROM p RETURNING id),
fi AS (INSERT INTO research_artifacts (company_id, field_name, value, source_url, critic_verdict, quote_verified, quote_verified_at)
  SELECT (j->>'company_id')::uuid, x->>'field', x, x->>'evidence_url', 'supported', true, now() FROM p, jsonb_array_elements(j->'facts') x RETURNING id),
gf AS (INSERT INTO research_artifacts (company_id, field_name, value, source_url, critic_verdict, quote_verified, verification_failure)
  SELECT (j->>'company_id')::uuid, x->>'field', x, x->>'evidence_url', 'dropped_gate', false, x->>'verification_failure' FROM p, jsonb_array_elements(COALESCE(j->'gate_failures', '[]'::jsonb)) x RETURNING id),
si AS (INSERT INTO signals (company_id, signal_type, detail, evidence_url)
  SELECT (j->>'company_id')::uuid, COALESCE(x->>'signal_type','other'), x->>'detail', x->>'evidence_url' FROM p, jsonb_array_elements(j->'signals') x RETURNING id),
pi AS (INSERT INTO people (company_id, full_name, title, source, raw_payload)
  SELECT (j->>'company_id')::uuid, x->>'full_name', x->>'title', 'tavily_research', x FROM p, jsonb_array_elements(j->'people') x RETURNING id),
sp AS (INSERT INTO spend_ledger (run_id, company_id, provider, action, credits)
  SELECT NULLIF(j->>'run_id','')::uuid, (j->>'company_id')::uuid, 'tavily', 'research_call', 1 FROM p RETURNING id),
up AS (UPDATE companies SET status = 'researched' WHERE id = (SELECT (j->>'company_id')::uuid FROM p) RETURNING id),
clt AS (INSERT INTO cost_ledger (run_id, workflow, provider, event_type, units, cost_usd, company_id, idempotency_key)
  SELECT NULLIF(j->>'run_id', ''), 'SF5 v-next.4', 'tavily', 'charge', 1, 0.008, (j->>'company_id')::uuid::text, 'sf5:tavily:' || COALESCE(NULLIF(j->>'run_id', ''), 'norun') || ':' || (j->>'company_id') FROM p ON CONFLICT (idempotency_key) DO NOTHING RETURNING id),
cll AS (INSERT INTO cost_ledger (run_id, workflow, provider, event_type, units, cost_usd, company_id, idempotency_key)
  SELECT NULLIF(j->>'run_id', ''), 'SF5 v-next.4', 'llm', 'charge', 2, NULL, (j->>'company_id')::uuid::text, 'sf5:llm:' || COALESCE(NULLIF(j->>'run_id', ''), 'norun') || ':' || (j->>'company_id') FROM p ON CONFLICT (idempotency_key) DO NOTHING RETURNING id)
SELECT (SELECT count(*) FROM fi) AS facts_saved, (SELECT count(*) FROM si) AS signals_saved, (SELECT count(*) FROM pi) AS people_saved, (SELECT count(*) FROM gf) AS gate_dropped, (SELECT count(*) FROM clt) + (SELECT count(*) FROM cll) AS ledger_rows
""".strip()

out = []
out.append("import { workflow, node, trigger, sticky, expr, ifElse } from '@n8n/workflow-sdk';")
out.append(f"const aboutNote = sticky({J('SF5 - Research + Critic (Tavily). Picks the highest-fit scored companies not yet researched, searches each via the Tavily MCP server (standalone MCP Client node, generic MCP OAuth2 credential), extracts ONLY evidence-bound facts with an LLM, drops anything a strict critic cannot verify against the evidence, and saves artifacts/signals/people + a spend-ledger row. Marks the company researched. No outreach is created here.')}, [], {{ color: 5 }});")
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
        { name: 'max_research', type: 'number' },
        { name: 'min_fit', type: 'number' },
        { name: 'spend_cap_usd', type: 'number' }
      ] }
    },
    position: [40, 400]
  },
  output: [{ search_profile_id: 'uuid', profile_version: 1, run_id: '', max_research: 3, min_fit: 36, spend_cap_usd: 100 }]
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
      options: {{ queryReplacement: expr('{{{{ [ $json.search_profile_id, $json.profile_version || 1 ] }}}}') }}
    }}
  }},
  output: [{{ company_id: 'uuid', name: 'Shop', fit_score: 50 }}]
}});""")
out.append(f"""
const rankNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Rank + Audit (F34)',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(RANK_JS)} }},
    position: [600, 400]
  }},
  output: [{{ picks: [], audit_payload: '[]', audit_count: 0 }}]
}});""")
AUDIT_CHECK_JS_D4 = r"""
const first = ($input.first() && $input.first().json) || {};
const failed = !!first.error;
const trig = $('When Executed by Another Workflow').item.json || {};
const body = 'SF5 v-next.5 (D4 isolation): the F34 selection-audit write FAILED for run ' + (trig.run_id || '') + '. Research continues - the audit write is isolated so its failure cannot block the pick - but this run has no selection audit trail until the write is repaired.\nError: ' + String(first.message || first.error || 'unknown').slice(0, 400);
return [{ json: { audit_failed: failed, sendTo: 'owner@example.com', subject: 'SF5 audit write failed - run ' + (trig.run_id || ''), body: body } }];
""".strip()
out.append(f"""
const auditNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Write Selection Audit (F34)',
    position: [740, 400],
    onError: 'continueRegularOutput',
    parameters: {{
      operation: 'executeQuery',
      query: {J(AUDIT_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.audit_payload ] }}}}') }}
    }}
  }},
  output: [{{ id: 1 }}]
}});""")
out.append(f"""
const auditCheck = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Audit Write Check (D4)',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(AUDIT_CHECK_JS_D4)} }},
    position: [860, 400]
  }},
  output: [{{ audit_failed: false, sendTo: 'x', subject: 's', body: 'b' }}]
}});""")
out.append("""
const auditIf = ifElse({
  version: 2.2,
  config: {
    name: 'Audit Failed?',
    position: [980, 400],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ $json.audit_failed }}'), operator: { type: 'boolean', operation: 'true' } }],
        combinator: 'and'
      }
    }
  }
});""")
out.append("""
const auditPass = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Audit OK Pass (D4)',
    parameters: { mode: 'runOnceForAllItems', jsCode: "return $input.all();" },
    position: [1100, 460]
  },
  output: [{ audit_failed: false }]
});""")
out.append(f"""
const alertDraft = node({{
  type: 'n8n-nodes-base.gmail',
  version: 2.1,
  config: {{
    name: 'Gmail - Audit Alert Draft (D4, NEVER SENDS)',
    parameters: {{ resource: 'draft', operation: 'create', sendTo: expr('{{{{ $json.sendTo }}}}'), subject: expr('{{{{ $json.subject }}}}'), emailType: 'text', message: expr('{{{{ $json.body }}}}'), options: {{}} }},
    credentials: {{ gmailOAuth2: newCredential('Gmail') }},
    position: [1100, 300]
  }},
  output: [{{ id: 'draft-id' }}]
}});""")
out.append(f"""
const jobsNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Build Jobs',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(BUILD_JOBS_JS)} }},
    position: [600, 400]
  }},
  output: [{{ company_id: 'uuid', mcp_input: '{{}}' }}]
}});""")

out.append(f"""
const capCheckNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Cap Check (F28)',
    position: [740, 400],
    executeOnce: true,
    parameters: {{
      operation: 'executeQuery',
      query: {J(CAP_CHECK_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.run_id ] }}}}') }}
    }}
  }},
  output: [{{ spent_usd: 0 }}]
}});""")
out.append(f"""
const capGateNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Cap Gate (F28)',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(CAP_GATE_JS)} }},
    position: [880, 400]
  }},
  output: [{{ company_id: 'uuid', cap_blocked: false }}]
}});""")
out.append("""
const capIf = ifElse({
  version: 2.2,
  config: {
    name: 'Cap OK? (D4)',
    position: [1020, 400],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ !$json.cap_blocked }}'), operator: { type: 'boolean', operation: 'true' } }],
        combinator: 'and'
      }
    }
  }
});""")
out.append(f"""
const capInsertNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Insert Cap Blocked (F28)',
    position: [1160, 240],
    parameters: {{
      operation: 'executeQuery',
      query: {J(CAP_BLOCKED_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.run_id, $json.company_id ] }}}}') }}
    }}
  }},
  output: [{{ id: 1 }}]
}});""")
out.append("""
const hasJobs = ifElse({
  version: 2.2,
  config: {
    name: 'Has Jobs?',
    position: [740, 400],
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
    position: [880, 560],
    parameters: {
      mode: 'manual',
      includeOtherFields: false,
      assignments: { assignments: [
        { id: 'a1', name: 'success', value: true, type: 'boolean' },
        { id: 'a2', name: 'researched', value: 0, type: 'number' },
        { id: 'a3', name: 'facts_saved', value: 0, type: 'number' },
        { id: 'a4', name: 'signals_saved', value: 0, type: 'number' },
        { id: 'a5', name: 'people_saved', value: 0, type: 'number' }
      ] }
    }
  },
  output: [{ success: true, researched: 0 }]
});""")

out.append(f"""
const claimNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Atomic Claim (F33)',
    position: [1020, 400],
    parameters: {{
      operation: 'executeQuery',
      query: {J(CLAIM_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.run_id, $json.company_id ] }}}}') }}
    }}
  }},
  output: [{{ claimed_company_id: 'uuid' }}]
}});""")
out.append(f"""
const claimFilterNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Filter Claimed (F33)',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(FILTER_JS)} }},
    position: [1160, 400]
  }},
  output: [{{ company_id: 'uuid', _claim_none: false }}]
}});""")
out.append("""
const claimedAny = ifElse({
  version: 2.2,
  config: {
    name: 'Claimed Any?',
    position: [1300, 400],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ !$json._claim_none }}'), operator: { type: 'boolean', operation: 'true' } }],
        combinator: 'and'
      }
    }
  }
});""")

mcp_params = {
    'serverTransport': 'httpStreamable',
    'endpointUrl': 'https://mcp.tavily.com/mcp/',
    'authentication': 'mcpOAuth2Api',
    'tool': { '__rl': True, 'mode': 'list', 'value': 'tavily_search', 'cachedResultName': 'tavily_search' },
    'inputMode': 'json',
    'options': { 'timeout': 120000, 'convertToBinary': False }
}
out.append(f"""
const mcpNode = node({{
  type: '@n8n/n8n-nodes-langchain.mcpClient',
  version: 1.1,
  config: {{
    name: 'Tavily MCP - Search',
    position: [880, 400],
    parameters: {{ {', '.join(f'{k}: {J(v)}' for k, v in mcp_params.items())}, jsonInput: expr('{{{{ $json.mcp_input }}}}') }}
  }},
  output: [{{}}]
}});""")
out.append(f"""
const packNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Pack Evidence',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(PACK_JS)} }},
    position: [1160, 400]
  }},
  output: [{{ company_id: 'uuid', corpus: '', research_payload: {{}} }}]
}});""")
def http_node(var, name, pos, payload_field, sample):
    return f"""
const {var} = node({{
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {{
    name: {J(name)},
    position: [{pos}, 400],
    parameters: {{
      method: 'POST',
      url: 'https://api.meta.ai/v1/chat/completions',
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendBody: true,
      contentType: 'json',
      specifyBody: 'json',
      jsonBody: expr('{{{{ JSON.stringify($json.{payload_field}) }}}}'),
      options: {{ timeout: 120000 }}
    }}
  }},
  output: [{{ choices: [{{ message: {{ content: '{sample}' }} }}] }}]
}});"""
out.append(http_node('researchNode', 'LLM - Researcher', 1440, 'research_payload', '{}'))
out.append(f"""
const parseNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Parse Extract',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(PARSE_JS)} }},
    position: [1720, 400]
  }},
  output: [{{ company_id: 'uuid', facts: [], critic_payload: {{}} }}]
}});""")
out.append(f"""
const gateNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Verify Gate (F24)',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(GATE_JS)} }},
    position: [2000, 400]
  }},
  output: [{{ company_id: 'uuid', facts: [], gate_failures: [], critic_payload: {{}} }}]
}});""")
out.append(http_node('criticNode', 'LLM - Critic', 2280, 'critic_payload', '{"verdicts": []}'))
out.append(f"""
const savePayloadNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Build Save Payload',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(SAVE_JS)} }},
    position: [2280, 400]
  }},
  output: [{{ payload: '{{}}', facts_kept: 0, facts_dropped: 0 }}]
}});""")
out.append(f"""
const saveNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Save Research',
    position: [2560, 400],
    parameters: {{
      operation: 'executeQuery',
      query: {J(SAVE_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.payload ] }}}}') }}
    }}
  }},
  output: [{{ facts_saved: 0, signals_saved: 0, people_saved: 0 }}]
}});""")
out.append(f"""
const retNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Return',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(RET_JS)} }},
    position: [2840, 400]
  }},
  output: [{{ success: true, researched: 0 }}]
}});""")
ENDCHECK_JS_D4 = r"""
const summary = ($input.first() && $input.first().json) || {};
const chk = ($('Audit Write Check (D4)').first() || {}).json || {};
const failed = !!chk.audit_failed;
return [{ json: Object.assign({}, summary, { audit_failed: failed, sendTo: 'owner@example.com', subject: chk.subject || '', body: chk.body || '' }) }];
""".strip()
out.append(f"""
const endCheck = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Audit Alert Gate (D4)',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(ENDCHECK_JS_D4)} }},
    position: [2960, 400]
  }},
  output: [{{ audit_failed: false }}]
}});""")
out.append("""
const endIf = ifElse({
  version: 2.2,
  config: {
    name: 'Audit Failed? (end)',
    position: [3080, 400],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ $json.audit_failed }}'), operator: { type: 'boolean', operation: 'true' } }],
        combinator: 'and'
      }
    }
  }
});""")
out.append("""
const endPass = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Audit OK Pass (end)',
    parameters: { mode: 'runOnceForAllItems', jsCode: "return $input.all();" },
    position: [3200, 460]
  },
  output: [{ audit_failed: false }]
});""")
out.append("""
const finalReturn = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Return - Final (D4)',
    parameters: { mode: 'runOnceForAllItems', jsCode: "const s = ($('Return').first() || {}).json || {}; return [{ json: s }];" },
    position: [3340, 400]
  },
  output: [{ success: true, researched: 0 }]
});""")
out.append("""
export default workflow('leadfinder-sf5-vnext5', 'SF5 v-next.5 - Research + Critic + Cap + Audit + Claim + Isolation (F24+F28+F33+F34+D4)')
  .add(aboutNote)
  .add(subTrigger)
  .to(pickNode)
  .to(rankNode)
  .to(auditNode)
  .to(auditCheck)
  .to(jobsNode)
  .to(capCheckNode)
  .to(capGateNode)
  .to(capIf
    .onTrue(hasJobs
    .onTrue(claimNode.to(claimFilterNode).to(claimedAny
    .onTrue(mcpNode.to(packNode).to(researchNode).to(parseNode).to(gateNode).to(criticNode).to(savePayloadNode).to(saveNode).to(retNode).to(endCheck).to(endIf.onTrue(alertDraft.to(finalReturn)).onFalse(endPass.to(finalReturn))))
    .onFalse(emptyReturn)))
    .onFalse(emptyReturn)
    .onFalse(capInsertNode)
  ));""")
code = '\n'.join(out) + '\n'
(BASE/'sf5vnext5f.ts').write_text(code)
json.dump({"code": code}, open(BASE/'validate-sf5vnext5f.json','w'))
json.dump({"code": code, "name": "SF5 v-next.5 - Research + Critic + Cap + Audit + Claim + Isolation (F24+F28+F33+F34+D4)"}, open(BASE/'create-sf5vnext5f.json','w'))
print('sf5 generated', len(code))
