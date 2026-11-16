import json

TRIGGER = r"""
const t = $input.first().json;
return [{ json: { search_profile_id: t.search_profile_id, profile_version: t.profile_version || 1, run_id: t.run_id || '' } }];
""".strip()

LOAD_SQL = """
SELECT
 (SELECT rubric FROM search_profiles WHERE id = $1::uuid AND version = $2) AS rubric,
 (SELECT profile FROM search_profiles WHERE id = $1::uuid AND version = $2) AS profile,
 (SELECT count(*) FROM companies WHERE search_profile_id = $1::uuid) AS total_companies,
 (SELECT count(*) FROM scores WHERE search_profile_id = $1::uuid AND profile_version = $2) AS already_scored,
 COALESCE((SELECT jsonb_agg(c) FROM (
   SELECT co.id, co.name, co.domain, co.place_id, co.category, co.location, co.website, co.phone, co.rating, co.review_count, co.source, co.status,
     COALESCE((SELECT jsonb_agg(jsonb_build_object('signal_type', s.signal_type, 'detail', s.detail, 'evidence_url', s.evidence_url, 'signal_date', s.signal_date, 'observed_at', s.observed_at, 'decay_days', s.decay_days)) FROM signals s WHERE s.company_id = co.id), '[]'::jsonb) AS signals
   FROM companies co
   WHERE co.search_profile_id = $1::uuid AND co.status = 'new'
     AND NOT EXISTS (SELECT 1 FROM scores sc WHERE sc.company_id = co.id AND sc.search_profile_id = $1::uuid AND sc.profile_version = $2)
 ) c), '[]'::jsonb) AS companies
""".strip()

