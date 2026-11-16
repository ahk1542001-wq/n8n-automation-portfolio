import json, pathlib
BASE = pathlib.Path(__file__).resolve().parent
example_ctx = json.load(open(pathlib.Path(__file__).resolve().parent/'example-context.json'))
def J(s): return json.dumps(s)

CTX_JS = "return { json: { business_context: " + json.dumps(example_ctx) + ", existing_profile_id: '', profile_version: 1, max_per_query: 5, spend_cap_usd: null, discovery_cache_ttl_hours: 24, discovery_source: 'places', import_sheet_id: '', import_tab: 'Import', coverage_min_ratio: 0, approval_sheet_id_vnext: '' } };"

STAGE_JS = r"""
const inp = $input.first().json;
const ctx = $('Business Context (edit me)').item.json;
return [{ json: { search_profile_id: inp.search_profile_id, profile_version: inp.version || ctx.profile_version || 1, max_per_query: ctx.max_per_query || 5, research_min_fit: ctx.research_min_fit || 30, max_research: ctx.max_research || 3, people_min_fit: ctx.people_min_fit || 30, max_people_companies: ctx.max_people_companies || 3, spend_cap_usd: (ctx.spend_cap_usd === undefined ? null : ctx.spend_cap_usd), discovery_cache_ttl_hours: ctx.discovery_cache_ttl_hours || 24, discovery_source: ctx.discovery_source || 'places', import_sheet_id: ctx.import_sheet_id || '', import_tab: ctx.import_tab || 'Import', coverage_min_ratio: ctx.coverage_min_ratio || 0, publish_limit: ctx.publish_limit || 200, approval_sheet_id_vnext: ctx.approval_sheet_id_vnext || '' } }];
""".strip()

GLUE4_JS = r"""
const inp = $input.first().json;
const stage = $('Stage Context').item.json;
const run = $('DB - Create Run Record').item.json;
return [{ json: { search_profile_id: stage.search_profile_id, profile_version: stage.profile_version, run_id: run.id, candidates: inp.candidates || [], discovered: inp.count || 0 } }];
""".strip()

GLUE7_JS = r"""
const inp = $input.first().json;
const g = $('Glue - To SF4').item.json;
return [{ json: { search_profile_id: g.search_profile_id, profile_version: g.profile_version, run_id: g.run_id, dedupe: inp } }];
""".strip()

SUMMARY_JS = r"""
const sf7 = $('SF7 v-next - Score Leads').item.json;
const sf5 = $('SF5 v-next - Research Leads').item.json;
const sf3 = $('SF3 v-next - Find People').item.json;
const sf9 = $('SF9 v-next - Timing Re-Score').item.json;
const sf8 = $('SF8 v-next - Approval View Sync').item.json;
const g4 = $('Glue - To SF4').item.json;
const g7 = $('Glue - To SF7').item.json;
const run = $('DB - Create Run Record').item.json;
return [{ json: { success: true, run_id: run.id, search_profile_id: g4.search_profile_id, profile_version: g4.profile_version,
  discovery: { found: g4.discovered },
  dedupe: { inserted: g7.dedupe.inserted, duplicates: g7.dedupe.duplicates, suppressed: g7.dedupe.suppressed },
  scoring: { scored: sf7.scored, skipped_already_scored: sf7.skipped_already_scored, insufficient_data: (sf7.results || []).filter(r => r.band === 'insufficient_data').length, results: sf7.results },
  profile: { max_achievable: $('Coverage Check').item.json.max_achievable, a_unreachable: $('Coverage Check').item.json.a_unreachable, scaled_a: $('Coverage Check').item.json.scaled_a },
  research: { researched: sf5.researched, facts_saved: sf5.facts_saved, signals_saved: sf5.signals_saved, people_saved: sf5.people_saved },
  people: { companies_processed: sf3.companies_processed, people_extracted: sf3.people_extracted, people_saved: sf3.people_saved, site_pages_fetched: sf3.site_pages_fetched || 0 },
  timing: { rescored: sf9.rescored, with_timing: sf9.with_timing },
  approval_view: { published: sf8.published } } }];
""".strip()


