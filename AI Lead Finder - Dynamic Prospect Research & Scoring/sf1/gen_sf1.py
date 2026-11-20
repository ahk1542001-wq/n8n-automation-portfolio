import json, pathlib

BASE = pathlib.Path(__file__).resolve().parent

def J(s):
    return json.dumps(s)

BUILD_PROMPT_JS = r"""
const ctx = $input.item.json.business_context || {};
const system = `You are SF1, the search-profile generator for a dynamic lead-finding system. From the business context you receive, produce a machine-executable search profile and a scoring rubric as ONE JSON object with exactly these keys:
{
  "target_summary": "one sentence: who exactly we are looking for",
  "lead_unit": "company | person | company_with_person",
  "sources": [{"source": "apify_maps | apollo | registry | tavily_research", "queries": ["..."], "locations": ["..."]}],
  "hard_filters": ["verifiable yes/no criteria; failing any one = excluded"],
  "exclusions": ["business types or situations to never return"],
  "decision_maker_titles": ["..."],
  "rubric": {
    "fit_criteria": [{"name": "...", "max_points": 0, "how_to_verify": "which public evidence proves this"}],
    "timing_triggers": [{"name": "...", "max_points": 0, "signal": "observable dated event", "decay_days": 14}],
    "llm_judgement_max": 30,
    "bands": {"A": 75, "B": 55, "C": 36}
  },
  "research_fields": ["fields a researcher must fill later, each provable with evidence or left null"],
  "outreach_angles": ["2-4 angles grounded only in verified fields"]
}
Rules:
- fit_criteria max_points MUST sum to exactly 70.
- Every fit criterion must be checkable from public evidence; how_to_verify must say how. A criterion that cannot be checked is not allowed.
- Sources must match the lead type: local / SMB targets get apify_maps first; B2B company targets get apollo and/or registry; tavily_research is research support only and must never be the only source.
- Copy the user's exclusions into "exclusions" verbatim - never drop or soften them.
- Never invent a price range, a location, or a customer fact that is not in the context.
- If the context is too vague to build verifiable criteria, return {"error": "insufficient_context", "missing": ["what is missing"]} instead of inventing a profile.
DETERMINISTIC SCORING CONTRACT: SF7 scores deterministically BEFORE any research, using only Google Maps fields (category, location, website, phone, rating, review_count, facebook.com in website URL). (1) One fact per criterion; split combined facts into separate criteria. (2) A criterion is deterministic only if its NAME contains a matcher keyword and how_to_verify states the exact check: location/city — "Maps location matches target location(s): <the same locations listed in sources>"; category / property type / business type / firm type — "Category/name matches any of: <comma-separated target terms>"; facebook — "Website URL contains facebook.com"; rating — "Maps rating >=4.0 full points, >=3.5 half"; review + count/volume/number — "Maps review_count >=50 full points, >=10 half"; website — "A website URL exists"; phone/contact — "A phone number exists". (3) Facts only research can establish (room count, employee size, ownership or chain affiliation, workload, reply behaviour, decision-maker) MUST end with "(research-only)" in the name and must not use matcher keywords. (4) At least 35 of 70 points deterministic; at most 35 research-only; website + phone/contact combined at most 10 points. (5) Never rename a research fact into a proxy: review_count is not a room or employee count, rating is not workload, category is not ownership. If a critical fact is research-only, keep it research-only and cut its points to fit rule (4).
Return ONLY the JSON object. No markdown fences, no commentary.`;
const user = 'Business context (JSON):\n' + JSON.stringify(ctx, null, 2);
return { json: {
  business_context: ctx,
  llm_payload: {
    model: 'muse-spark-1.3',
    temperature: 0.1,
    messages: [
      { role: 'system', content: system },
      { role: 'user', content: user }
    ]
  }
} };
""".strip()

