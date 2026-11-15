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
return $input.all().map(i => {
  const c = i.json;
  const q = (c.name + ' ' + (c.category || '') + ' ' + (c.location || '')).trim();
  return { json: { company_id: c.company_id, name: c.name, category: c.category || '', location: c.location || '', website: c.website || '', run_id: trig.run_id || '', mcp_input: JSON.stringify({ query: q, search_depth: 'basic', max_results: 5 }) } };
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

SAVE_JS = r"""
const extracts = $('Parse Extract').all().map(i => i.json);
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
  const payload = { company_id: ex.company_id, run_id: ex.run_id || '', summary: ex.summary || '', corpus: (ex.corpus || '').slice(0, 4000), facts, signals: ex.signals || [], people: ex.people || [] };
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
SELECT c.id::text AS company_id, c.name, c.category, c.location, c.website, s.fit_score
FROM companies c
JOIN scores s ON s.company_id = c.id AND s.search_profile_id = $1::uuid AND s.profile_version = $2
WHERE s.fit_score >= $3 AND c.status NOT IN ('approved','rejected')
  AND NOT EXISTS (SELECT 1 FROM research_artifacts ra WHERE ra.company_id = c.id)
ORDER BY s.fit_score DESC LIMIT $4
""".strip()

SAVE_SQL = """
WITH p AS (SELECT $1::jsonb AS j),
pack AS (INSERT INTO research_artifacts (company_id, field_name, value, source_url, raw_content, critic_verdict)
  SELECT (j->>'company_id')::uuid, 'research_pack', jsonb_build_object('summary', j->>'summary'), NULL, j->>'corpus', 'unchecked' FROM p RETURNING id),
fi AS (INSERT INTO research_artifacts (company_id, field_name, value, source_url, critic_verdict)
  SELECT (j->>'company_id')::uuid, x->>'field', x, x->>'evidence_url', 'supported' FROM p, jsonb_array_elements(j->'facts') x RETURNING id),
si AS (INSERT INTO signals (company_id, signal_type, detail, evidence_url)
  SELECT (j->>'company_id')::uuid, COALESCE(x->>'signal_type','other'), x->>'detail', x->>'evidence_url' FROM p, jsonb_array_elements(j->'signals') x RETURNING id),
pi AS (INSERT INTO people (company_id, full_name, title, source, raw_payload)
  SELECT (j->>'company_id')::uuid, x->>'full_name', x->>'title', 'tavily_research', x FROM p, jsonb_array_elements(j->'people') x RETURNING id),
sp AS (INSERT INTO spend_ledger (run_id, company_id, provider, action, credits)
  SELECT NULLIF(j->>'run_id','')::uuid, (j->>'company_id')::uuid, 'tavily', 'research_call', 1 FROM p RETURNING id),
up AS (UPDATE companies SET status = 'researched' WHERE id = (SELECT (j->>'company_id')::uuid FROM p) RETURNING id)
SELECT (SELECT count(*) FROM fi) AS facts_saved, (SELECT count(*) FROM si) AS signals_saved, (SELECT count(*) FROM pi) AS people_saved
""".strip()

out = []
out.append("import { workflow, node, trigger, sticky, expr } from '@n8n/workflow-sdk';")
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
        { name: 'min_fit', type: 'number' }
      ] }
    },
    position: [40, 400]
  },
  output: [{ search_profile_id: 'uuid', profile_version: 1, run_id: '', max_research: 3, min_fit: 36 }]
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
      options: {{ queryReplacement: expr('{{{{ [ $json.search_profile_id, $json.profile_version || 1, $json.min_fit || 36, $json.max_research || 3 ] }}}}') }}
    }}
  }},
  output: [{{ company_id: 'uuid', name: 'Shop', fit_score: 50 }}]
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
out.append(http_node('criticNode', 'LLM - Critic', 2000, 'critic_payload', '{"verdicts": []}'))
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
out.append("""
export default workflow('leadfinder-sf5', 'SF5 - Research + Critic (Tavily)')
  .add(aboutNote)
  .add(subTrigger)
  .to(pickNode)
  .to(jobsNode)
  .to(mcpNode)
  .to(packNode)
  .to(researchNode)
  .to(parseNode)
  .to(criticNode)
  .to(savePayloadNode)
  .to(saveNode)
  .to(retNode);""")
code = '\n'.join(out) + '\n'
(BASE/'sf5.ts').write_text(code)
json.dump({"code": code}, open(BASE/'validate-sf5.json','w'))
json.dump({"code": code, "name": "SF5 - Research + Critic (Tavily)"}, open(BASE/'create-sf5.json','w'))
print('sf5 generated', len(code))