COVERAGE_JS = r"""
const row = $input.first().json || {};
const rubric = row.rubric || {};
const profile = row.profile || {};
let det = (rubric.coverage && typeof rubric.coverage.deterministic_points === 'number') ? rubric.coverage.deterministic_points : null;
if (det === null) {
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
  for (const s of (profile.sources || [])) for (const L of (s.locations || [])) locTargets.push(String(L).toLowerCase());
  det = 0;
  for (const c of (rubric.fit_criteria || [])) if (classifyCriterion(c, locTargets) !== 'needs_research') det += Number(c.max_points) || 0;
}
const llmMax = Number(rubric.llm_judgement_max || 30);
const maxA = det + llmMax;
return [{ json: { status: row.status || '', deterministic_points: det, coverage_ok: det >= 35, max_achievable: maxA, scaled_a: Math.ceil(75 * maxA / 100), scaled_b: Math.ceil(55 * maxA / 100), scaled_c: Math.ceil(36 * maxA / 100), a_unreachable: maxA < 75, maxa_ok: maxA > 0 } }];
""".strip()


SNAPSHOT_JS = r"""
const stage = $('Stage Context').item.json;
const run = $('DB - Create Run Record').item.json;
const cfg = { search_profile_id: stage.search_profile_id, profile_version: stage.profile_version, max_per_query: stage.max_per_query, research_min_fit: stage.research_min_fit, max_research: stage.max_research, people_min_fit: stage.people_min_fit, max_people_companies: stage.max_people_companies, spend_cap_usd: stage.spend_cap_usd, discovery_source: stage.discovery_source, discovery_cache_ttl_hours: stage.discovery_cache_ttl_hours, import_sheet_id: stage.import_sheet_id, import_tab: stage.import_tab, coverage_min_ratio: stage.coverage_min_ratio, publish_limit: stage.publish_limit, approval_sheet_id_vnext: stage.approval_sheet_id_vnext, orchestrator: 'wf00-vnext' };
return [{ json: { run_id: run.id, config_snapshot: JSON.stringify(cfg) } }];
""".strip()

COVRATIO_JS = r"""
const row = $input.first().json || {};
const stage = $('Stage Context').item.json;
const discovered = Number(row.discovered || 0), scored = Number(row.scored || 0), matched = Number(row.det_matched || 0);
const minRatio = Number(stage.coverage_min_ratio || 0);
const ratio = discovered > 0 ? matched / discovered : 0;
const ok = discovered > 0 && ratio >= minRatio;
const run = $('DB - Create Run Record').item.json;
const body = 'WF00 v-next run ' + run.id + ' closed as insufficient_coverage (F27 post-discovery gate).\nDiscovered: ' + discovered + '\nScored: ' + scored + '\nDeterministic-matched: ' + matched + '\nCoverage ratio: ' + ratio.toFixed(3) + ' (minimum ' + minRatio + ')\nProfile: ' + stage.search_profile_id + ' v' + stage.profile_version;
return [{ json: { ratio_ok: ok, ratio, discovered, scored, det_matched: matched, sendTo: 'owner@example.com', subject: 'WF00 v-next - insufficient_coverage ' + run.id, body } }];
""".strip()

def execwf(name, wf_id, cached, inputs, pos, output):
    schema = []
    value_parts = []
    for idname, typ, exprv in inputs:
        schema.append({ 'id': idname, 'displayName': idname, 'required': False, 'defaultMatch': False, 'display': True, 'type': typ, 'canBeUsedToMatch': True })
        value_parts.append(f"{idname}: {exprv}")
    values_ts = "{ " + ", ".join(value_parts) + " }"
    return f"""
const {name} = node({{
  type: 'n8n-nodes-base.executeWorkflow',
  version: 1.2,
  config: {{
    name: {J(cached)},
    parameters: {{
      source: 'database',
      workflowId: {{ __rl: true, mode: 'id', value: {J(wf_id)}, cachedResultName: {J(cached)} }},
      workflowInputs: {{
        mappingMode: 'defineBelow',
        value: {values_ts},
        matchingColumns: [],
        schema: {J(schema)}
      }},
      mode: 'once',
      options: {{ waitForSubWorkflow: true }}
    }},
    position: {pos}
  }},
  output: [{J(output)}]
}});"""