DET = r"""
const trig = $('When Executed by Another Workflow').item.json;
const row = $input.first().json;
const rubric = row.rubric || {};
const profile = row.profile || {};
const criteria = rubric.fit_criteria || [];
const triggers = rubric.timing_triggers || [];
const locTargets = [];
for (const s of (profile.sources || [])) for (const l of (s.locations || [])) locTargets.push(String(l).toLowerCase());
function classifyCriterion(crit, locTargets) {
  const name = (crit.name || '').toLowerCase();
  const verify = (crit.how_to_verify || '').toLowerCase();
  const both = name + ' ' + verify;
  if (name.includes('research-only')) return 'needs_research';
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
function coverageOf(fitCriteria, locTargets) {
  let det = 0, res = 0, contact = 0; const families = {};
  for (const c of (fitCriteria || [])) {
    const f = classifyCriterion(c, locTargets || []);
    families[c.name] = f;
    const pts = Number(c.max_points) || 0;
    if (f === 'needs_research') res += pts; else det += pts;
    if (f === 'website' || f === 'phone_contact') contact += pts;
  }
  return { deterministic_points: det, research_points: res, contact_points: contact, families };
}
const SIG2TRIG = { hiring: ['hiring','job'], expansion: ['expansion','growth','new office'], job_change: ['partner','leadership','job change','new hire'], funding: ['funding','raised','investment'], new_post: ['post'], review_activity: ['review','complaint','reply'] };
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
function detScore(crit, co) {
  const name = (crit.name || '').toLowerCase();
  const verify = (crit.how_to_verify || '').toLowerCase();
  const both = name + ' ' + verify;
  const max = crit.max_points || 0;
  const loc = (co.location || '').toLowerCase();
  if (name.includes('research-only')) return { awarded: 0, basis: 'needs_research' };
  if (/city|location|geograph|footprint|area|region/.test(name)) {
    if (loc && locTargets.some(t => loc.includes(t) || t.includes(loc))) return { awarded: max, basis: 'location_match' };
    return { awarded: 0, basis: 'location_no_match' };
  }
  if (/category|property type|business type|firm type/.test(name)) {
    const parsed = categoryTerms(crit.how_to_verify);
    if (!parsed || !parsed.include.length) return { awarded: 0, basis: 'needs_research' };
    const terms = parsed.include;
    const hay = ((co.category || '') + ' ' + (co.name || '')).toLowerCase();
    return terms.some(t => hay.includes(t)) ? { awarded: max, basis: 'category_match' } : { awarded: 0, basis: 'category_no_match' };
  }
  if (/facebook/.test(name)) {
    if (co.website && co.website.toLowerCase().includes('facebook.com')) return { awarded: Math.ceil(max / 2), basis: 'facebook_page_listed_partial' };
    return { awarded: 0, basis: 'no_facebook_evidence' };
  }
  if (/rating/.test(name)) {
    const r = parseFloat(co.rating);
    if (!isNaN(r) && r >= 4.0) return { awarded: max, basis: 'rating_threshold' };
    if (!isNaN(r) && r >= 3.5) return { awarded: Math.ceil(max / 2), basis: 'rating_threshold_partial' };
    return { awarded: 0, basis: 'rating_below_or_missing' };
  }
  if (/review/.test(name) && /count|volume|number/.test(both)) {
    const n = co.review_count || 0;
    if (n >= 50) return { awarded: max, basis: 'review_volume' };
    if (n >= 10) return { awarded: Math.ceil(max / 2), basis: 'review_volume_partial' };
    return { awarded: 0, basis: 'review_volume_low' };
  }
  if (/website/.test(name)) {
    return co.website ? { awarded: max, basis: 'has_website' } : { awarded: 0, basis: 'no_website' };
  }
  if (/phone|contact/.test(name)) {
    return co.phone ? { awarded: max, basis: 'has_phone' } : { awarded: 0, basis: 'no_phone' };
  }
  return { awarded: 0, basis: 'needs_research' };
}
function timingScore(co) {
  let total = 0; const comps = [];
  for (const sig of (co.signals || [])) {
    const keys = SIG2TRIG[sig.signal_type] || [];
    const trig = triggers.find(t => keys.some(k => ((t.name || '') + ' ' + (t.signal || '')).toLowerCase().includes(k)));
    if (!trig) { comps.push({ signal_type: sig.signal_type, awarded: 0, basis: 'no_matching_trigger' }); continue; }
    const when = sig.signal_date ? new Date(sig.signal_date) : new Date(sig.observed_at);
    const ageDays = Math.max(0, Math.floor((Date.now() - when.getTime()) / 86400000));
    const decay = trig.decay_days || sig.decay_days || 14;
    const pts = Math.round((trig.max_points || 0) * Math.max(0, 1 - ageDays / decay));
    total += pts;
    comps.push({ trigger: trig.name, signal_type: sig.signal_type, age_days: ageDays, awarded: pts });
  }
  return { total, comps };
}
if (!row.companies || row.companies.length === 0) {
  return [{ json: { empty_run: true, search_profile_id: trig.search_profile_id, profile_version: trig.profile_version || 1, already_scored: row.already_scored || 0, total_companies: row.total_companies || 0, det_points: 0, fit_components: [], timing_score: 0, timing_components: [], insufficient_data: false, llm_max: rubric.llm_judgement_max || 30, max_achievable: coverageOf(criteria, locTargets).deterministic_points + (rubric.llm_judgement_max || 30), company: {}, criteria_names: [] } }];
}
const out = [];
for (const co of (row.companies || [])) {
  const comps = []; let det = 0;
  for (const crit of criteria) { const r = detScore(crit, co); det += r.awarded; comps.push({ criterion: crit.name, max: crit.max_points, awarded: r.awarded, basis: r.basis }); }
  const ts = timingScore(co);
  const insufficient = !co.website && (co.rating === null || co.rating === undefined) && !co.review_count && !co.category;
  out.push({ json: {
    company_id: co.id, name: co.name, search_profile_id: trig.search_profile_id, profile_version: trig.profile_version || 1,
    det_points: det, fit_components: comps, timing_score: ts.total, timing_components: ts.comps,
    insufficient_data: insufficient, llm_max: rubric.llm_judgement_max || 30, max_achievable: coverageOf(criteria, locTargets).deterministic_points + (rubric.llm_judgement_max || 30),
    total_companies: row.total_companies || 0, already_scored: row.already_scored || 0,
    company: { name: co.name, category: co.category, location: co.location, website: co.website, phone: co.phone, rating: co.rating, review_count: co.review_count, source: co.source },
    criteria_names: criteria.map(c => ({ name: c.name, max_points: c.max_points, how_to_verify: c.how_to_verify }))
  }});
}
return out;
""".strip()

