import json, pathlib
BASE = pathlib.Path(__file__).resolve().parent
def J(s): return json.dumps(s)

# Reuse SF6b constants (SQL + token JS) from the sibling generator.
_ns = {'__file__': str(BASE / 'gen_sf6b_vnext2.py')}
_src = (BASE / 'gen_sf6b_vnext2.py').read_text()
exec(_src[:_src.find('# ---------- Generator')], _ns)
TOKEN_JS = _ns['TOKEN_JS']
SAVE_PERSON_SQL = _ns['SAVE_PERSON_SQL']
MARK_CHECKED_SQL = _ns['MARK_CHECKED_SQL']
FAIL_SQL = _ns['FAIL_SQL']

STAGE_JS = r"""
const t = $('When Executed by Another Workflow').first().json;
let batch = [];
let titles = [];
try { batch = JSON.parse(t.batch_json || '[]'); } catch (e) { batch = []; }
try { titles = JSON.parse(t.dm_titles_json || '[]'); } catch (e) { titles = []; }
return [{ json: {
  apify_run_id: t.apify_run_id || '',
  dataset_id: t.dataset_id || '',
  run_id: t.run_id || '',
  batch: Array.isArray(batch) ? batch : [],
  dm_titles: Array.isArray(titles) ? titles : [],
  profile_version: Number(t.profile_version || 1),
  mtd_apify_usd: Number(t.mtd_apify_usd || 0),
  picked_count: Number(t.picked_count || 0)
} }];
""".strip()

BUILD_RUN_URL_JS = r"""
const j = $input.first().json;
return [{ json: Object.assign({}, j, { run_url: 'https://api.apify.com/v2/actor-runs/' + j.apify_run_id, poll_started_at: Date.now() }) }];
""".strip()

POLL_JS = r"""
const stage = $('Stage Context').first().json;
if (!stage.apify_run_id) {
  return [{ json: { apify_run_id: '', dataset_id: '', status: 'NO_RUN', finished: true, succeeded: false, usage_usd: 0, run_id: stage.run_id, run_url: '' } }];
}
const j = $input.first().json || {};
const data = j.data || {};
const status = String(data.status || '');
const startedAt = data.startedAt ? Date.parse(data.startedAt) : 0;
let t0 = 0;
try { t0 = Number($('Build Run URL').first().json.poll_started_at || 0); } catch (e) {}
const elapsedMin = t0 ? (Date.now() - t0) / 60000 : (startedAt ? (Date.now() - startedAt) / 60000 : 0);
const finished = ['SUCCEEDED', 'FAILED', 'ABORTED', 'TIMED-OUT'].includes(status);
const giveUp = !finished && elapsedMin > 8;
return [{ json: {
  apify_run_id: stage.apify_run_id,
  dataset_id: stage.dataset_id || String(data.defaultDatasetId || ''),
  status: status,
  finished: finished || giveUp,
  succeeded: status === 'SUCCEEDED',
  usage_usd: Number(data.usageTotalUsd || 0),
  run_id: stage.run_id,
  run_url: 'https://api.apify.com/v2/actor-runs/' + stage.apify_run_id
} }];
""".strip()

BUILD_DS_URL_JS = r"""
const j = $input.first().json;
return [{ json: Object.assign({}, j, { dataset_url: 'https://api.apify.com/v2/datasets/' + j.dataset_id + '/items?clean=true&limit=1000' }) }];
""".strip()