E = lambda s: f"expr('{{{{ {s} }}}}')"
out = []
out.append("import { workflow, node, trigger, sticky, ifElse, expr } from '@n8n/workflow-sdk';")
out.append("")
out.append(f"const aboutNote = sticky({J('WF00 v-next - Lead Finder Orchestrator (F22/F27/F28/F31/F34 assembly). Manual start -> business context -> SF1 profile (or resume an existing profile id) -> run record -> APPROVAL GATE (profile status must be approved in the database) -> SF2 Maps discovery -> SF4 dedupe -> SF7 scoring -> SF5 research -> SF3 v2 people finder (open route, 2 searches) -> SF9 timing re-score -> SF8 approval view sync -> run closed. v8: coverage gate after the approval gate (rubric deterministic coverage must be >= 35/70, from rubric.coverage or recomputed with the SF7 classifier); SF5 v2 and SF3 v3 return empty-pick summaries so a run always closes. Error workflow ERR marks stuck runs failed. Drafts only; nothing is ever sent.')}, [], {{ color: 5 }});")
out.append("""
const startTrigger = trigger({
  type: 'n8n-nodes-base.manualTrigger',
  version: 1,
  config: { name: 'START - New Lead Run', position: [40, 400] },
  output: [{}]
});""")
out.append(f"""
const contextNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Business Context (edit me)',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(CTX_JS)} }},
    position: [280, 400]
  }},
  output: [{{ business_context: {{}}, existing_profile_id: '', profile_version: 1, max_per_query: 5 }}]
}});""")
out.append("""
const hasExisting = ifElse({
  version: 2.2,
  config: {
    name: 'Has Existing Profile?',
    position: [520, 400],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ $json.existing_profile_id }}'), operator: { type: 'string', operation: 'notEmpty', singleValue: true } }],
        combinator: 'and'
      }
    }
  }
});""")
out.append(f"""
const useExisting = node({{
  type: 'n8n-nodes-base.set',
  version: 3.4,
  config: {{
    name: 'Use Existing Profile',
    position: [760, 260],
    parameters: {{
      mode: 'manual',
      includeOtherFields: false,
      assignments: {{ assignments: [
        {{ id: 'u1', name: 'search_profile_id', value: expr('{{{{ $json.existing_profile_id }}}}'), type: 'string' }},
        {{ id: 'u2', name: 'version', value: expr('{{{{ $json.profile_version }}}}'), type: 'number' }},
        {{ id: 'u3', name: 'status', value: 'existing', type: 'string' }}
      ] }}
    }}
  }},
  output: [{{ search_profile_id: 'uuid', version: 1, status: 'existing' }}]
}});""")
out.append(execwf('callSf1', 'ayTqyqiZIQ1dwLhW', 'SF1 - Generate Search Profile',
    [('business_context', 'object', "expr('{{ $json.business_context }}')")], [760, 540],
    {'success': True, 'search_profile_id': 'uuid', 'version': 1, 'status': 'draft'}))
out.append(f"""
const stageCtx = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Stage Context',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(STAGE_JS)} }},
    position: [1020, 400]
  }},
  output: [{{ search_profile_id: 'uuid', profile_version: 1, max_per_query: 5, research_min_fit: 30, max_research: 3, people_min_fit: 30, max_people_companies: 3 }}]
}});""")
open(BASE/'part1-vnext.txt','w').write('\n'.join(out))
print('part1 written', len(out))

