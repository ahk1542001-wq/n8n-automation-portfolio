import json, pathlib
BASE = pathlib.Path(__file__).resolve().parent
BASE.mkdir(parents=True, exist_ok=True)
def J(s): return json.dumps(s)

EXTRACT_SYS = (
"You are a people finder for B2B sales research. You receive a company and raw web evidence. "
"Find the people who own, founded, lead or work at THIS company. Return ONLY a JSON object: "
"{\"people\": [{\"full_name\": string, \"title\": string, \"linkedin_url\": string, \"is_decision_maker\": boolean, \"evidence_url\": string, \"evidence_quote\": string}]}. "
"Every person MUST have an evidence_url copied from the evidence and a short EXACT quote copied from the evidence that names the person together with this company or their role in it. "
"A LinkedIn URL may only be included if it appears in the evidence. Never invent names, titles or URLs. "
"If no person can be tied to this company by the evidence, return an empty list."
)

BUILD_JOBS_JS = r"""
const trig = $('When Executed by Another Workflow').item.json;
const picks = ($input.first().json.picks || []);
if (!picks.length) {
  return [{ json: { empty_run: true, stage: 'SF3', reason: 'no_companies_met_fit_threshold', fit_threshold: trig.min_fit || 30, search_profile_id: trig.search_profile_id || '', profile_version: trig.profile_version || 1, run_id: trig.run_id || '' } }];
}
return picks.map(c => {
  const loc = (c.location || '').trim();
  const qLinkedin = (c.name + ' ' + loc + ' LinkedIn owner founder').trim();
  let domain = '';
  try { domain = (c.website || '').replace(/^https?:\/\//, '').replace(/^www\./, '').split('/')[0]; } catch (e) { domain = ''; }
  const realDomain = domain && domain.indexOf('facebook.com') === -1 && domain.indexOf('.') > -1;
  const qWeb = realDomain ? (c.name + ' ' + domain + ' team about owner founder').trim() : (c.name + ' ' + loc + ' about team owner founder').trim();
  return { json: { company_id: c.company_id, name: c.name, category: c.category || '', location: loc, website: c.website || '', run_id: trig.run_id || '',
    mcp_linkedin: JSON.stringify({ query: qLinkedin, search_depth: 'basic', max_results: 5 }),
    mcp_web: JSON.stringify({ query: qWeb, search_depth: 'basic', max_results: 5 }) } };
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

PACK_JS = r"""
const jobs = $('Build Jobs').all().map(i => i.json);
const first = $('Reattach').all().map(i => i.json);
return $input.all().map((item, idx) => {
  const job = jobs[idx] || {};
  let t2 = '';
  try { t2 = typeof item.json === 'string' ? item.json : JSON.stringify(item.json); } catch (e) { t2 = String(item.json); }
  let corpus = 'LINKEDIN SEARCH RESULTS:\n' + ((first[idx] || {}).search1_text || '') + '\n\nWEBSITE AND TEAM SEARCH RESULTS:\n' + t2;
  if (corpus.length > 9000) corpus = corpus.slice(0, 9000);
  const userMsg = 'Company: ' + job.name + '\nCategory: ' + job.category + '\nLocation: ' + job.location + '\nWebsite: ' + job.website + '\n\nWEB EVIDENCE:\n' + corpus;
  return { json: { company_id: job.company_id, run_id: job.run_id, name: job.name, corpus,
    extract_payload: { model: 'muse-spark-1.3', temperature: 0.1, messages: [ { role: 'system', content: EXTRACT_SYS }, { role: 'user', content: userMsg } ] } } };
});
""".strip().replace('EXTRACT_SYS', J(EXTRACT_SYS))

PARSE_JS = r"""
const packs = $('Pack Evidence').all().map(i => i.json);
const DM = /(owner|founder|co-founder|partner|director|ceo|managing|manager|president)/i;
function norm(s) { return String(s || '').toLowerCase().replace(/\s+/g, ' ').trim(); }
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
    people.push({ full_name: String(p.full_name), title, linkedin_url: li,
      is_decision_maker: (p.is_decision_maker === true) || DM.test(title),
      evidence_url: String(p.evidence_url), evidence_quote: String(p.evidence_quote) });
  }
  const payload = { company_id: pack.company_id, run_id: pack.run_id || '', corpus: (pack.corpus || '').slice(0, 4000), people };
  return { json: { payload: JSON.stringify(payload), company_id: pack.company_id, people_found: people.length } };
});
""".strip()

RET_JS = r"""
const saves = $input.all().map(i => i.json);
const packs = $('Parse + Validate').all().map(i => i.json);
return [{ json: { success: true, companies_processed: saves.length,
  people_extracted: packs.reduce((a, s) => a + (s.people_found || 0), 0),
  people_saved: saves.reduce((a, s) => a + (Number(s.people_saved) || 0), 0) } }];
