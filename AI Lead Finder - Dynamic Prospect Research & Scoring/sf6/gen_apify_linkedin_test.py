import json, pathlib
BASE = pathlib.Path(__file__).resolve().parent
def J(s): return json.dumps(s)

DOC = ''  # approval-view spreadsheet id (deployment-specific)
ACTOR_URL = 'https://api.apify.com/v2/acts/santamaria-automations~linkedin-company-scraper/run-sync-get-dataset-items?memory=1024'

INPUT_JS = r"""
const input = {
  companies: [
    { company_id: 'test-shopify', company_name: 'Shopify', linkedin_url: 'https://www.linkedin.com/company/shopify' },
    { company_id: 'test-grab', company_name: 'Grab', linkedin_url: 'https://www.linkedin.com/company/grabapp' },
    { company_id: 'test-ritholtz', company_name: 'Ritholtz Wealth Management', website_domain: 'ritholtz.com' }
  ],
  includeEmployees: true,
  maxEmployeesPerCompany: 10
};
return [{ json: { apify_input: input } }];
""".strip()

FORMAT_JS = r"""
return $input.all().map(item => {
  const j = item.json || {};
  const emps = Array.isArray(j.employees) ? j.employees : [];
  const lines = emps.map(e => [e.name || '', e.title || e.headline || '', e.linkedin_url || e.profile_url || e.url || ''].join(' | '));
  return { json: {
    company_id: String(j.company_id || ''),
    company_name: String(j.company_name || ''),
    employees_found: emps.length,
    sample: lines.join('\n').slice(0, 1500),
    note: ('range=' + (j.employee_count_range || '') + ' error=' + (j.error || '') + ' keys=' + Object.keys(j).join(',')).slice(0, 900)
  } };
});
""".strip()

COLS = ['company_id', 'company_name', 'employees_found', 'sample', 'note']
value_map = ', '.join(f"{c}: expr('{{{{ $json.{c} }}}}')" for c in COLS)
schema = ', '.join("{ id: '%s', displayName: '%s', required: false, defaultMatch: false, display: true, type: 'string', canBeUsedToMatch: true }" % (c, c) for c in COLS)

out = []
out.append("import { workflow, node, trigger, sticky, expr } from '@n8n/workflow-sdk';")
out.append(f"const aboutNote = sticky({J('TEST - Apify LinkedIn company employees probe (2026-11-17). Manual trigger -> santamaria-automations/linkedin-company-scraper (public guest pages, NO LinkedIn login) for 3 test companies with includeEmployees -> summary rows to the ApifyTest tab of the v-next Sheet copy. Archive when done.')}, [], {{ color: 7 }});")
out.append("""
const manualTrigger = trigger({
  type: 'n8n-nodes-base.manualTrigger',
  version: 1,
  config: { name: 'Manual Trigger', position: [40, 300] },
  output: [{}]
});""")
out.append(f"""
const inputNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Build Input',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(INPUT_JS)} }},
    position: [320, 300]
  }},
  output: [{{ apify_input: {{}} }}]
}});""")
out.append(f"""
const apifyNode = node({{
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {{
    name: 'Apify - LinkedIn Company',
    onError: 'continueRegularOutput',
    position: [600, 300],
    parameters: {{
      method: 'POST',
      url: {J(ACTOR_URL)},
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendBody: true,
      contentType: 'json',
      specifyBody: 'json',
      jsonBody: expr('{{{{ $json.apify_input }}}}'),
      options: {{ timeout: 300000 }}
    }},
    credentials: {{ httpHeaderAuth: newCredential('Apify') }}
  }},
  output: [{{ company_id: 'x', employees: [] }}]
}});""")
out.append(f"""
const fmtNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Format Results',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(FORMAT_JS)} }},
    position: [880, 300]
  }},
  output: [{{ company_id: 'x', company_name: '', employees_found: 0, sample: '', note: '' }}]
}});""")
out.append(f"""
const sheetNode = node({{
  type: 'n8n-nodes-base.googleSheets',
  version: 4.2,
  config: {{
    name: 'Sheet - ApifyTest',
    position: [1160, 300],
    parameters: {{
      resource: 'sheet',
      operation: 'appendOrUpdate',
      documentId: {{ __rl: true, mode: 'id', value: {J(DOC)}, cachedResultName: 'Lead Finder - Approval View (v-next F32)' }},
      sheetName: {{ __rl: true, mode: 'name', value: 'ApifyTest', cachedResultName: 'ApifyTest' }},
      columns: {{
        mappingMode: 'defineBelow',
        value: {{ {value_map} }},
        matchingColumns: ['company_id'],
        schema: [ {schema} ]
      }},
      options: {{}}
    }},
    credentials: {{ googleSheetsOAuth2Api: newCredential('Google Sheets') }}
  }},
  output: [{{}}]
}});""")
out.append("""
export default workflow('test-apify-linkedin-people', 'TEST - Apify LinkedIn People')
  .add(aboutNote)
  .add(manualTrigger)
  .to(inputNode)
  .to(apifyNode)
  .to(fmtNode)
  .to(sheetNode);""")
code = '\n'.join(out) + '\n'
(BASE/'apify-linkedin-test.ts').write_text(code)
json.dump({"code": code, "name": "TEST - Apify LinkedIn People"}, open(BASE/'create-apify-linkedin-test.json', 'w'))
print('generated', len(code))