# ---------------- part 2: run record, gate, SF2/SF4/SF7, close ----------------
out.append(f"""
const createRun = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Create Run Record',
    position: [1260, 400],
    parameters: {{
      operation: 'executeQuery',
      query: "INSERT INTO runs (search_profile_id, profile_version, status, notes) VALUES ($1::uuid, $2, 'started', 'WF00 orchestrated run') RETURNING id, search_profile_id, profile_version",
      options: {{ queryReplacement: expr('{{{{ [ $json.search_profile_id, $json.profile_version ] }}}}') }}
    }}
  }},
  output: [{{ id: 'run-uuid', search_profile_id: 'uuid', profile_version: 1 }}]
}});""")
out.append(f"""
const loadStatus = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Load Profile Status',
    position: [1500, 400],
    parameters: {{
      operation: 'executeQuery',
      query: "SELECT status, profile, rubric FROM search_profiles WHERE id = $1::uuid",
      options: {{ queryReplacement: expr('{{{{ [ $(\'Stage Context\').item.json.search_profile_id ] }}}}') }}
    }}
  }},
  output: [{{ status: 'draft', profile: {{}}, rubric: {{}} }}]
}});""")
out.append("""
const approvedGate = ifElse({
  version: 2.2,
  config: {
    name: 'Profile Approved?',
    position: [1740, 400],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ $json.status }}'), rightValue: 'approved', operator: { type: 'string', operation: 'equals' } }],
        combinator: 'and'
      }
    }
  }
});""")
out.append(f"""
const awaitReturn = node({{
  type: 'n8n-nodes-base.set',
  version: 3.4,
  config: {{
    name: 'Return - Awaiting Approval',
    position: [1980, 560],
    parameters: {{
      mode: 'manual',
      includeOtherFields: false,
      assignments: {{ assignments: [
        {{ id: 'w1', name: 'success', value: false, type: 'boolean' }},
        {{ id: 'w2', name: 'stage', value: 'awaiting_profile_approval', type: 'string' }},
        {{ id: 'w3', name: 'search_profile_id', value: expr('{{{{ $(\'Stage Context\').item.json.search_profile_id }}}}'), type: 'string' }},
        {{ id: 'w4', name: 'run_id', value: expr('{{{{ $(\'DB - Create Run Record\').item.json.id }}}}'), type: 'string' }},
        {{ id: 'w5', name: 'message', value: 'Profile is still draft. Approve it in the database (status = approved), then re-run WF00 with existing_profile_id set to this profile.', type: 'string' }}
      ] }}
    }}
  }},
  output: [{{ success: false, stage: 'awaiting_profile_approval' }}]
}});""")
out.append(f"""
const markAwaiting = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Mark Run Awaiting Approval',
    position: [1860, 560],
    parameters: {{
      operation: 'executeQuery',
      query: "UPDATE runs SET status = 'awaiting_profile_approval', notes = 'Stopped at the approval gate - profile is still draft' WHERE id = $1::uuid RETURNING id, status",
      options: {{ queryReplacement: expr('{{{{ [ $(\'DB - Create Run Record\').item.json.id ] }}}}') }}
    }}
  }},
  output: [{{ id: 'run-uuid', status: 'awaiting_profile_approval' }}]
}});""")

out.append(f"""
const coverageCheck = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Coverage Check',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(COVERAGE_JS)} }},
    position: [1620, 400]
  }},
  output: [{{ status: 'approved', deterministic_points: 45, coverage_ok: true }}]
}});""")
out.append("""
const coverageGate = ifElse({
  version: 2.2,
  config: {
    name: 'Coverage OK?',
    position: [1860, 400],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ $json.coverage_ok }}'), operator: { type: 'boolean', operation: 'true' } }],
        combinator: 'and'
      }
    }
  }
});""")
out.append(f"""
const markCoverage = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Mark Run Coverage Blocked',
    position: [2100, 640],
    parameters: {{
      operation: 'executeQuery',
      query: "UPDATE runs SET status = 'blocked_coverage', notes = 'Stopped at the coverage gate - rubric deterministic coverage below 35/70. Regenerate the profile with SF1 (deterministic scoring contract), approve the new version, then re-run.' WHERE id = $1::uuid RETURNING id, status",
      options: {{ queryReplacement: expr('{{{{ [ $(\'DB - Create Run Record\').item.json.id ] }}}}') }}
    }}
  }},
  output: [{{ id: 'run-uuid', status: 'blocked_coverage' }}]
}});""")
out.append(f"""
const coverageReturn = node({{
  type: 'n8n-nodes-base.set',
  version: 3.4,
  config: {{
    name: 'Return - Coverage Blocked',
    position: [2340, 640],
    parameters: {{
      mode: 'manual',
      includeOtherFields: false,
      assignments: {{ assignments: [
        {{ id: 'c1', name: 'success', value: false, type: 'boolean' }},
        {{ id: 'c2', name: 'stage', value: 'blocked_coverage_below_floor', type: 'string' }},
        {{ id: 'c3', name: 'search_profile_id', value: expr('{{{{ $(\'Stage Context\').item.json.search_profile_id }}}}'), type: 'string' }},
        {{ id: 'c4', name: 'run_id', value: expr('{{{{ $(\'DB - Create Run Record\').item.json.id }}}}'), type: 'string' }},
        {{ id: 'c5', name: 'deterministic_points', value: expr('{{{{ $(\'Coverage Check\').item.json.deterministic_points }}}}'), type: 'number' }},
        {{ id: 'c6', name: 'message', value: 'Rubric deterministic coverage is below the 35/70 floor. Regenerate the profile with SF1 so the rubric follows the deterministic scoring contract, approve the new version, then re-run.', type: 'string' }}
      ] }}
    }}
  }},
  output: [{{ success: false, stage: 'blocked_coverage_below_floor' }}]
}});""")
out.append(execwf('callSf2', 'imW1Fn0pgBnTrWJF', 'SF2 v-next - Discover',
    [('search_profile_id', 'string', "expr('{{ $('Stage Context').item.json.search_profile_id }}')"),
     ('profile_version', 'number', "expr('{{ $('Stage Context').item.json.profile_version }}')"),
     ('run_id', 'string', "expr('{{ $('DB - Create Run Record').item.json.id }}')"),
     ('max_per_query', 'number', "expr('{{ $('Stage Context').item.json.max_per_query }}')"), ('discovery_source', 'string', "expr('{{ $('Stage Context').item.json.discovery_source }}')"), ('import_sheet_id', 'string', "expr('{{ $('Stage Context').item.json.import_sheet_id }}')"), ('import_tab', 'string', "expr('{{ $('Stage Context').item.json.import_tab }}')"), ('discovery_cache_ttl_hours', 'number', "expr('{{ $('Stage Context').item.json.discovery_cache_ttl_hours }}')")], [1980, 260],
    {'success': True, 'count': 0, 'candidates': []}))
