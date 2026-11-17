import json, pathlib
BASE = pathlib.Path(__file__).resolve().parent
def J(s): return json.dumps(s)
DOC = ''
SEED_JS = r"""
return [{ json: {
  search_profile_id: 'f9000000-0000-4000-8000-000000000001',
  profile_version: 1,
  run_id: 'f9000000-0000-4000-8000-000000000008',
  linkedin_min_fit: 30,
  max_linkedin_companies: 5,
  spend_cap_usd: 1.00,
  max_employees: 3,
  linkedin_people_enabled: true
} }];
""".strip()
FMT_JS = r"""
const items = $input.all().map(i => i.json);
return [{ json: { line: 'SF6B driver2 summary: ' + items.map(x => JSON.stringify(x)).join(' | ') } }];
""".strip()
out = []
out.append("import { workflow, node, trigger, expr } from '@n8n/workflow-sdk';")
out.append("""
const start = trigger({
  type: 'n8n-nodes-base.manualTrigger',
  version: 1,
  config: { name: 'Manual Trigger', position: [40, 400] },
  output: [{}]
});""")
out.append(f"""
const seed = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Seed Inputs',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(SEED_JS)} }},
    position: [320, 400]
  }},
  output: [{{ run_id: 'x' }}]
}});""")
out.append(f"""
const call = node({{
  type: 'n8n-nodes-base.executeWorkflow',
  version: 1.2,
  config: {{
    name: 'Call SF6b',
    parameters: {{
      source: 'database',
      workflowId: {{ __rl: true, value: 'PLACEHOLDER', mode: 'list', cachedResultName: 'SF6b' }},
      mode: 'once',
      options: {{ waitForSubWorkflow: true }},
      workflowInputs: {{ mappingMode: 'passthrough' }}
    }},
    position: [600, 400]
  }},
  output: [{{ success: true }}]
}});""")
out.append(f"""
const fmt = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Format',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(FMT_JS)} }},
    position: [880, 400]
  }},
  output: [{{ line: 'x' }}]
}});""")
out.append(f"""
const sheet = node({{
  type: 'n8n-nodes-base.googleSheets',
  version: 4.2,
  config: {{
    name: 'Sheets - ProbeLog',
    position: [1160, 400],
    parameters: {{
      resource: 'sheet',
      operation: 'append',
      documentId: {{ __rl: true, mode: 'id', value: {J(DOC)}, cachedResultName: 'Lead Finder - Approval View (v-next F32)' }},
      sheetName: {{ __rl: true, mode: 'name', value: 'ProbeLog', cachedResultName: 'ProbeLog' }},
      columns: {{ mappingMode: 'defineBelow', value: {{ line: "={{{{ $json.line }}}}" }}, matchingColumns: [], schema: [{{ id: 'line', displayName: 'line', required: false, defaultMatch: false, display: true, type: 'string', canBeUsedToMatch: true }}] }},
      options: {{}}
    }},
    credentials: {{ googleSheetsOAuth2Api: newCredential('Google Sheets') }}
  }},
  output: [{{ line: 'x' }}]
}});""")
out.append("""
export default workflow('driver2-sf6b-tests', 'DRIVER2 - SF6b Tests')
  .add(start)
  .to(seed)
  .to(call)
  .to(fmt)
  .to(sheet);
""")
(BASE / 'driver2.ts').write_text('\n'.join(out))
print('driver2 generated')
