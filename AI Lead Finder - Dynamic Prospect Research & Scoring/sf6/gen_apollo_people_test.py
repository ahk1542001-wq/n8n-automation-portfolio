import json, pathlib
BASE = pathlib.Path(__file__).resolve().parent
def J(s): return json.dumps(s)

DOC = ''  # approval-view spreadsheet id (deployment-specific)

DOMAINS_JS = r"""
return [
  { json: { domain: 'shopify.com' } },
  { json: { domain: 'grab.com' } },
  { json: { domain: 'agoda.com' } }
];
""".strip()

FORMAT_JS = r"""
const domains = $('Domains').all().map(i => i.json.domain);
return $input.all().map((item, idx) => {
  const j = item.json || {};
  const domain = domains[idx] || '';
  const people = j.people || j.contacts || [];
  const total = (j.pagination && j.pagination.total_entries !== undefined) ? j.pagination.total_entries : '';
  let note = '';
  if (j.error || j.message) note = String(j.error || j.message).slice(0, 300);
  const lines = people.slice(0, 5).map(p => {
    const name = ((p.first_name || '') + ' ' + (p.last_name || p.last_name_obfuscated || '')).trim();
    return [name, p.title || '', p.seniority || '', p.linkedin_url ? 'li:yes' : 'li:no', p.email_status || (p.has_email ? 'has_email' : '')].join(' | ');
  });
  const keys = people.length ? Object.keys(people[0]).join(',') : '';
  return { json: { domain, total_entries: total, returned: people.length, sample: lines.join('\n'), person_keys: keys.slice(0, 900), note } };
});
""".strip()

COLS = ['domain', 'total_entries', 'returned', 'sample', 'person_keys', 'note']
value_map = ', '.join(f"{c}: expr('{{{{ $json.{c} }}}}')" for c in COLS)
schema = ', '.join("{ id: '%s', displayName: '%s', required: false, defaultMatch: false, display: true, type: 'string', canBeUsedToMatch: true }" % (c, c) for c in COLS)

out = []
out.append("import { workflow, node, trigger, sticky, expr } from '@n8n/workflow-sdk';")
out.append(f"const aboutNote = sticky({J('TEST - Apollo People Search capability probe (2026-11-17). Manual trigger -> 3 known domains -> Apollo mixed_people/search (search ONLY, no email reveal, no credits spent on reveal) -> summary rows to the ApolloTest tab of the v-next Sheet copy. Archive when done.')}, [], {{ color: 7 }});")
out.append("""
const manualTrigger = trigger({
  type: 'n8n-nodes-base.manualTrigger',
  version: 1,
  config: { name: 'Manual Trigger', position: [40, 300] },
  output: [{}]
});""")
out.append(f"""
const domainsNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Domains',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(DOMAINS_JS)} }},
    position: [320, 300]
  }},
  output: [{{ domain: 'shopify.com' }}]
}});""")
out.append("""
const apolloPeople = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {
    name: 'Apollo - People Search',
    onError: 'continueRegularOutput',
    position: [600, 300],
    parameters: {
      method: 'POST',
      url: 'https://api.apollo.io/api/v1/mixed_people/search',
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendBody: true,
      contentType: 'json',
      specifyBody: 'json',
      jsonBody: expr('{{ JSON.stringify({ organization_domains: [$json.domain], person_seniorities: ["owner", "founder", "partner", "cxo", "vp"], page: 1, per_page: 10 }) }}'),
      options: { timeout: 30000 }
    },
    credentials: { httpHeaderAuth: newCredential('Apollo') }
  },
  output: [{ people: [] }]
});""")
out.append(f"""
const fmtNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Format Results',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(FORMAT_JS)} }},
    position: [880, 300]
  }},
  output: [{{ domain: 'x', total_entries: 0, returned: 0, sample: '', person_keys: '', note: '' }}]
}});""")
out.append(f"""
const sheetNode = node({{
  type: 'n8n-nodes-base.googleSheets',
  version: 4.2,
  config: {{
    name: 'Sheet - ApolloTest',
    position: [1160, 300],
    parameters: {{
      resource: 'sheet',
      operation: 'appendOrUpdate',
      documentId: {{ __rl: true, mode: 'id', value: {J(DOC)}, cachedResultName: 'Lead Finder - Approval View (v-next F32)' }},
      sheetName: {{ __rl: true, mode: 'name', value: 'ApolloTest', cachedResultName: 'ApolloTest' }},
      columns: {{
        mappingMode: 'defineBelow',
        value: {{ {value_map} }},
        matchingColumns: ['domain'],
        schema: [ {schema} ]
      }},
      options: {{}}
    }},
    credentials: {{ googleSheetsOAuth2Api: newCredential('Google Sheets') }}
  }},
  output: [{{}}]
}});""")
out.append("""
export default workflow('test-apollo-people-search', 'TEST - Apollo People Search')
  .add(aboutNote)
  .add(manualTrigger)
  .to(domainsNode)
  .to(apolloPeople)
  .to(fmtNode)
  .to(sheetNode);""")
code = '\n'.join(out) + '\n'
(BASE/'apollo-people-test.ts').write_text(code)
json.dump({"code": code, "name": "TEST - Apollo People Search"}, open(BASE/'create-apollo-people-test.json', 'w'))
print('generated', len(code))