out.append(f"""
const glue4 = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Glue - To SF4',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(GLUE4_JS)} }},
    position: [2220, 260]
  }},
  output: [{{ search_profile_id: 'uuid', profile_version: 1, run_id: 'uuid', candidates: [], discovered: 0 }}]
}});""")
out.append(execwf('callSf4', 'pJIqH7PlZ83VBWbX', 'SF4 - Dedupe + Exclusion',
    [('search_profile_id', 'string', "expr('{{ $json.search_profile_id }}')"),
     ('profile_version', 'number', "expr('{{ $json.profile_version }}')"),
     ('run_id', 'string', "expr('{{ $json.run_id }}')"),
     ('candidates', 'array', "expr('{{ $json.candidates }}')")], [2460, 260],
    {'success': True, 'inserted': 0, 'duplicates': 0, 'suppressed': 0}))
out.append(f"""
const glue7 = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Glue - To SF7',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(GLUE7_JS)} }},
    position: [2700, 260]
  }},
  output: [{{ search_profile_id: 'uuid', profile_version: 1, run_id: 'uuid', dedupe: {{}} }}]
}});""")
out.append(execwf('callSf7', 'IKnu5IRC4NGu35Lc', 'SF7 v-next - Score Leads',
    [('search_profile_id', 'string', "expr('{{ $json.search_profile_id }}')"),
     ('profile_version', 'number', "expr('{{ $json.profile_version }}')"),
     ('run_id', 'string', "expr('{{ $json.run_id }}')")], [2940, 260],
    {'success': True, 'scored': 0, 'results': []}))
out.append(execwf('callSf5', 'aAIfiQ9fSWcG6zPr', 'SF5 v-next - Research Leads',
    [('search_profile_id', 'string', "expr('{{ $('Stage Context').item.json.search_profile_id }}')"),
     ('profile_version', 'number', "expr('{{ $('Stage Context').item.json.profile_version }}')"),
     ('run_id', 'string', "expr('{{ $('DB - Create Run Record').item.json.id }}')"),
     ('max_research', 'number', "expr('{{ $('Stage Context').item.json.max_research }}')"),
     ('min_fit', 'number', "expr('{{ $('Stage Context').item.json.research_min_fit }}')"), ('spend_cap_usd', 'number', "expr('{{ $('Stage Context').item.json.spend_cap_usd }}')")], [3180, 260],
    {'success': True, 'researched': 0, 'facts_saved': 0, 'signals_saved': 0, 'people_saved': 0}))

