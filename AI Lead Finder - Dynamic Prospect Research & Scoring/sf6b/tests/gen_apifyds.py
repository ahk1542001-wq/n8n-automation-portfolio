import json, pathlib
BASE = pathlib.Path(__file__).resolve().parent
def J(s): return json.dumps(s)
DOC = ''
EXTRACT_JS = r"""
const d = ($input.first().json || {}).data || {};
return [{ json: { dataset_id: String(d.id || ''), create_url: 'https://api.apify.com/v2/datasets/' + String(d.id || '') + '/items' } }];
""".strip()
FMT_JS = r"""
const stage = $('Extract Id').first().json;
return [{ json: { line: 'garbage dataset: ' + stage.dataset_id } }];
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
out.append("""
const create = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {
    name: 'Apify - Create Dataset',
    position: [320, 400],
    parameters: {
      method: 'POST',
      url: 'https://api.apify.com/v2/datasets',
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendBody: true,
      contentType: 'json',
      jsonBody: '={"name":"sf6b-schema-drift-test"}',
      options: { timeout: 30000 }
    },
    credentials: { httpHeaderAuth: newCredential('Header Auth account 2') }
  },
  output: [{ data: { id: 'x' } }]
});""")
out.append(f"""
const extract = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Extract Id',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(EXTRACT_JS)} }},
    position: [600, 400]
  }},
  output: [{{ dataset_id: 'x' }}]
}});""")
out.append("""
const push = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {
    name: 'Apify - Push Garbage Items',
    position: [880, 400],
    parameters: {
      method: 'POST',
      url: expr("{{ $json.create_url }}"),
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendBody: true,
      contentType: 'json',
      jsonBody: '=[{"foo":1},{"bar":"x"},{"baz":[1,2]}]',
      options: { timeout: 30000 }
    },
    credentials: { httpHeaderAuth: newCredential('Header Auth account 2') }
  },
  output: [{ ok: true }]
});""")
out.append(f"""
const fmt = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Format',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(FMT_JS)} }},
    position: [1160, 400]
  }},
  output: [{{ line: 'x' }}]
}});""")
out.append(f"""
const sheet = node({{
  type: 'n8n-nodes-base.googleSheets',
  version: 4.2,
  config: {{
    name: 'Sheets - ProbeLog',
    position: [1440, 400],
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
export default workflow('apifyds-garbage', 'APIFYDS - Garbage Dataset')
  .add(start)
  .to(create)
  .to(extract)
  .to(push)
  .to(fmt)
  .to(sheet);
""")
(BASE / 'apifyds.ts').write_text('\n'.join(out))
print('apifyds generated')
