import json, pathlib
BASE = pathlib.Path(__file__).resolve().parent
example_ctx = json.load(open(BASE/'example-context.json'))
def J(s): return json.dumps(s)

CTX_JS = "return { json: { business_context: " + json.dumps(example_ctx) + ", existing_profile_id: '', profile_version: 1, max_per_query: 5 } };"

STAGE_JS = r"""
const inp = $input.first().json;
const ctx = $('Business Context (edit me)').item.json;
return [{ json: { search_profile_id: inp.search_profile_id, profile_version: inp.version || ctx.profile_version || 1, max_per_query: ctx.max_per_query || 5, research_min_fit: ctx.research_min_fit || 30, max_research: ctx.max_research || 3, people_min_fit: ctx.people_min_fit || 30, max_people_companies: ctx.max_people_companies || 3 } }];
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
const sf7 = $('SF7 - Score Leads').item.json;
const sf5 = $('SF5 - Research Leads').item.json;
const sf3 = $('SF3 - Find People (Open) v2').item.json;
const sf9 = $('SF9 - Timing Re-Score').item.json;
const sf8 = $('SF8 - Approval View Sync').item.json;
const g4 = $('Glue - To SF4').item.json;
const g7 = $('Glue - To SF7').item.json;
const run = $('DB - Create Run Record').item.json;
return [{ json: { success: true, run_id: run.id, search_profile_id: g4.search_profile_id, profile_version: g4.profile_version,
  discovery: { found: g4.discovered },
  dedupe: { inserted: g7.dedupe.inserted, duplicates: g7.dedupe.duplicates, suppressed: g7.dedupe.suppressed },
  scoring: { scored: sf7.scored, skipped_already_scored: sf7.skipped_already_scored, results: sf7.results },
  research: { researched: sf5.researched, facts_saved: sf5.facts_saved, signals_saved: sf5.signals_saved, people_saved: sf5.people_saved },
  people: { companies_processed: sf3.companies_processed, people_extracted: sf3.people_extracted, people_saved: sf3.people_saved },
  timing: { rescored: sf9.rescored, with_timing: sf9.with_timing },
  approval_view: { published: sf8.published } } }];
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
out.append(f"const aboutNote = sticky({J('WF00 - Lead Finder Orchestrator (FULL). Manual start -> business context -> SF1 profile (or resume an existing profile id) -> run record -> APPROVAL GATE (profile status must be approved in the database) -> SF2 Maps discovery -> SF4 dedupe -> SF7 scoring -> SF5 research -> SF3 v2 people finder (open route, 2 searches) -> SF9 timing re-score -> SF8 approval view sync -> run closed. Error workflow ERR marks stuck runs failed. Drafts only; nothing is ever sent.')}, [], {{ color: 5 }});")
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
open(BASE/'part1.txt','w').write('\n'.join(out))
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
      query: "SELECT status FROM search_profiles WHERE id = $1::uuid",
      options: {{ queryReplacement: expr('{{{{ [ $json.search_profile_id ] }}}}') }}
    }}
  }},
  output: [{{ status: 'draft' }}]
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
out.append(execwf('callSf2', '5djXrCvudO5YLBkk', 'SF2 - Discover (Maps)',
    [('search_profile_id', 'string', "expr('{{ $('Stage Context').item.json.search_profile_id }}')"),
     ('profile_version', 'number', "expr('{{ $('Stage Context').item.json.profile_version }}')"),
     ('run_id', 'string', "expr('{{ $('DB - Create Run Record').item.json.id }}')"),
     ('max_per_query', 'number', "expr('{{ $('Stage Context').item.json.max_per_query }}')")], [1980, 260],
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
out.append(execwf('callSf7', 'b87J5pDCBNAL4twx', 'SF7 - Score Leads',
    [('search_profile_id', 'string', "expr('{{ $json.search_profile_id }}')"),
     ('profile_version', 'number', "expr('{{ $json.profile_version }}')"),
     ('run_id', 'string', "expr('{{ $json.run_id }}')")], [2940, 260],
    {'success': True, 'scored': 0, 'results': []}))
out.append(execwf('callSf5', 'iDOzbKCdbvM624oP', 'SF5 - Research Leads',
    [('search_profile_id', 'string', "expr('{{ $('Stage Context').item.json.search_profile_id }}')"),
     ('profile_version', 'number', "expr('{{ $('Stage Context').item.json.profile_version }}')"),
     ('run_id', 'string', "expr('{{ $('DB - Create Run Record').item.json.id }}')"),
     ('max_research', 'number', "expr('{{ $('Stage Context').item.json.max_research }}')"),
     ('min_fit', 'number', "expr('{{ $('Stage Context').item.json.research_min_fit }}')")], [3180, 260],
    {'success': True, 'researched': 0, 'facts_saved': 0, 'signals_saved': 0, 'people_saved': 0}))

out.append(execwf('callSf3', 'R9kXgJptTkzixYP8', 'SF3 - Find People (Open) v2',
    [('search_profile_id', 'string', "expr('{{ $('Stage Context').item.json.search_profile_id }}')"),
     ('profile_version', 'number', "expr('{{ $('Stage Context').item.json.profile_version }}')"),
     ('run_id', 'string', "expr('{{ $('DB - Create Run Record').item.json.id }}')"),
     ('max_companies', 'number', "expr('{{ $('Stage Context').item.json.max_people_companies }}')"),
     ('min_fit', 'number', "expr('{{ $('Stage Context').item.json.people_min_fit }}')")], [3420, 260],
    {'success': True, 'companies_processed': 0, 'people_extracted': 0, 'people_saved': 0}))
out.append(execwf('callSf9', 'QoiR3M1Slbckih0O', 'SF9 - Timing Re-Score',
    [('search_profile_id', 'string', "expr('{{ $('Stage Context').item.json.search_profile_id }}')"),
     ('profile_version', 'number', "expr('{{ $('Stage Context').item.json.profile_version }}')"),
     ('run_id', 'string', "expr('{{ $('DB - Create Run Record').item.json.id }}')")], [3660, 260],
    {'success': True, 'rescored': 0, 'with_timing': 0}))
out.append(execwf('callSf8', '64tf9AdGtFoqs1Tl', 'SF8 - Approval View Sync',
    [('search_profile_id', 'string', "expr('{{ $('Stage Context').item.json.search_profile_id }}')"),
     ('profile_version', 'number', "expr('{{ $('Stage Context').item.json.profile_version }}')")], [3900, 260],
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
      options: {{ queryReplacement: expr('{{{{ [ $(\'Glue - To SF7\').item.json.run_id, \\'SF2 found \\' + $(\'Glue - To SF4\').item.json.discovered + \\'; SF4 inserted \\' + $('Glue - To SF7').item.json.dedupe.inserted + \\' (dup \\' + $('Glue - To SF7').item.json.dedupe.duplicates + \\', suppressed \\' + $('Glue - To SF7').item.json.dedupe.suppressed + \\'); SF7 scored \\' + $(\'SF7 - Score Leads\').item.json.scored + \\'; SF5 researched \\' + $(\'SF5 - Research Leads\').item.json.researched + \\' ; SF3 people searched \\' + $(\'SF3 - Find People (Open) v2\').item.json.companies_processed + \\' companies, saved \\' + $(\'SF3 - Find People (Open) v2\').item.json.people_saved + \\' people; SF9 timing rescored \\' + $(\'SF9 - Timing Re-Score\').item.json.rescored + \\' (\\' + $(\'SF9 - Timing Re-Score\').item.json.with_timing + \\' with timing); SF8 approval view published \\' + $(\'SF8 - Approval View Sync\').item.json.published + \\' rows\\' ] }}}}') }}
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
out.append("""
export default workflow('leadfinder-wf00-full', 'WF00 - Lead Finder Orchestrator')
  .add(aboutNote)
  .add(startTrigger)
  .to(contextNode)
  .to(hasExisting
    .onTrue(useExisting.to(stageCtx.to(createRun).to(loadStatus).to(approvedGate
      .onTrue(callSf2.to(glue4).to(callSf4).to(glue7).to(callSf7).to(callSf5).to(callSf3).to(callSf9).to(callSf8).to(closeRun).to(summaryNode))
      .onFalse(markAwaiting.to(awaitReturn))
    )))
    .onFalse(callSf1.to(stageCtx))
  );""")

code = '\n'.join(out) + '\n'
(BASE/'wf00-v7.ts').write_text(code)
json.dump({"code": code}, open(BASE/'validate-wf00-v7.json','w'))
json.dump({"code": code, "name": "WF00 - Lead Finder Orchestrator"}, open(BASE/'create-wf00-v7.json','w'))
print('written', len(code))