PROMPT = r"""
const j = $json;
const sys = 'You are the bounded fit judge in a lead-scoring system. Score ONLY from the evidence given. Return strict JSON only: {"points": <int 0..LLM_MAX>, "rationale": "<short, evidence-based>", "disqualifiers": ["..."], "insufficient_data": <bool>}. If insufficient_data is true in the input, points MUST be 0 and insufficient_data MUST be true. Never invent facts (no emails, no people, no numbers not in the evidence).'.replace('LLM_MAX', String(j.llm_max));
const user = JSON.stringify({ company: j.company, deterministic_components: j.fit_components, deterministic_points: j.det_points, insufficient_data: j.insufficient_data, rubric_criteria: j.criteria_names }, null, 1);
return { ...j, llm_payload: { model: 'muse-spark-1.3', temperature: 0.1, messages: [ { role: 'system', content: sys }, { role: 'user', content: user } ] } };
""".strip()

PARSE = r"""
const detItems = $('Deterministic Score').all();
const llmItems = $input.all();
if (detItems.length !== llmItems.length) throw new Error('SF7: item count mismatch between deterministic and LLM stages');
const out = [];
for (let i = 0; i < detItems.length; i++) {
  const d = detItems[i].json;
  let judged = { points: 0, rationale: 'LLM output unparseable', disqualifiers: [], insufficient_data: d.insufficient_data };
  try {
    const content = llmItems[i].json.choices[0].message.content;
    const parsed = JSON.parse(content.slice(content.indexOf('{'), content.lastIndexOf('}') + 1));
    judged = { points: Math.max(0, Math.min(d.llm_max, Math.round(parsed.points || 0))), rationale: String(parsed.rationale || ''), disqualifiers: Array.isArray(parsed.disqualifiers) ? parsed.disqualifiers : [], insufficient_data: !!parsed.insufficient_data };
  } catch (e) { /* keep defaults: fail-closed at 0 judgement points */ }
  if (d.insufficient_data) { judged.points = 0; judged.insufficient_data = true; }
  const fit = d.det_points + judged.points;
  const DESIGN_MAX = 100;
  const maxA = (typeof d.max_achievable === 'number') ? d.max_achievable : DESIGN_MAX;
  const tA = maxA < DESIGN_MAX ? Math.ceil(75 * maxA / DESIGN_MAX) : 75;
  const tB = maxA < DESIGN_MAX ? Math.ceil(55 * maxA / DESIGN_MAX) : 55;
  const tC = maxA < DESIGN_MAX ? Math.ceil(36 * maxA / DESIGN_MAX) : 36;
  const band = judged.insufficient_data ? 'insufficient_data' : (fit >= tA ? 'A' : fit >= tB ? 'B' : fit >= tC ? 'C' : 'not_a_fit');
  out.push({ json: { company_id: d.company_id, name: d.name, search_profile_id: d.search_profile_id, profile_version: d.profile_version, fit_score: fit, fit_components: d.fit_components, llm_judgement: judged.points, llm_rationale: judged.rationale, disqualifiers: judged.disqualifiers, timing_score: d.timing_score, timing_components: d.timing_components, band, max_achievable: maxA, thresholds: { A: tA, B: tB, C: tC }, total_companies: d.total_companies, already_scored: d.already_scored } });
}
return out;
""".strip()