""".strip()

PICK_SQL = """
SELECT COALESCE(jsonb_agg(p), '[]'::jsonb) AS picks
FROM (
  SELECT c.id::text AS company_id, c.name, c.category, c.location, c.website, s.fit_score
  FROM companies c
  JOIN scores s ON s.company_id = c.id AND s.search_profile_id = $1::uuid AND s.profile_version = $2
  WHERE s.fit_score >= $3 AND c.status NOT IN ('approved','rejected')
    AND NOT EXISTS (SELECT 1 FROM people pp WHERE pp.company_id = c.id)
    AND NOT EXISTS (SELECT 1 FROM research_artifacts ra WHERE ra.company_id = c.id AND ra.field_name = 'people_search_pack')
  ORDER BY s.fit_score DESC LIMIT $4
) p
""".strip()

SAVE_SQL = """
WITH p AS (SELECT $1::jsonb AS j),
pack AS (INSERT INTO research_artifacts (company_id, field_name, value, source_url, raw_content, critic_verdict)
  SELECT (j->>'company_id')::uuid, 'people_search_pack', jsonb_build_object('people_found', jsonb_array_length(j->'people')), NULL, j->>'corpus', 'deterministic_quote_check' FROM p RETURNING id),
pi AS (INSERT INTO people (company_id, full_name, title, linkedin_url, is_decision_maker, source, raw_payload)
  SELECT (j->>'company_id')::uuid, x->>'full_name', NULLIF(x->>'title',''), NULLIF(x->>'linkedin_url',''), COALESCE((x->>'is_decision_maker')::boolean, false), 'tavily_people_search', x
  FROM p, jsonb_array_elements(j->'people') x
  WHERE NOT EXISTS (SELECT 1 FROM people pp WHERE pp.company_id = (j->>'company_id')::uuid AND lower(pp.full_name) = lower(x->>'full_name'))
  RETURNING id),
sp AS (INSERT INTO spend_ledger (run_id, company_id, provider, action, credits)
  SELECT NULLIF(j->>'run_id','')::uuid, (j->>'company_id')::uuid, 'tavily', 'people_search', 2 FROM p RETURNING id)