out.append(execwf('callSf3', 'cCN8KY8bnIYtwNed', 'SF3 v-next - Find People',
    [('search_profile_id', 'string', "expr('{{ $('Stage Context').item.json.search_profile_id }}')"),
     ('profile_version', 'number', "expr('{{ $('Stage Context').item.json.profile_version }}')"),
     ('run_id', 'string', "expr('{{ $('DB - Create Run Record').item.json.id }}')"),
     ('max_companies', 'number', "expr('{{ $('Stage Context').item.json.max_people_companies }}')"),
     ('min_fit', 'number', "expr('{{ $('Stage Context').item.json.people_min_fit }}')"), ('spend_cap_usd', 'number', "expr('{{ $('Stage Context').item.json.spend_cap_usd }}')")], [3420, 260],
    {'success': True, 'companies_processed': 0, 'people_extracted': 0, 'people_saved': 0}))
out.append(execwf('callSf9', 'UJvLDTNetRBUk6PX', 'SF9 v-next - Timing Re-Score',
    [('search_profile_id', 'string', "expr('{{ $('Stage Context').item.json.search_profile_id }}')"),
     ('profile_version', 'number', "expr('{{ $('Stage Context').item.json.profile_version }}')"),
     ('run_id', 'string', "expr('{{ $('DB - Create Run Record').item.json.id }}')")], [3660, 260],
    {'success': True, 'rescored': 0, 'with_timing': 0}))
out.append(execwf('callSf8', 'UP1R34u2xwvg4nvD', 'SF8 v-next - Approval View Sync',
    [('search_profile_id', 'string', "expr('{{ $('Stage Context').item.json.search_profile_id }}')"),
     ('profile_version', 'number', "expr('{{ $('Stage Context').item.json.profile_version }}')"), ('run_id', 'string', "expr('{{ $('DB - Create Run Record').item.json.id }}')"), ('approval_sheet_id_vnext', 'string', "expr('{{ $('Stage Context').item.json.approval_sheet_id_vnext }}')"), ('publish_limit', 'number', "expr('{{ $('Stage Context').item.json.publish_limit }}')")], [3900, 260],
    {'success': True, 'published': 0}))
