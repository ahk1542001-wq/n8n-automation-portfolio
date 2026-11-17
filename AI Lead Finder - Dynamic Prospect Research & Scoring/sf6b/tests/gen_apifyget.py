import json, pathlib
BASE = pathlib.Path(__file__).resolve().parent
def J(s): return json.dumps(s)
DOC = ''
FMT_JS = r"""
const d = ($input.first().json || {}).data || {};
return [{ json: { line: 'apify run <apify-run-id>: status=' + String(d.status || '?') + ' usage_usd=' + String(d.usageTotalUsd || 0) + ' dataset=' + String(d.defaultDatasetId || '') } }];
""".strip()
out = []
out.append("import { workflow, node, trigger } from '@n8n/workflow-sdk';")
out.append("""
const start = trigger({
  type: 'n8n-nodes-base.manualTrigger',
  version: 1,
  config: { name: 'Manual Trigger', position: [40, 400] },
  output: [{}]
});""")
out.append("""
const get = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {
    name: 'Apify - Get Run',
    position: [320, 400],
    parameters: {
      method: 'GET',
      url: 'https://api.apify.com/v2/actor-runs/<apify-run-id>',
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      options: { timeout: 30000 }
    },
    credentials: { httpHeaderAuth: newCredential('Header Auth account 2') }
  },
  output: [{ data: { status: 'SUCCEEDED' } }]
});""")
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
export default workflow('apifyget-orphan', 'APIFYGET - Orphan Run Usage')
  .add(start)
  .to(get)
  .to(fmt)
  .to(sheet);
""")
(BASE / 'apifyget.ts').write_text('\n'.join(out))
print('apifyget generated')
