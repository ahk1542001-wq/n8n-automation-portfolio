import json, pathlib
BASE = pathlib.Path('pathlib.Path(__file__).resolve().parent/sf8')
def J(s): return json.dumps(s)
DOC = '1dF2mdjUFc6D0jFTvhxbby6DJxWo4T6Fw0UrWEHI20JM'  # v-next Sheet COPY (F32) - never the live approval sheet
FIELDS = ['run_id','company_id','Company','Category','Location','Website','Phone','Facebook','Email','Size','Rating','Reviews','Fit','Timing','Band']

# ---------------- SF8 v-next publish (F32) ----------------
out = []
out.append("import { workflow, node, trigger, sticky, expr, ifElse } from '@n8n/workflow-sdk';")
out.append(f"const aboutNote = sticky({J('SF8 v-next.5 - Approval View Sync (F32 + SF6 contacts + Yangon-first + People tab). Publishes ranked scored leads into the v-next Sheet COPY keyed by run_id + company_id, now with Phone/Facebook/Email/Size columns (SF6), ordered Yangon -> Mandalay -> Bangkok -> other (city from the Places record), then a People tab with the decision-makers (name, position, LinkedIn, phone, email) for the published companies. Header gate: run_id, company_id, Decision, Note must exist on the copy or zero rows are written and a Gmail draft names the missing header. Decision and Note columns are never written. insufficient_data rows show as Unknown - insufficient data (F31).')}, [], {{ color: 5 }});")
out.append("""
const subTrigger = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger',
  version: 1.1,
  config: {
    name: 'When Executed by Another Workflow',
    parameters: {
      workflowInputs: { values: [
        { name: 'search_profile_id', type: 'string' },
        { name: 'profile_version', type: 'number' },
        { name: 'run_id', type: 'string' },
        { name: 'approval_sheet_id_vnext', type: 'string' },
        { name: 'publish_limit', type: 'number' }
      ] }
    },
    position: [40, 400]
  },
  output: [{ search_profile_id: 'uuid', profile_version: 1, run_id: 'run', approval_sheet_id_vnext: '', publish_limit: 200 }]
});""")
QUERY = """
SELECT $3::text AS run_id, c.id::text AS company_id, c.name AS "Company", c.category AS "Category", c.location AS "Location",
       c.website AS "Website", CASE WHEN c.phone IS NULL OR c.phone = '' THEN '' ELSE '''' || c.phone END AS "Phone", c.facebook_url AS "Facebook", c.email AS "Email", c.company_size AS "Size",
       c.rating AS "Rating", c.review_count AS "Reviews",
       s.fit_score AS "Fit", s.timing_score AS "Timing",
       CASE WHEN s.band = 'insufficient_data' THEN 'Unknown — insufficient data' ELSE s.band END AS "Band"
FROM companies c
JOIN scores s ON s.company_id = c.id AND s.search_profile_id = $1::uuid AND s.profile_version = $2
WHERE ($3 = '' OR c.run_id::text = $3)
ORDER BY CASE
           WHEN COALESCE(c.raw_payload->>'city', '') ILIKE '%yangon%' OR c.location ILIKE '%yangon%' THEN 0
           WHEN COALESCE(c.raw_payload->>'city', '') ILIKE '%mandalay%' OR c.location ILIKE '%mandalay%' THEN 1
           WHEN COALESCE(c.raw_payload->>'city', '') ILIKE '%bangkok%' OR c.location ILIKE '%bangkok%' OR COALESCE(c.raw_payload->>'state', '') ILIKE '%bangkok%' THEN 2
           ELSE 3
         END,
         s.fit_score DESC
LIMIT (CASE WHEN $4 > 0 THEN $4 ELSE 200 END)
""".strip()
out.append(f"""
const pgNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Ranked Leads',
    position: [320, 400],
    parameters: {{
      operation: 'executeQuery',
      query: {J(QUERY)},
      options: {{ queryReplacement: expr('{{{{ [ $(\\'When Executed by Another Workflow\\').item.json.search_profile_id, $(\\'When Executed by Another Workflow\\').item.json.profile_version || 1, $(\\'When Executed by Another Workflow\\').item.json.run_id || \\'\\', $(\\'When Executed by Another Workflow\\').item.json.publish_limit || 200 ] }}}}') }}
    }}
  }},
  output: [{{ run_id: 'run', company_id: 'uuid', Company: 'Shop', Fit: 50 }}]
}});""")
out.append(f"""
const readExistingNode = node({{
  type: 'n8n-nodes-base.googleSheets',
  version: 4.2,
  config: {{
    name: 'Sheet - Read Existing (F32)',
    alwaysOutputData: true,
    position: [600, 400],
    parameters: {{
      resource: 'sheet',
      operation: 'read',
      documentId: {{ __rl: true, mode: 'id', value: {J(DOC)}, cachedResultName: 'Lead Finder - Approval View (v-next F32)' }},
      sheetName: {{ __rl: true, mode: 'name', value: 'Lead Review', cachedResultName: 'Lead Review' }},
      options: {{}}
    }}
  }},
  output: [{{ run_id: 'run', company_id: 'uuid', Decision: '' }}]
}});""")
KEYMAP_JS = r"""
const REQUIRED = ['run_id', 'company_id', 'Decision', 'Note'];
const sheetRows = $input.all().map(i => i.json);
const headerSet = new Set();
for (const r of sheetRows) for (const k of Object.keys(r)) headerSet.add(k);
const missing = headerSet.size ? REQUIRED.filter(h => !headerSet.has(h)) : [];
if (missing.length) {
  return [{ json: { header_error: missing[0], missing_headers: missing, success: false } }];
}
const byKey = new Map();
for (const r of sheetRows) {
  if (r.run_id && r.company_id) byKey.set(String(r.run_id) + '|' + String(r.company_id), r);
}
const leads = $('DB - Ranked Leads').all().map(i => i.json);
const out = [];
let preserved = 0;
for (const lead of leads) {
  const key = String(lead.run_id || '') + '|' + String(lead.company_id || '');
  const existing = byKey.get(key);
  const hasDecision = !!(existing && String(existing.Decision || '').trim());
  if (hasDecision) preserved++;
  out.push({ json: { ...lead, _key: key, _preserved_decision: hasDecision, header_error: '' } });
}
if (!out.length) out.push({ json: { header_error: '', _empty: true, run_id: '', company_id: '' } });
for (const o of out) o.json._preserved_total = preserved;
return out;
""".strip()
out.append(f"""
const keyMapNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Key Map + Validate (F32)',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(KEYMAP_JS)} }},
    position: [880, 400]
  }},
  output: [{{ run_id: 'run', company_id: 'uuid', header_error: '' }}]
}});""")
out.append("""
const headerGate = ifElse({
  type: 'n8n-nodes-base.if',
  version: 2.2,
  config: {
    name: 'Header OK?',
    position: [1160, 400],
    parameters: {
      conditions: {
        options: { caseSensitive: true, leftValue: '', typeValidation: 'loose' },
        conditions: [{ id: 'herr', leftValue: expr("{{ $json.header_error }}"), rightValue: '', operator: { type: 'string', operation: 'empty', singleValue: true } }],
        combinator: 'and'
      },
      options: {}
    }
  }
});""")
cols_value = ", ".join(f"{f}: expr('{{{{ $json.{f} }}}}')" for f in FIELDS)
schema = ", ".join("{ id: '%s', displayName: '%s', required: false, defaultMatch: false, display: true, type: 'string', canBeUsedToMatch: true }" % (f, f) for f in FIELDS)
out.append(f"""
const sheetNode = node({{
  type: 'n8n-nodes-base.googleSheets',
  version: 4.2,
  config: {{
    name: 'Sheet - Publish Ranked Leads',
    position: [1440, 320],
    parameters: {{
      resource: 'sheet',
      operation: 'appendOrUpdate',
      documentId: {{ __rl: true, mode: 'id', value: {J(DOC)}, cachedResultName: 'Lead Finder - Approval View (v-next F32)' }},
      sheetName: {{ __rl: true, mode: 'name', value: 'Lead Review', cachedResultName: 'Lead Review' }},
      columns: {{
        mappingMode: 'defineBelow',
        value: {{ {cols_value} }},
        matchingColumns: ['run_id', 'company_id'],
        schema: [ {schema} ]
      }},
      options: {{}}
    }}
  }},
  output: [{{}}]
}});""")
ERRDRAFT_JS = r"""
const km = $('Key Map + Validate (F32)').first().json;
return [{ json: { subject: 'SF8 v-next header error - missing header: ' + (km.header_error || ''), text: 'SF8 v-next (F32) refused to write to the v-next approval Sheet copy.\nMissing/renamed header: ' + (km.header_error || '') + '\nAll missing: ' + JSON.stringify(km.missing_headers || []) + '\nZero rows were written. Rename the header back to continue.' } }];
""".strip()
out.append(f"""
const errDraftNode = node({{
  type: 'n8n-nodes-base.gmail',
  version: 2.1,
  config: {{
    name: 'Gmail - Header Error Draft (F32)',
    position: [1440, 560],
    parameters: {{
      resource: 'draft',
      operation: 'create',
      subject: expr('{{{{ $json.subject }}}}'),
      emailType: 'text',
      message: expr('{{{{ $json.text }}}}'),
      options: {{}}
    }}
  }},
  output: [{{ id: 'draft' }}]
}});""")
out.append(f"""
const errPrepNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Prep Header Error',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(ERRDRAFT_JS)} }},
    position: [1300, 560]
  }},
  output: [{{ subject: 'x', text: 'y' }}]
}});""")
RET_JS = r"""
const km = $('Key Map + Validate (F32)').all();
const preserved = km.length ? (km[0].json._preserved_total || 0) : 0;
const published = km.filter(i => !i.json._empty).length;
return [{ json: { success: true, published, preserved_decisions: preserved } }];
""".strip()
out.append(f"""
const retNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Return',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(RET_JS)} }},
    position: [2140, 320]
  }},
  output: [{{ success: true, published: 0, preserved_decisions: 0 }}]
}});""")
RET_ERR_JS = "const km = $('Key Map + Validate (F32)').first().json; return [{ json: { success: false, header_error: km.header_error || '', published: 0 } }];"
out.append(f"""
const retErrNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Return - Header Error',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(RET_ERR_JS)} }},
    position: [1720, 560]
  }},
  output: [{{ success: false, header_error: '' }}]
}});""")