COLLECT = r"""
const items = $input.all().map(i => i.json);
const first = items[0] || {};
const rows = items.map(j => ({ company_id: j.company_id, fit_score: j.fit_score, fit_components: j.fit_components, llm_judgement: j.llm_judgement, llm_rationale: j.llm_rationale, disqualifiers: j.disqualifiers, timing_score: j.timing_score, timing_components: j.timing_components, band: j.band }));
return [{ json: { payload: JSON.stringify(rows), search_profile_id: first.search_profile_id || $('When Executed by Another Workflow').item.json.search_profile_id, profile_version: first.profile_version || 1, loaded: items.length, already_scored: first.already_scored || 0, total_companies: first.total_companies || 0 } }];
""".strip()

PERSIST_SQL = """
WITH ins AS (
  INSERT INTO scores (company_id, search_profile_id, profile_version, fit_score, fit_components, llm_judgement, llm_rationale, disqualifiers, timing_score, timing_components, band)
  SELECT (r->>'company_id')::uuid, $2::uuid, $3, (r->>'fit_score')::int, r->'fit_components', (r->>'llm_judgement')::int, r->>'llm_rationale', COALESCE(r->'disqualifiers', '[]'::jsonb), (r->>'timing_score')::int, r->'timing_components', r->>'band'
  FROM jsonb_array_elements($1::jsonb) AS r
  WHERE NOT EXISTS (SELECT 1 FROM scores s WHERE s.company_id = (r->>'company_id')::uuid AND s.search_profile_id = $2::uuid AND s.profile_version = $3)
  RETURNING company_id, fit_score, band
), upd AS (
  UPDATE companies c SET status = 'scored' FROM ins WHERE c.id = ins.company_id RETURNING c.id
)
SELECT (SELECT count(*) FROM ins) AS inserted,
       COALESCE((SELECT jsonb_agg(jsonb_build_object('company_id', company_id, 'fit_score', fit_score, 'band', band)) FROM ins), '[]'::jsonb) AS results
""".strip()

SUMMARY = r"""
const p = $input.first().json;
const c = $('Collect Rows').item.json;
return [{ json: { success: true, scored: p.inserted || 0, loaded_unscored: c.loaded, skipped_already_scored: c.already_scored, total_companies: c.total_companies, results: p.results || [] } }];
""".strip()