SELECT (SELECT count(*) FROM pi) AS people_saved
""".strip()

out = []
out.append("import { workflow, node, trigger, sticky, expr, ifElse } from '@n8n/workflow-sdk';")
out.append(f"const aboutNote = sticky({J('SF3 - People Finder (Open). Apollo-free people discovery: for the highest-fit scored companies with no people yet and no prior people search, runs TWO Tavily searches per company (LinkedIn-flavoured, then website/team-flavoured via a Reattach node that carries the second query past the first MCP node), extracts people with an evidence-bound LLM, then applies a DETERMINISTIC quote check (each persons evidence_quote must appear verbatim in the search corpus or the person is dropped). Saves people idempotently, a people_search_pack audit artifact, and a 2-credit spend-ledger row per company. No emails are guessed; no outreach is created here.')}, [], {{ color: 5 }});")
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
        { name: 'min_fit', type: 'number' }
      ] }
    },
    position: [40, 400]
  },
  output: [{ search_profile_id: 'uuid', profile_version: 1, run_id: '', max_companies: 3, min_fit: 30 }]
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
      options: {{ queryReplacement: expr('{{{{ [ $json.search_profile_id, $json.profile_version || 1, $json.min_fit || 30, $json.max_companies || 3 ] }}}}') }}
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
  output: [{{ company_id: 'uuid', mcp_linkedin: '{{}}', mcp_web: '{{}}' }}]
}});""")
mcp_params = {
    'serverTransport': 'httpStreamable',
    'endpointUrl': 'https://mcp.tavily.com/mcp/',
    'authentication': 'mcpOAuth2Api',
    'tool': { '__rl': True, 'mode': 'list', 'value': 'tavily_search', 'cachedResultName': 'tavily_search' },
    'inputMode': 'json',
    'options': { 'timeout': 120000, 'convertToBinary': False }
}
def mcp_node(var, name, pos, field):
    return f"""
const {var} = node({{
  type: '@n8n/n8n-nodes-langchain.mcpClient',
  version: 1.1,
  config: {{
    name: {J(name)},
    position: [{pos}, 400],
    parameters: {{ {', '.join(f'{k}: {J(v)}' for k, v in mcp_params.items())}, jsonInput: expr('{{{{ $json.{field} }}}}') }}
  }},
  output: [{{}}]
}});"""

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
        { id: 'a2', name: 'companies_processed', value: 0, type: 'number' },
        { id: 'a3', name: 'people_extracted', value: 0, type: 'number' },
        { id: 'a4', name: 'people_saved', value: 0, type: 'number' }
      ] }
    }
  },
  output: [{ success: true, companies_processed: 0, people_saved: 0 }]
});""")
out.append(mcp_node('mcpSearch1', 'Tavily MCP - Search LinkedIn', 880, 'mcp_linkedin'))
out.append(f"""
const reattachNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Reattach',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(REATTACH_JS)} }},
    position: [1160, 400]
  }},
  output: [{{ company_id: 'uuid', search1_text: '', mcp_input: '{{}}' }}]
}});""")
out.append(mcp_node('mcpSearch2', 'Tavily MCP - Search Web', 1440, 'mcp_input'))
out.append(f"""
const packNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Pack Evidence',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(PACK_JS)} }},
    position: [1720, 400]
  }},
  output: [{{ company_id: 'uuid', corpus: '', extract_payload: {{}} }}]
}});""")
out.append(f"""
const extractNode = node({{
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {{
    name: 'LLM - People Extractor',
    position: [2000, 400],
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
    position: [2280, 400]
  }},
  output: [{{ payload: '{{}}', people_found: 0 }}]
}});""")
out.append(f"""
const saveNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Save People',
    position: [2560, 400],
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
    position: [2840, 400]
  }},
  output: [{{ success: true, companies_processed: 0, people_saved: 0 }}]
}});""")
out.append("""
export default workflow('leadfinder-sf3-v3', 'SF3 - People Finder (Open) v3')
  .add(aboutNote)
  .add(subTrigger)
  .to(pickNode)
  .to(jobsNode)
  .to(hasJobs
    .onTrue(mcpSearch1
  .to(reattachNode)
  .to(mcpSearch2)
  .to(packNode)
  .to(extractNode)
  .to(parseNode)
  .to(saveNode)
  .to(retNode))
    .onFalse(emptyReturn)
  );""")
code = '\n'.join(out) + '\n'
(BASE/'sf3v3.ts').write_text(code)
json.dump({"code": code}, open(BASE/'validate-sf3v3.json','w'))
json.dump({"code": code, "name": "SF3 - People Finder (Open) v3"}, open(BASE/'create-sf3v3.json','w'))
print('sf3 generated', len(code))