PARSE_JS = TOKEN_JS + r"""

const stage = $('Stage Context').first().json;
const titles = (stage.dm_titles || []).map(t => ({ raw: t, norm: normPhrase(t) })).filter(t => t.norm);
const meta = stage.batch || [];
const bySlug = {};
for (const m of meta) bySlug[m.slug] = m;
let droppedSchema = 0;
const out = [];
for (const item of $input.all()) {
  const p = item.json || {};
  if (!p.fullName || !p.profileUrl || !p.publicIdentifier || !p.company) { droppedSchema++; continue; }
  const m = bySlug[String(p.company)];
  if (!m) { droppedSchema++; continue; }
  const headline = String(p.headline || '');
  const hNorm = ' ' + normPhrase(headline) + ' ';
  let matchedTitle = '';
  for (const t of titles) { if (hNorm.includes(' ' + t.norm + ' ')) { matchedTitle = t.raw; break; } }
  const hToks = new Set(normTokens(headline));
  const assoc = (m.distinctive_tokens || []).some(t => hToks.has(t)) || normPhrase(headline).replace(/ /g, '').includes(String(m.slug || '').toLowerCase().replace(/[^a-z0-9]/g, ''));
  const dm = !!matchedTitle;
  const save = dm && assoc;
  const canonical = 'https://www.linkedin.com/in/' + String(p.publicIdentifier).toLowerCase();
  const raw = Object.assign({}, p, { dm_matched_title: matchedTitle || null, dm_profile_version: stage.profile_version });
  out.push({ json: {
    company_id: m.company_id, full_name: String(p.fullName), title: headline,
    linkedin_url: canonical, save_flag: save ? 1 : 0,
    is_dm_match: dm, assoc_ok: assoc,
    drop_reason: save ? '' : (dm ? 'association_unverified' : 'non_dm'),
    raw_json: JSON.stringify(raw), source_url: canonical, evidence_quote: headline,
    run_id: stage.run_id, id_hash: hashId(p.publicIdentifier),
    charged: p.charged === true ? 1 : 0,
    run_counts: null
  } });
}
const counts = { returned: out.length, dropped_schema: droppedSchema };
for (const o of out) o.json.run_counts = counts;
if (!out.length) {
  out.push({ json: { company_id: '00000000-0000-0000-0000-000000000000', full_name: '', title: '', linkedin_url: '', save_flag: 0, is_dm_match: false, assoc_ok: false, drop_reason: 'none', raw_json: '{}', source_url: '', evidence_quote: '', run_id: stage.run_id, id_hash: '', charged: 0, run_counts: counts, sentinel: true } });
}
return out;
""".strip()

ROLLUP_JS = r"""
const stage = $('Stage Context').first().json;
const people = $('Parse People').all().map(i => i.json).filter(p => !p.sentinel);
const saves = $('DB - Save Person').all().map(i => i.json);
const byCompany = {};
for (const m of (stage.batch || [])) byCompany[m.company_id] = { returned: 0, charged: 0, dm_saved: 0, dup_same: 0, dup_cross: 0, non_dm_dropped: 0, association_dropped: 0 };
people.forEach((p, idx) => {
  const c = byCompany[p.company_id]; if (!c) return;
  c.returned++; c.charged += Number(p.charged || 0);
  const outcome = (saves[idx] || {}).outcome || '';
  if (p.save_flag === 1) {
    if (outcome === 'inserted') c.dm_saved++;
    else if (outcome === 'dup_same') c.dup_same++;
    else if (outcome === 'dup_cross') c.dup_cross++;
  } else if (p.drop_reason === 'non_dm') c.non_dm_dropped++;
  else if (p.drop_reason === 'association_unverified') c.association_dropped++;
});
const batch = stage.batch || [];
if (!batch.length) return [{ json: { company_id: '00000000-0000-0000-0000-000000000000', run_id: stage.run_id, detail_json: '{}', is_first: 0, act: 0 } }];
return batch.map((m, i) => {
  const c = byCompany[m.company_id];
  const detail = Object.assign({ outcome: c.returned === 0 ? 'searched_zero' : 'searched', source: 'apify_linkedin', linkedin_url: m.linkedin_url }, c);
  return { json: { company_id: m.company_id, run_id: stage.run_id, detail_json: JSON.stringify(detail), is_first: i === 0 ? 1 : 0, act: 1 } };
});
""".strip()

FAIL_ITEMS_JS = r"""
const stage = $('Stage Context').first().json;
let usage = 0; let runId = stage.apify_run_id || '';
try { const pc = $('Poll Check').first().json; usage = Number(pc.usage_usd || 0); if (pc.apify_run_id) runId = String(pc.apify_run_id); } catch (e) {}
const batch = stage.batch || [];
if (!batch.length) return [{ json: { company_id: '00000000-0000-0000-0000-000000000000', run_id: stage.run_id, usage_usd: 0, apify_run_id: runId, is_first: 0 } }];
return batch.map((m, i) => ({ json: { company_id: m.company_id, run_id: stage.run_id, usage_usd: usage, apify_run_id: runId, is_first: i === 0 ? 1 : 0 } }));
""".strip()