out.append(f"""
const closeRun = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Close Run Record',
    position: [4140, 260],
    parameters: {{
      operation: 'executeQuery',
      query: "UPDATE runs SET status = 'done', finished_at = now(), notes = $2 WHERE id = $1::uuid RETURNING id, status",
      options: {{ queryReplacement: expr('{{{{ [ $(\'Glue - To SF7\').item.json.run_id, \\'SF2 found \\' + $(\'Glue - To SF4\').item.json.discovered + \\'; SF4 inserted \\' + $('Glue - To SF7').item.json.dedupe.inserted + \\' (dup \\' + $('Glue - To SF7').item.json.dedupe.duplicates + \\', suppressed \\' + $('Glue - To SF7').item.json.dedupe.suppressed + \\'); SF7 scored \\' + $(\'SF7 v-next - Score Leads\').item.json.scored + \\'; SF5 researched \\' + $(\'SF5 v-next - Research Leads\').item.json.researched + \\' ; SF3 people searched \\' + $(\'SF3 v-next - Find People\').item.json.companies_processed + \\' companies, saved \\' + $(\'SF3 v-next - Find People\').item.json.people_saved + \\' people; SF9 timing rescored \\' + $(\'SF9 v-next - Timing Re-Score\').item.json.rescored + \\' (\\' + $(\'SF9 v-next - Timing Re-Score\').item.json.with_timing + \\' with timing); SF8 approval view published \\' + $(\'SF8 v-next - Approval View Sync\').item.json.published + \\' rows\\' ] }}}}') }}
    }}
  }},
  output: [{{ id: 'run-uuid', status: 'done' }}]
}});""")
out.append(f"""
const summaryNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Run Summary',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(SUMMARY_JS)} }},
    position: [4380, 260]
  }},
  output: [{{ success: true }}]
}});""")
out.append(f"""
const snapshotBuild = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Build Config Snapshot (F34)',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(SNAPSHOT_JS)} }},
    position: [1380, 400]
  }},
  output: [{{ run_id: 'uuid', config_snapshot: '{{}}' }}]
}});""")
out.append(f"""
const snapshotWrite = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Write Config Snapshot (F34)',
    position: [1500, 400],
    parameters: {{
      operation: 'executeQuery',
      query: "UPDATE runs SET config_snapshot = $2::jsonb WHERE id = $1::uuid RETURNING id",
      options: {{ queryReplacement: expr('{{{{ [ $json.run_id, $json.config_snapshot ] }}}}') }}
    }}
  }},
  output: [{{ id: 'run-uuid' }}]
}});""")
out.append("""
const maxAGate = ifElse({
  version: 2.2,
  config: {
    name: 'Max Achievable OK? (F22)',
    position: [1860, 300],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ $json.maxa_ok }}'), operator: { type: 'boolean', operation: 'true' } }],
        combinator: 'and'
      }
    }
  }
});""")
out.append(f"""
const markInsufficient = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Mark Run Insufficient Coverage',
    position: [2100, 760],
    parameters: {{
      operation: 'executeQuery',
      query: "UPDATE runs SET status = 'insufficient_coverage', finished_at = now(), notes = 'Stopped at the F27 preflight gate - profile max_achievable is 0: no deterministic or judge-scored path to any band. Rework the rubric or the discovery source.' WHERE id = $1::uuid RETURNING id, status",
      options: {{ queryReplacement: expr('{{{{ [ $(\'DB - Create Run Record\').item.json.id ] }}}}') }}
    }}
  }},
  output: [{{ id: 'run-uuid', status: 'insufficient_coverage' }}]
}});""")
out.append(f"""
const insuffReturn = node({{
  type: 'n8n-nodes-base.set',
  version: 3.4,
  config: {{
    name: 'Return - Insufficient Coverage',
    position: [2340, 760],
    parameters: {{
      mode: 'manual',
      includeOtherFields: false,
      assignments: {{ assignments: [
        {{ id: 'i1', name: 'success', value: false, type: 'boolean' }},
        {{ id: 'i2', name: 'stage', value: 'insufficient_coverage', type: 'string' }},
        {{ id: 'i3', name: 'search_profile_id', value: expr('{{{{ $(\'Stage Context\').item.json.search_profile_id }}}}'), type: 'string' }},
        {{ id: 'i4', name: 'run_id', value: expr('{{{{ $(\'DB - Create Run Record\').item.json.id }}}}'), type: 'string' }},
        {{ id: 'i5', name: 'message', value: 'Profile max_achievable is 0 - nothing in this rubric can be scored. Rework the profile before spending on discovery.', type: 'string' }}
      ] }}
    }}
  }},
  output: [{{ success: false, stage: 'insufficient_coverage' }}]
}});""")
out.append(f"""
const covRatioNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Coverage Ratio Counts (F27)',
    position: [3060, 260],
    parameters: {{
      operation: 'executeQuery',
      query: "SELECT (SELECT count(*) FROM companies WHERE search_profile_id = $1::uuid) AS discovered, (SELECT count(*) FROM scores WHERE search_profile_id = $1::uuid AND profile_version = $2) AS scored, (SELECT count(*) FROM scores s WHERE s.search_profile_id = $1::uuid AND s.profile_version = $2 AND EXISTS (SELECT 1 FROM jsonb_array_elements(s.fit_components) c WHERE (c->>'awarded')::numeric > 0)) AS det_matched",
      options: {{ queryReplacement: expr('{{{{ [ $(\'Stage Context\').item.json.search_profile_id, $(\'Stage Context\').item.json.profile_version ] }}}}') }}
    }}
  }},
  output: [{{ discovered: 0, scored: 0, det_matched: 0 }}]
}});""")
out.append(f"""
const covCheck = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Coverage Ratio Check (F27)',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(COVRATIO_JS)} }},
    position: [3180, 260]
  }},
  output: [{{ ratio_ok: true, ratio: 0, discovered: 0, scored: 0, det_matched: 0 }}]
}});""")
out.append("""
const covGate = ifElse({
  version: 2.2,
  config: {
    name: 'Coverage Ratio OK? (F27)',
    position: [3300, 260],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ $json.ratio_ok }}'), operator: { type: 'boolean', operation: 'true' } }],
        combinator: 'and'
      }
    }
  }
});""")
out.append(f"""
const markInsufficient2 = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Mark Run Insufficient Coverage (F27)',
    position: [3420, 420],
    parameters: {{
      operation: 'executeQuery',
      query: "UPDATE runs SET status = 'insufficient_coverage', finished_at = now(), notes = 'Stopped at the F27 post-discovery coverage gate - too few discovered companies match the rubric deterministically. See the Gmail draft alert for the ratio.' WHERE id = $1::uuid RETURNING id, status",
      options: {{ queryReplacement: expr('{{{{ [ $(\'DB - Create Run Record\').item.json.id ] }}}}') }}
    }}
  }},
  output: [{{ id: 'run-uuid', status: 'insufficient_coverage' }}]
}});""")
out.append("""
const gmailDraftNode = node({
  type: 'n8n-nodes-base.gmail',
  version: 2.1,
  config: {
    name: 'Gmail - Coverage Alert Draft (NEVER SENDS)',
    parameters: {
      resource: 'draft',
      operation: 'create',
      sendTo: expr('{{ $('Coverage Ratio Check (F27)').item.json.sendTo }}'),
      subject: expr('{{ $('Coverage Ratio Check (F27)').item.json.subject }}'),
      emailType: 'text',
      message: expr('{{ $('Coverage Ratio Check (F27)').item.json.body }}'),
      options: {}
    },
    credentials: { gmailOAuth2: newCredential('Gmail') },
    position: [3540, 420]
  },
  output: [{ id: 'draft-id' }]
});""")
out.append(f"""
const insuff2Return = node({{
  type: 'n8n-nodes-base.set',
  version: 3.4,
  config: {{
    name: 'Return - Insufficient Coverage (F27)',
    position: [3660, 420],
    parameters: {{
      mode: 'manual',
      includeOtherFields: false,
      assignments: {{ assignments: [
        {{ id: 'j1', name: 'success', value: false, type: 'boolean' }},
        {{ id: 'j2', name: 'stage', value: 'insufficient_coverage', type: 'string' }},
        {{ id: 'j3', name: 'search_profile_id', value: expr('{{{{ $(\'Stage Context\').item.json.search_profile_id }}}}'), type: 'string' }},
        {{ id: 'j4', name: 'run_id', value: expr('{{{{ $(\'DB - Create Run Record\').item.json.id }}}}'), type: 'string' }},
        {{ id: 'j5', name: 'message', value: 'Post-discovery coverage below the configured minimum (or nothing discovered). Run closed before research spend; see the Gmail draft alert.', type: 'string' }}
      ] }}
    }}
  }},
  output: [{{ success: false, stage: 'insufficient_coverage' }}]
}});""")
out.append("""
export default workflow('leadfinder-wf00-vnext', 'WF00 v-next - Lead Finder Orchestrator')
  .add(aboutNote)
  .add(startTrigger)
  .to(contextNode)
  .to(hasExisting
    .onTrue(useExisting.to(stageCtx.to(createRun).to(snapshotBuild).to(snapshotWrite).to(loadStatus).to(coverageCheck).to(approvedGate
      .onTrue(maxAGate
        .onTrue(coverageGate
          .onTrue(callSf2.to(glue4).to(callSf4).to(glue7).to(callSf7).to(covRatioNode).to(covCheck).to(covGate
            .onTrue(callSf5.to(callSf3).to(callSf9).to(callSf8).to(closeRun).to(summaryNode))
            .onFalse(markInsufficient2.to(gmailDraftNode).to(insuff2Return))
          ))
          .onFalse(markCoverage.to(coverageReturn))
        )
        .onFalse(markInsufficient.to(insuffReturn))
      )
      .onFalse(markAwaiting.to(awaitReturn))
    )))
    .onFalse(callSf1.to(stageCtx))
  );""")

code = '\n'.join(out) + '\n'
(BASE/'wf00-vnext3.ts').write_text(code)
json.dump({"code": code}, open(BASE/'validate-wf00-vnext3.json','w'))
json.dump({"code": code, "name": "WF00 v-next - Lead Finder Orchestrator"}, open(BASE/'create-wf00-vnext3.json','w'))
print('written', len(code))
