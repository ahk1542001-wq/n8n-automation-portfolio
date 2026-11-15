import json

sql = open('sf4.sql').read()

NORM_JS = r"""const inp = $input.item.json || {};
function normName(s){ if(s===null||s===undefined) return ''; let t = String(s).toLowerCase().replace(/[^a-z0-9\u1000-\u109F ]+/g,' ').replace(/\s+/g,' ').trim(); t = t.replace(/\b(co ltd|company limited|limited|ltd|llc|inc|corp|company|pte|sdn bhd|gmbh)\b/g,' ').replace(/\s+/g,' ').trim(); return t; }
function normDomain(d, w){ let v = (d || w || ''); if(!v) return null; v = String(v).toLowerCase().trim().replace(/^https?:\/\//,'').replace(/^www\./,'').split('/')[0].split('?')[0].trim(); return v || null; }
const cands = (inp.candidates || []).map(c => ({
  source: c.source || 'manual',
  source_id: c.source_id || c.place_id || null,
  name: c.name || '',
  normalised_name: normName(c.name),
  domain: normDomain(c.domain, c.website),
  place_id: c.place_id || null,
  registration_no: c.registration_no || null,
  category: c.category || null,
  location: c.location || null,
  website: c.website || null,
  phone: c.phone || null,
  rating: (c.rating === undefined ? null : c.rating),
  review_count: (c.review_count === undefined ? null : c.review_count),
  raw: c.raw || c
}));
const payload = { search_profile_id: inp.search_profile_id || null, profile_version: inp.profile_version || 1, run_id: inp.run_id || null, candidates: cands };
return { json: { payload_json: JSON.stringify(payload), candidate_count: cands.length } };"""

SUM_JS = r"""const rows = $input.all().map(i => i.json);
const counts = { inserted: 0, duplicates: 0, suppressed: 0 };
for (const r of rows) { if (r.outcome === 'inserted') counts.inserted++; else if (r.outcome === 'suppressed') counts.suppressed++; else counts.duplicates++; }
return { json: { success: true, inserted: counts.inserted, duplicates: counts.duplicates, suppressed: counts.suppressed, results: rows } };"""

ts = """import { workflow, node, trigger, sticky, newCredential, expr } from '@n8n/workflow-sdk';

const aboutNote = sticky("SF4 - Dedupe + Exclusion. Input: { search_profile_id, profile_version, run_id, candidates[] } in the common raw-lead contract. Normalises names/domains, then ONE deterministic SQL statement checks the suppression ledger and existing companies (place_id, domain, name+location keys), inserts only genuinely new companies, and returns a per-candidate outcome: inserted | duplicate | suppressed. Dedupe runs BEFORE any paid enrichment spend.", [], { color: 5 });

const subTrigger = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger',
  version: 1.1,
  config: {
    name: 'When Executed by Another Workflow',
    parameters: {
      workflowInputs: { values: [ { name: 'search_profile_id', type: 'string' }, { name: 'profile_version', type: 'number' }, { name: 'run_id', type: 'string' }, { name: 'candidates', type: 'array' } ] }
    },
    position: [40, 400]
  },
  output: [{ search_profile_id: 'uuid', profile_version: 1, run_id: '', candidates: [] }]
});

const normalize = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Normalize + Build Payload',
    parameters: { mode: 'runOnceForAllItems', jsCode: NORMJS },
    position: [320, 400]
  },
  output: [{ payload_json: '{}', candidate_count: 0 }]
});

const dbDedupe = node({
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {
    name: 'DB - Dedupe + Insert',
    parameters: {
      operation: 'executeQuery',
      query: SQLSTR,
      options: { queryReplacement: expr('{{ [ $json.payload_json ] }}') }
    },
    credentials: { postgres: newCredential('Supabase Postgres') },
    position: [600, 400]
  },
  output: [{ name: 'Example', outcome: 'inserted', company_id: 'uuid' }]
});

const summarize = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Summarize + Return',
    parameters: { mode: 'runOnceForAllItems', jsCode: SUMJS },
    position: [880, 400]
  },
  output: [{ success: true, inserted: 0, duplicates: 0, suppressed: 0, results: [] }]
});

export default workflow('sf4-dedupe-exclusion', 'SF4 - Dedupe + Exclusion')
  .add(aboutNote)
  .add(subTrigger)
  .to(normalize)
  .to(dbDedupe)
  .to(summarize);
"""
ts = ts.replace('NORMJS', json.dumps(NORM_JS)).replace('SUMJS', json.dumps(SUM_JS)).replace('SQLSTR', json.dumps(sql))
open('sf4.ts', 'w').write(ts)
json.dump({"code": ts}, open('create-sf4.json', 'w'))
json.dump({"code": ts}, open('validate-sf4.json', 'w'))
print('generated', len(ts))
