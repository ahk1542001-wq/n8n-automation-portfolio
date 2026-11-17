import json, pathlib
BASE = pathlib.Path(__file__).resolve().parent
def J(s): return json.dumps(s)
DOC = ''
FMT_JS = "return $input.all().map(i => ({ json: { line: String((i.json && i.json.line) || JSON.stringify(i.json)) } }));"
out = []
out.append("import { workflow, node, trigger } from '@n8n/workflow-sdk';")
out.append("""
const start = trigger({
  type: 'n8n-nodes-base.manualTrigger',
  version: 1,
  config: { name: 'Manual Trigger', position: [40, 400] },
  output: [{}]
});""")
out.append(f"""
const probe = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Probe',
    position: [320, 400],
    parameters: {{ operation: 'executeQuery', query: 'SELECT 1 AS line', options: {{}} }},
    credentials: {{ postgres: newCredential('Postgres') }}
  }},
  output: [{{ line: 'x' }}]
}});""")
out.append(f"""
const fmt = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Format',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(FMT_JS)} }},
    position: [600, 400]
  }},
  output: [{{ line: 'x' }}]
}});""")
out.append(f"""
const sheet = node({{
  type: 'n8n-nodes-base.googleSheets',
  version: 4.2,
  config: {{
    name: 'Sheets - ProbeLog',
    position: [880, 400],
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
export default workflow('probe2-sf6b-tests', 'PROBE2 - SF6b Tests')
  .add(start)
  .to(probe)
  .to(fmt)
  .to(sheet);
""")
(BASE / 'probe2.ts').write_text('\n'.join(out))
print('probe2 generated')