SUMMARY_JS = r"""
function tryAll(name) { try { return $(name).all().map(i => i.json); } catch (e) { return []; } }
function tryFirst(name) { try { return $(name).first().json || {}; } catch (e) { return {}; } }
const stage = tryFirst('Stage Context');
const people = tryAll('Parse People').filter(p => !p.sentinel);
const saves = tryAll('DB - Save Person');
const saved = saves.filter(s => s.outcome === 'inserted').length;
const counts = (people[0] && people[0].run_counts) || { returned: people.length, dropped_schema: 0 };
const chargedProfiles = people.reduce((a, p) => a + Number(p.charged || 0), 0);
const runApifyCost = chargedProfiles * 0.01 + ((stage.batch || []).length ? 0.005 : 0);
const mtdAfter = Number(stage.mtd_apify_usd || 0) + runApifyCost;
let failed = false;
try { failed = $('Build Failure Items').all().length > 0; } catch (e) {}
return [{ json: {
  success: !failed, stage: 'SF6b',
  picked: Number(stage.picked_count || 0), slug_resolved: (stage.batch || []).length,
  people_returned: counts.returned, dropped_schema: counts.dropped_schema,
  people_saved: saved, decision_makers_saved: saved,
  non_dm_dropped: people.filter(p => p.drop_reason === 'non_dm').length,
  association_dropped: people.filter(p => p.drop_reason === 'association_unverified').length,
  dup_cross_company: saves.filter(s => s.outcome === 'dup_cross').length,
  apify_profiles_charged: chargedProfiles,
  apify_run_cost_usd: Math.round(runApifyCost * 1000) / 1000,
  slug_search_cost_usd: Math.round(Number(stage.picked_count || 0) * 0.008 * 1000) / 1000,
  total_stage_cost_usd: Math.round((runApifyCost + Number(stage.picked_count || 0) * 0.008) * 1000) / 1000,
  mtd_apify_usd: Math.round(mtdAfter * 1000) / 1000,
  mtd_warning: mtdAfter > 4.5,
  apify_failed: failed,
  cap_blocked: false, empty_run: false, gate_fail: false
} }];
""".strip()

