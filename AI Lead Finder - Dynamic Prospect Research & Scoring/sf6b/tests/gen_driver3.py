import json, pathlib
BASE = pathlib.Path(__file__).resolve().parent
def J(s): return json.dumps(s)
DOC = ''
BATCH = [{"company_id": "f9000000-0000-4000-8000-0000000000d4", "name": "Shopify", "slug": "shopify", "linkedin_url": "https://www.linkedin.com/company/shopify", "distinctive_tokens": ["shopify"]}]
SEED_JS = "return [{ json: {\n  apify_run_id: '<apify-run-id>',\n  dataset_id: '<dataset-id>',\n  run_id: 'f9000000-0000-4000-8000-000000000009',\n  batch_json: " + J(json.dumps(BATCH)) + ",\n  dm_titles_json: " + J(json.dumps(["CEO", "General Manager", "Founder", "Owner"])) + ",\n  profile_version: 1,\n  mtd_apify_usd: 0,\n  picked_count: 1\n} }];"
FMT_JS = r"""
const items = $input.all().map(i => i.json);
return [{ json: { line: 'SF6C driver3 summary: ' + items.map(x => JSON.stringify(x)).join(' | ') } }];
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
out.append("""
const call = node({
  type: 'n8n-nodes-base.executeWorkflow',
  version: 1.2,
  config: {
    name: 'Call SF6c',
    parameters: {
      source: 'database',
      workflowId: { __rl: true, value: 'PLACEHOLDER', mode: 'list', cachedResultName: 'SF6c' },
      mode: 'once',
      options: { waitForSubWorkflow: true },
      workflowInputs: { mappingMode: 'passthrough' }
    },
    position: [600, 400]
  },
  output: [{ success: true }]
});""")
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
export default workflow('driver3-sf6c-tests', 'DRIVER3 - SF6c Tests')
  .add(start)
  .to(seed)
  .to(call)
  .to(fmt)
  .to(sheet);
""")
(BASE / 'driver3.ts').write_text('\n'.join(out))
print('driver3 generated')