code = f'''import {{ workflow, node, links, trigger, ifElse, expr }} from '@n8n/workflow-sdk';

const trigNode = trigger({{
  type: 'n8n-nodes-base.executeWorkflowTrigger',
  version: 1.1,
  config: {{
    name: 'When Executed by Another Workflow',
    position: [240, 400],
    parameters: {{
      inputSource: 'workflowInputs',
      workflowInputs: {{
        values: [
          {{ name: 'search_profile_id', type: 'string' }},
          {{ name: 'profile_version', type: 'number' }},
          {{ name: 'run_id', type: 'string' }}
        ]
      }}
    }}
  }},
  output: [{{ search_profile_id: 'profile-uuid', profile_version: 1, run_id: '' }}]
}});

const loadNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Load Profile + Companies',
    position: [480, 400],
    parameters: {{
      operation: 'executeQuery',
      query: {json.dumps(LOAD_SQL)},
      options: {{ queryReplacement: expr("{{{{ [ $('When Executed by Another Workflow').item.json.search_profile_id, $('When Executed by Another Workflow').item.json.profile_version || 1 ] }}}}") }}
    }}
  }},
  output: [{{ rubric: {{}}, profile: {{}}, companies: [], total_companies: 0, already_scored: 0 }}]
}});

const detNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Deterministic Score',
    position: [720, 400],
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {json.dumps(DET)} }}
  }},
  output: [{{ company_id: 'uuid', det_points: 0, fit_components: [], timing_score: 0 }}]
}});


const hasCompanies = ifElse({{
  version: 2.2,
  config: {{
    name: 'Has Companies?',
    position: [840, 400],
    parameters: {{
      conditions: {{
        options: {{ caseSensitive: true, typeValidation: 'loose' }},
        conditions: [{{ leftValue: expr('{{{{ !$json.empty_run }}}}'), operator: {{ type: 'boolean', operation: 'true' }} }}],
        combinator: 'and'
      }}
    }}
  }}
}});

const emptyReturn = node({{
  type: 'n8n-nodes-base.set',
  version: 3.4,
  config: {{
    name: 'Return - Empty Run Summary',
    position: [960, 560],
    parameters: {{
      mode: 'manual',
      includeOtherFields: false,
      assignments: {{ assignments: [
        {{ id: 'a1', name: 'success', value: true, type: 'boolean' }},
        {{ id: 'a2', name: 'scored', value: 0, type: 'number' }},
        {{ id: 'a3', name: 'loaded_unscored', value: 0, type: 'number' }},
        {{ id: 'a4', name: 'skipped_already_scored', value: expr('{{{{ $json.already_scored }}}}'), type: 'number' }},
        {{ id: 'a5', name: 'total_companies', value: expr('{{{{ $json.total_companies }}}}'), type: 'number' }},
        {{ id: 'a6', name: 'results', value: [], type: 'array' }}
      ] }}
    }}
  }},
  output: [{{ success: true, scored: 0, loaded_unscored: 0, skipped_already_scored: 0, total_companies: 0, results: [] }}]
}});

const promptNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Build LLM Prompt',
    position: [960, 400],
    parameters: {{ mode: 'runOnceForEachItem', jsCode: {json.dumps(PROMPT)} }}
  }},
  output: [{{ llm_payload: {{}} }}]
}});

const llmNode = node({{
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {{
    name: 'LLM - Judge Fit',
    position: [1200, 400],
    parameters: {{
      method: 'POST',
      url: 'https://api.meta.ai/v1/chat/completions',
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendBody: true,
      contentType: 'json',
      specifyBody: 'json',
      jsonBody: expr('{{{{ JSON.stringify($json.llm_payload) }}}}'),
      options: {{ timeout: 120000 }}
    }}
  }},
  output: [{{ choices: [{{ message: {{ content: '{{"points": 0}}' }} }}] }}]
}});

const parseNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Parse + Assemble',
    position: [1440, 400],
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {json.dumps(PARSE)} }}
  }},
  output: [{{ company_id: 'uuid', fit_score: 0, band: 'C' }}]
}});

const collectNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Collect Rows',
    position: [1680, 400],
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {json.dumps(COLLECT)} }}
  }},
  output: [{{ payload: '[]', loaded: 0 }}]
}});

const persistNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Persist Scores',
    position: [1920, 400],
    parameters: {{
      operation: 'executeQuery',
      query: {json.dumps(PERSIST_SQL)},
      options: {{ queryReplacement: expr("{{{{ [ $json.payload, $json.search_profile_id, $json.profile_version ] }}}}") }}
    }}
  }},
  output: [{{ inserted: 0, results: [] }}]
}});

const summaryNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Summarize + Return',
    position: [2160, 400],
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {json.dumps(SUMMARY)} }}
  }},
  output: [{{ success: true, scored: 0 }}]
}});

export default workflow('sf7-scoring-vnext', 'SF7 v-next - Scoring (F22)')
  .add(trigNode)
  .to(loadNode)
  .to(detNode)
  .to(hasCompanies
    .onTrue(promptNode.to(llmNode).to(parseNode).to(collectNode).to(persistNode).to(summaryNode))
    .onFalse(emptyReturn)
  );
'''
open('sf7-vnext.ts', 'w').write(code)
print('sf7.ts written', len(code))