PEOPLE_SQL = """
SELECT c.id::text AS company_id, c.name AS "Company", p.full_name AS "Person", p.title AS "Position",
       p.linkedin_url AS "LinkedIn", CASE WHEN p.phone IS NULL OR p.phone = '' THEN '' ELSE '''' || p.phone END AS "Phone", p.email AS "Email"
FROM people p
JOIN companies c ON c.id = p.company_id
JOIN scores s ON s.company_id = c.id AND s.search_profile_id = $1::uuid AND s.profile_version = $2
WHERE ($3 = '' OR c.run_id::text = $3)
ORDER BY s.fit_score DESC
LIMIT (CASE WHEN $4 > 0 THEN $4 ELSE 200 END)
""".strip()
out.append(f"""
const peopleDbNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - People for Published',
    executeOnce: true,
    position: [1580, 320],
    parameters: {{
      operation: 'executeQuery',
      query: {J(PEOPLE_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $(\\'When Executed by Another Workflow\\').first().json.search_profile_id, $(\\'When Executed by Another Workflow\\').first().json.profile_version || 1, $(\\'When Executed by Another Workflow\\').first().json.run_id || \\'\\', $(\\'When Executed by Another Workflow\\').first().json.publish_limit || 200 ] }}}}') }}
    }},
    credentials: {{ postgres: newCredential('Postgres') }}
  }},
  output: [{{ company_id: 'uuid', Person: 'Name' }}]
}});""")
PFIELDS = ['company_id','Company','Person','Position','LinkedIn','Phone','Email']
pcols_value = ", ".join(f"{f}: expr('{{{{ $json.{f} }}}}')" for f in PFIELDS)
pschema = ", ".join("{ id: '%s', displayName: '%s', required: false, defaultMatch: false, display: true, type: 'string', canBeUsedToMatch: true }" % (f, f) for f in PFIELDS)
out.append(f"""
const peopleSheetNode = node({{
  type: 'n8n-nodes-base.googleSheets',
  version: 4.2,
  config: {{
    name: 'Sheet - Publish People',
    position: [1860, 320],
    parameters: {{
      resource: 'sheet',
      operation: 'appendOrUpdate',
      documentId: {{ __rl: true, mode: 'id', value: {J(DOC)}, cachedResultName: 'Lead Finder - Approval View (v-next F32)' }},
      sheetName: {{ __rl: true, mode: 'name', value: 'People', cachedResultName: 'People' }},
      columns: {{
        mappingMode: 'defineBelow',
        value: {{ {pcols_value} }},
        matchingColumns: ['company_id', 'Person'],
        schema: [ {pschema} ]
      }},
      options: {{}}
    }},
    credentials: {{ googleSheetsOAuth2Api: newCredential('Google Sheets') }}
  }},
  output: [{{}}]
}});""")

out.append("""
export default workflow('leadfinder-sf8-vnext5', 'SF8 v-next.5 - Approval View Sync (contacts + Yangon-first + People)')
  .add(aboutNote)
  .add(subTrigger)
  .to(pgNode)
  .to(readExistingNode)
  .to(keyMapNode)
  .to(headerGate
    .onTrue(sheetNode.to(peopleDbNode).to(peopleSheetNode).to(retNode))
    .onFalse(errPrepNode.to(errDraftNode).to(retErrNode))
  );""")
code = '\n'.join(out) + '\n'
(BASE/'sf8-vnext5.ts').write_text(code)
json.dump({"code": code, "name": "SF8 v-next.5 - Approval View Sync (contacts + Yangon-first + People)"}, open(BASE/'create-sf8-vnext5.json','w'))