out = []
out.append("import { workflow, node, trigger, sticky, ifElse, expr } from '@n8n/workflow-sdk';")
out.append(f"const aboutNote = sticky({J('SF6c v-next - People Fetch (2026-11-17). Second half of SF6b: polls the persisted Apify run (started by SF6b), fetches the dataset by id, classifies people against the profile decision_maker_titles (deterministic phrase match, verbatim headline as evidence), saves ONLY decision-makers passing the SF6 association gate, writes per-company events + checked marks, releases claims on failure. Flat top-level chain by design (deep ifElse nesting inside branch arguments mis-wires in the SDK - proven 2026-11-17). No send node.')}, [], {{ color: 5 }});")
out.append("""
const subTrigger = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger',
  version: 1.1,
  config: {
    name: 'When Executed by Another Workflow',
    parameters: {
      workflowInputs: { values: [
        { name: 'apify_run_id', type: 'string' },
        { name: 'dataset_id', type: 'string' },
        { name: 'run_id', type: 'string' },
        { name: 'batch_json', type: 'string' },
        { name: 'dm_titles_json', type: 'string' },
        { name: 'profile_version', type: 'number' },
        { name: 'mtd_apify_usd', type: 'number' },
        { name: 'picked_count', type: 'number' }
      ] }
    },
    position: [40, 400]
  },
  output: [{ apify_run_id: 'x', dataset_id: 'y', run_id: '', batch_json: '[]', dm_titles_json: '[]', profile_version: 1, mtd_apify_usd: 0, picked_count: 0 }]
});""")
out.append(f"""
const stageNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Stage Context',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(STAGE_JS)} }},
    position: [320, 400]
  }},
  output: [{{ apify_run_id: 'x', batch: [] }}]
}});""")
out.append(f"""
const buildRunUrlNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Build Run URL',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(BUILD_RUN_URL_JS)} }},
    position: [600, 400]
  }},
  output: [{{ run_url: 'u' }}]
}});""")
out.append("""
const getRunNode = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {
    name: 'Apify - Get Run',
    onError: 'continueRegularOutput',
    alwaysOutputData: true,
    position: [880, 400],
    parameters: {
      method: 'GET',
      url: expr('{{ $json.run_url }}'),
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      options: { timeout: 60000 }
    },
    credentials: { httpHeaderAuth: newCredential('Apify') }
  },
  output: [{ data: { status: 'RUNNING' } }]
});""")
out.append(f"""
const pollCheckNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Poll Check',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(POLL_JS)} }},
    position: [1160, 400]
  }},
  output: [{{ finished: false, succeeded: false }}]
}});""")
out.append("""
const finGate = ifElse({
  version: 2.2,
  config: {
    name: 'Run Finished?',
    position: [1440, 400],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ $json.finished }}'), operator: { type: 'boolean', operation: 'true' } }],
        combinator: 'and'
      }
    }
  }
});""")
out.append("""
const waitNode = node({
  type: 'n8n-nodes-base.wait',
  version: 1.1,
  config: {
    name: 'Wait 15s',
    parameters: { amount: 15 },
    position: [1440, 640]
  },
  output: [{}]
});""")
out.append("""
const succGate = ifElse({
  version: 2.2,
  config: {
    name: 'Run Succeeded?',
    position: [1720, 400],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ $json.succeeded }}'), operator: { type: 'boolean', operation: 'true' } }],
        combinator: 'and'
      }
    }
  }
});""")
out.append(f"""
const buildDsUrlNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Build Dataset URL',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(BUILD_DS_URL_JS)} }},
    position: [2000, 400]
  }},
  output: [{{ dataset_url: 'u' }}]
}});""")
out.append("""
const getDatasetNode = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {
    name: 'Apify - Get Dataset',
    onError: 'continueRegularOutput',
    alwaysOutputData: true,
    position: [2280, 400],
    parameters: {
      method: 'GET',
      url: expr('{{ $json.dataset_url }}'),
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      options: { timeout: 120000, response: { response: { responseFormat: 'json' } } }
    },
    credentials: { httpHeaderAuth: newCredential('Apify') }
  },
  output: [{ fullName: 'x' }]
});""")
out.append(f"""
const parseNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Parse People',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(PARSE_JS)} }},
    position: [2560, 400]
  }},
  output: [{{ company_id: 'uuid', full_name: 'x' }}]
}});""")
out.append(f"""
const savePersonNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Save Person',
    position: [2840, 400],
    parameters: {{
      operation: 'executeQuery',
      query: {J(SAVE_PERSON_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.company_id, $json.full_name, $json.title, $json.linkedin_url, $json.save_flag, $json.raw_json, $json.source_url, $json.evidence_quote, $json.run_id, $json.id_hash, $json.charged ] }}}}') }}
    }},
    credentials: {{ postgres: newCredential('Postgres') }}
  }},
  output: [{{ outcome: 'inserted' }}]
}});""")
out.append(f"""
const rollupNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Company Rollup',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(ROLLUP_JS)} }},
    position: [3120, 400]
  }},
  output: [{{ company_id: 'uuid', detail_json: '{{}}' }}]
}});""")
out.append(f"""
const markCheckedNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Mark Checked + Events',
    position: [3400, 400],
    parameters: {{
      operation: 'executeQuery',
      query: {J(MARK_CHECKED_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.company_id, $json.run_id, $json.detail_json, $json.is_first, $json.act ] }}}}') }}
    }},
    credentials: {{ postgres: newCredential('Postgres') }}
  }},
  output: [{{ updated: 1 }}]
}});""")
out.append(f"""
const failItemsNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Build Failure Items',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(FAIL_ITEMS_JS)} }},
    position: [2000, 640]
  }},
  output: [{{ company_id: 'uuid', usage_usd: 0 }}]
}});""")
out.append(f"""
const failDbNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Release Claims + Failure Events',
    position: [2280, 640],
    parameters: {{
      operation: 'executeQuery',
      query: {J(FAIL_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.company_id, $json.run_id, $json.usage_usd, $json.apify_run_id, $json.is_first ] }}}}') }}
    }},
    credentials: {{ postgres: newCredential('Postgres') }}
  }},
  output: [{{ updated: 1 }}]
}});""")
out.append(f"""
const summaryNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Return - Summary',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(SUMMARY_JS)} }},
    position: [3680, 400]
  }},
  output: [{{ success: true, stage: 'SF6b', picked: 0 }}]
}});""")
out.append(f"""
const summaryFailNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Return - Summary (Run Failed)',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(SUMMARY_JS)} }},
    position: [2560, 640]
  }},
  output: [{{ success: false, stage: 'SF6b', picked: 0 }}]
}});""")
out.append("""
export default workflow('leadfinder-sf6c-vnext', 'SF6c v-next - People Fetch (poll + save)')
  .add(aboutNote)
  .add(subTrigger)
  .to(stageNode)
  .to(buildRunUrlNode)
  .to(getRunNode)
  .to(pollCheckNode)
  .to(finGate
    .onTrue(succGate
      .onTrue(buildDsUrlNode
        .to(getDatasetNode)
        .to(parseNode)
        .to(savePersonNode)
        .to(rollupNode)
        .to(markCheckedNode)
        .to(summaryNode))
      .onFalse(failItemsNode
        .to(failDbNode)
        .to(summaryFailNode)))
    .onFalse(waitNode
      .to(getRunNode)));
""")
code = '\n'.join(out) + '\n'
(BASE/'sf6c-vnext.ts').write_text(code)
json.dump({"code": code, "name": "SF6c v-next - People Fetch (poll + save)"}, open(BASE/'create-sf6c-vnext.json', 'w'))
print('sf6c generated', len(code))