VALIDATE_JS = r"""
const raw = $input.item.json.choices?.[0]?.message?.content ?? '';
const ctx = $('Build Prompt').first().json.business_context || {};
let p = null;
try { p = JSON.parse(String(raw).replace(/```json|```/g, '').trim()); } catch (e) { p = null; }
if (!p) return { json: { success: false, error: 'unparseable_llm_output' } };
if (p.error === 'insufficient_context') return { json: { success: false, error: 'insufficient_context', missing: p.missing || [] } };
const req = ['target_summary','lead_unit','sources','hard_filters','exclusions','decision_maker_titles','rubric','research_fields','outreach_angles'];
for (const k of req) { if (!(k in p)) return { json: { success: false, error: 'missing_key_' + k } }; }
const fit = (p.rubric && p.rubric.fit_criteria) || [];
const sum = fit.reduce((a, c) => a + (Number(c.max_points) || 0), 0);
if (sum !== 70) return { json: { success: false, error: 'fit_points_sum_' + sum } };
if (!Array.isArray(p.sources) || p.sources.length === 0) return { json: { success: false, error: 'no_sources' } };
function categoryTerms(howToVerify) {
  const m = (howToVerify || '').match(/matches any of:\s*(.+)/i);
  if (!m) return null;
  const text = m[1].toLowerCase();
  const clauses = text
    .split(/\s+but\s+|\s+however\s+/)
    .flatMap(part => part.split(/[,;]/))
    .map(s => s.trim())
    .filter(Boolean);
  const include = [], exclude = [];
  for (const clause of clauses) {
    const neg = clause.match(/\b(not|no|never|without|isn't|isnt)\b/);
    if (neg) {
      const after = clause.slice(neg.index + neg[0].length).slice(0, 40).trim().replace(/^(a|an|the)\s+/, '').trim();
      if (after) exclude.push(after);
    } else {
      include.push(clause);
    }
  }
  return { include, exclude };
}
const MATCHER_VERSION = 'synonyms_v1';
const MATCHER_SYNONYMS_V1 = {
  'operates in target cities': 'location',
  'local presence in target markets': 'location',
  'target markets': 'location',
  'operates in target markets': 'location'
};
const KNOWN_FAMILIES = ['location', 'category', 'facebook', 'rating', 'review_volume', 'website', 'phone_contact'];
function normPhrase(s) {
  return String(s || '').toLowerCase().replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
}
function synonymFamily(rawName) {
  const v = MATCHER_SYNONYMS_V1[normPhrase(rawName)];
  if (v === undefined) return null;
  return KNOWN_FAMILIES.includes(v) ? v : 'unknown';
}
function classifyCriterion(crit, locTargets) {
  const name = (crit.name || '').toLowerCase();
  const verify = (crit.how_to_verify || '').toLowerCase();
  const both = name + ' ' + verify;
  if (name.includes('research-only')) return 'needs_research';
  const syn = synonymFamily(crit.name);
  if (syn === 'location') {
    return (locTargets && locTargets.length) ? 'location' : 'needs_research';
  }
  if (syn && syn !== 'unknown') return syn;
  if (/city|location|geograph|footprint|area|region/.test(name)) {
    return (locTargets && locTargets.length) ? 'location' : 'needs_research';
  }
  if (/category|property type|business type|firm type/.test(name)) {
    const parsed = categoryTerms(crit.how_to_verify);
    if (!parsed) return 'needs_research';
    return parsed.include.length ? 'category' : 'needs_research';
  }
  if (/facebook/.test(name)) return 'facebook';
  if (/rating/.test(name)) return 'rating';
  if (/review/.test(name) && /count|volume|number/.test(both)) return 'review_volume';
  if (/website/.test(name)) return 'website';
  if (/phone|contact/.test(name)) return 'phone_contact';
  return 'needs_research';
}
const locTargets = [];
for (const s of (p.sources || [])) for (const L of (s.locations || [])) locTargets.push(String(L).toLowerCase());
let detPts = 0, resPts = 0, contactPts = 0; const families = {};
for (const c of fit) {
  const f = classifyCriterion(c, locTargets);
  families[c.name] = f;
  const pts = Number(c.max_points) || 0;
  if (f === 'needs_research') resPts += pts; else detPts += pts;
  if (f === 'website' || f === 'phone_contact') contactPts += pts;
}
const coverage = { deterministic_points: detPts, research_points: resPts, contact_points: contactPts, families };
const COVERAGE_BLOCKING = true;
if (COVERAGE_BLOCKING && (detPts < 35 || resPts > 35 || contactPts > 10)) return { json: { success: false, error: 'coverage_below_floor', coverage } };
const rubricOut = Object.assign({}, p.rubric, { coverage });
const profile = {
  target_summary: p.target_summary,
  lead_unit: p.lead_unit,
  sources: p.sources,
  hard_filters: p.hard_filters,
  exclusions: p.exclusions,
  decision_maker_titles: p.decision_maker_titles,
  research_fields: p.research_fields,
  outreach_angles: p.outreach_angles
};
return { json: {
  success: true,
  target_summary: p.target_summary,
  business_context_json: JSON.stringify(ctx),
  profile_json: JSON.stringify(profile),
  rubric_json: JSON.stringify(rubricOut),
  deterministic_points: detPts,
  research_points: resPts,
  contact_points: contactPts
} };
""".strip()

out = []
out.append("import { workflow, node, trigger, sticky, placeholder, newCredential, ifElse, switchCase, merge, splitInBatches, nextBatch, languageModel, memory, tool, outputParser, embedding, embeddings, vectorStore, retriever, documentLoader, textSplitter, reranker, fromAi, expr } from '@n8n/workflow-sdk';")
out.append("")
out.append(f"const aboutNote = sticky({J('SF1 - Search-Profile Generator. Input: business_context (object). Turns a free-form business context into a versioned search profile + scoring rubric (SF1-SPEC contract), validates it deterministically, and stores it in Supabase Postgres search_profiles as status=draft for human approval. Returns { success, search_profile_id, version, status, target_summary } or { success:false, error }. NO discovery runs here.')}, [], {{ color: 5 }});")
out.append("""
const subTrigger = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger',
  version: 1.1,
  config: {
    name: 'When Executed by Another Workflow',
    parameters: {
      workflowInputs: { values: [ { name: 'business_context', type: 'object' } ] }
    },
    position: [40, 400]
  },
  output: [{ business_context: { business_name: 'Example Co', what_they_sell: '...', customer_in_users_words: '...', locations: ['Bangkok'] } }]
});""")
out.append(f"""
const buildPrompt = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Build Prompt',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(BUILD_PROMPT_JS)} }},
    position: [320, 400]
  }},
  output: [{{ business_context: {{}}, llm_payload: {{ model: 'muse-spark-1.3', temperature: 0.1, messages: [] }} }}]
}});""")
out.append("""
const llmGen = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {
    name: 'LLM - Generate Profile',
    parameters: {
      method: 'POST',
      url: 'https://api.meta.ai/v1/chat/completions',
      sendHeaders: true,
      headerParameters: { parameters: [
        { name: 'Authorization', value: 'Bearer YOUR_LLM_API_KEY' },
        { name: 'Content-Type', value: 'application/json' }
      ] },
      sendBody: true,
      contentType: 'json',
      specifyBody: 'json',
      jsonBody: expr('{{ JSON.stringify($json.llm_payload) }}'),
      options: { timeout: 90000 }
    },
    position: [600, 400]
  },
  output: [{ choices: [{ message: { content: '{"target_summary":"..."}' } }] }]
});""")
out.append(f"""
const validateShape = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Validate + Shape',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(VALIDATE_JS)} }},
    position: [880, 400]
  }},
  output: [{{ success: true, target_summary: '...', business_context_json: '{{}}', profile_json: '{{}}', rubric_json: '{{}}' }}]
}});""")
out.append("""
const profileOk = ifElse({
  version: 2.2,
  config: {
    name: 'Profile OK?',
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ $json.success }}'), operator: { type: 'boolean', operation: 'true' } }],
        combinator: 'and'
      }
    },
    position: [1160, 400]
  }
});""")
out.append("""
const insertProfile = node({
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {
    name: 'DB - Insert Search Profile',
    parameters: {
      operation: 'executeQuery',
      query: "INSERT INTO search_profiles (business_context, profile, rubric, status) VALUES ($1::jsonb, $2::jsonb, $3::jsonb, 'draft') RETURNING id, version, status",
      options: { queryReplacement: expr('{{ [ $json.business_context_json, $json.profile_json, $json.rubric_json ] }}') }
    },
    credentials: { postgres: newCredential('Supabase Postgres') },
    position: [1440, 320]
  },
  output: [{ id: 'uuid', version: 1, status: 'draft' }]
});""")
out.append("""
const returnOk = node({
  type: 'n8n-nodes-base.set',
  version: 3.4,
  config: {
    name: 'Return',
    parameters: {
      mode: 'manual',
      includeOtherFields: false,
      assignments: { assignments: [
        { id: 'a1', name: 'success', value: true, type: 'boolean' },
        { id: 'a2', name: 'search_profile_id', value: expr('{{ $json.id }}'), type: 'string' },
        { id: 'a3', name: 'version', value: expr('{{ $json.version }}'), type: 'number' },
        { id: 'a4', name: 'status', value: expr('{{ $json.status }}'), type: 'string' },
        { id: 'a5', name: 'target_summary', value: expr("{{ $('Validate + Shape').first().json.target_summary }}"), type: 'string' }
      ] }
    },
    position: [1720, 320]
  },
  output: [{ success: true, search_profile_id: 'uuid', version: 1, status: 'draft', target_summary: '...' }]
});""")
out.append("""
const returnErr = node({
  type: 'n8n-nodes-base.set',
  version: 3.4,
  config: {
    name: 'Return Error',
    parameters: {
      mode: 'manual',
      includeOtherFields: false,
      assignments: { assignments: [
        { id: 'e1', name: 'success', value: false, type: 'boolean' },
        { id: 'e2', name: 'error', value: expr('{{ $json.error }}'), type: 'string' },
        { id: 'e3', name: 'missing', value: expr('{{ $json.missing }}'), type: 'array' }
      ] }
    },
    position: [1440, 520]
  },
  output: [{ success: false, error: 'insufficient_context', missing: [] }]
});""")
out.append("""
export default workflow('leadfinder-sf1', 'SF1 - Search-Profile Generator')
  .add(aboutNote)
  .add(subTrigger)
  .to(buildPrompt)
  .to(llmGen)
  .to(validateShape)
  .to(profileOk
    .onTrue(insertProfile.to(returnOk))
    .onFalse(returnErr)
  );""")

code = '\n'.join(out) + '\n'
(BASE/'sf1.ts').write_text(code)
# validate + create argument files
json.dump({"code": code}, open(BASE/'validate-sf1.json','w'))
json.dump({"code": code, "name": "SF1 - Search-Profile Generator"}, open(BASE/'create-sf1.json','w'))
print('written', len(code))
