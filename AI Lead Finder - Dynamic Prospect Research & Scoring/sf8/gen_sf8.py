import json, pathlib
BASE = pathlib.Path(__file__).resolve().parent
def J(s): return json.dumps(s)
DOC = '1xikaoJRfWqVxPUxtUFn5bAx8EjjI2_53BvP09czHxc4'
FIELDS = ['company_id','Company','Category','Location','Website','Rating','Reviews','Fit','Timing','Band']

# ---------------- SF8 publish ----------------
out = []
out.append("import { workflow, node, trigger, sticky, expr } from '@n8n/workflow-sdk';")
out.append(f"const aboutNote = sticky({J('SF8 - Approval View Sync. Publishes the ranked scored leads for one search profile into the Google Sheet approval view (Lead Finder - Approval View / Lead Review tab) via appendOrUpdate on company_id. Only data columns are written - the Decision and Note columns belong to the human and are never overwritten.')}, [], {{ color: 5 }});")
out.append("""
const subTrigger = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger',
  version: 1.1,
  config: {
    name: 'When Executed by Another Workflow',
    parameters: {
      workflowInputs: { values: [
        { name: 'search_profile_id', type: 'string' },
        { name: 'profile_version', type: 'number' }
      ] }
    },
    position: [40, 400]
  },
  output: [{ search_profile_id: 'uuid', profile_version: 1 }]
});""")
QUERY = """
SELECT c.id::text AS company_id, c.name AS "Company", c.category AS "Category", c.location AS "Location",
       c.website AS "Website", c.rating AS "Rating", c.review_count AS "Reviews",
       s.fit_score AS "Fit", s.timing_score AS "Timing", s.band AS "Band"
FROM companies c
JOIN scores s ON s.company_id = c.id AND s.search_profile_id = $1::uuid AND s.profile_version = $2
ORDER BY s.fit_score DESC
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
      options: {{ queryReplacement: expr('{{{{ [ $(\'When Executed by Another Workflow\').item.json.search_profile_id, $(\'When Executed by Another Workflow\').item.json.profile_version || 1 ] }}}}') }}
    }}
  }},
  output: [{{ company_id: 'uuid', Company: 'Shop', Fit: 50 }}]
}});""")
cols_value = ", ".join(f"{f}: expr('{{{{ $json.{f} }}}}')" for f in FIELDS)
schema = ", ".join("{ id: '%s', displayName: '%s', required: false, defaultMatch: false, display: true, type: 'string', canBeUsedToMatch: true }" % (f, f) for f in FIELDS)
out.append(f"""
const sheetNode = node({{
  type: 'n8n-nodes-base.googleSheets',
  version: 4.2,
  config: {{
    name: 'Sheet - Publish Ranked Leads',
    position: [600, 400],
    parameters: {{
      resource: 'sheet',
      operation: 'appendOrUpdate',
      documentId: {{ __rl: true, mode: 'id', value: {J(DOC)}, cachedResultName: 'Lead Finder - Approval View' }},
      sheetName: {{ __rl: true, mode: 'name', value: 'Lead Review', cachedResultName: 'Lead Review' }},
      columns: {{
        mappingMode: 'defineBelow',
        value: {{ {cols_value} }},
        matchingColumns: ['company_id'],
        schema: [ {schema} ]
      }},
      options: {{}}
    }}
  }},
  output: [{{}}]
}});""")
RET_JS = "return [{ json: { success: true, published: $input.all().length } }];"
out.append(f"""
const retNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Return',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(RET_JS)} }},
    position: [880, 400]
  }},
  output: [{{ success: true, published: 0 }}]
}});""")
out.append("""
export default workflow('leadfinder-sf8', 'SF8 - Approval View Sync')
  .add(aboutNote)
  .add(subTrigger)
  .to(pgNode)
  .to(sheetNode)
  .to(retNode);""")
code = '\n'.join(out) + '\n'
(BASE/'sf8.ts').write_text(code)
json.dump({"code": code}, open(BASE/'validate-sf8.json','w'))
json.dump({"code": code, "name": "SF8 - Approval View Sync"}, open(BASE/'create-sf8.json','w'))

# ---------------- SF8b write-back ----------------
out = []
out.append("import { workflow, node, trigger, sticky, expr } from '@n8n/workflow-sdk';")
out.append(f"const aboutNote = sticky({J('SF8b - Approval Write-Back. Reads the Lead Review sheet, records every human Decision (approved/rejected/hold) into the approvals table (idempotent - same decision never recorded twice) and applies approved/rejected to the company status. The sheet stays the human view; Postgres stays the truth.')}, [], {{ color: 5 }});")
out.append("""
const subTrigger = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger',
  version: 1.1,
  config: {
    name: 'When Executed by Another Workflow',
    parameters: {
      workflowInputs: { values: [
        { name: 'decided_by', type: 'string' }
      ] }
    },
    position: [40, 400]
  },
  output: [{ decided_by: 'sheet' }]
});""")
out.append(f"""
const readNode = node({{
  type: 'n8n-nodes-base.googleSheets',
  version: 4.2,
  config: {{
    name: 'Sheet - Read Decisions',
    position: [320, 400],
    parameters: {{
      resource: 'sheet',
      operation: 'read',
      documentId: {{ __rl: true, mode: 'id', value: {J(DOC)}, cachedResultName: 'Lead Finder - Approval View' }},
      sheetName: {{ __rl: true, mode: 'name', value: 'Lead Review', cachedResultName: 'Lead Review' }},
      options: {{}}
    }}
  }},
  output: [{{ company_id: 'uuid', Decision: '' }}]
}});""")
COLLECT_JS = r"""
const rows = $input.all().map(i => i.json);
const ok = { approved: 1, rejected: 1, hold: 1 };
const decisions = [];
for (const r of rows) {
  const d = String(r.Decision || '').trim().toLowerCase();
  if (r.company_id && ok[d]) decisions.push({ company_id: r.company_id, decision: d, note: String(r.Note || '') });
}
const decidedBy = ($('When Executed by Another Workflow').item.json.decided_by) || 'sheet:Lead Review';
return [{ json: { payload: JSON.stringify(decisions), count: decisions.length, decided_by: decidedBy } }];
""".strip()
out.append(f"""
const collectNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Collect Decisions',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(COLLECT_JS)} }},
    position: [600, 400]
  }},
  output: [{{ payload: '[]', count: 0, decided_by: 'sheet' }}]
}});""")
SQL1 = """
WITH items AS (SELECT x FROM jsonb_array_elements($1::jsonb) AS x)
INSERT INTO approvals (company_id, decision, decided_by, note)
SELECT (x->>'company_id')::uuid, x->>'decision', $2, NULLIF(x->>'note','')
FROM items x
WHERE NOT EXISTS (SELECT 1 FROM approvals a WHERE a.company_id = (x->>'company_id')::uuid AND a.decision = x->>'decision')
RETURNING company_id
""".strip()
SQL2 = """
WITH items AS (SELECT x FROM jsonb_array_elements($1::jsonb) AS x)
UPDATE companies c
SET status = CASE WHEN x->>'decision' = 'approved' THEN 'approved' WHEN x->>'decision' = 'rejected' THEN 'rejected' ELSE c.status END
FROM items x
WHERE c.id = (x->>'company_id')::uuid AND x->>'decision' IN ('approved','rejected')
RETURNING c.id
""".strip()
for var, nm, pos, sql in [('recNode','DB - Record Approvals', 880, SQL1), ('applyNode','DB - Apply Status', 1160, SQL2)]:
    out.append(f"""
const {var} = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: {J(nm)},
    position: [{pos}, 400],
    parameters: {{
      operation: 'executeQuery',
      query: {J(sql)},
      options: {{ queryReplacement: expr('{{{{ [ $(\'Collect Decisions\').item.json.payload, $(\'Collect Decisions\').item.json.decided_by ] }}}}') }}
    }}
  }},
  output: [{{}}]
}});""")
RET2_JS = "const c = $('Collect Decisions').item.json; return [{ json: { success: true, decisions_seen: c.count } }];"
out.append(f"""
const retNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Return',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(RET2_JS)} }},
    position: [1440, 400]
  }},
  output: [{{ success: true, decisions_seen: 0 }}]
}});""")
out.append("""
export default workflow('leadfinder-sf8b', 'SF8b - Approval Write-Back')
  .add(aboutNote)
  .add(subTrigger)
  .to(readNode)
  .to(collectNode)
  .to(recNode)
  .to(applyNode)
  .to(retNode);""")
code = '\n'.join(out) + '\n'
(BASE/'sf8b.ts').write_text(code)
json.dump({"code": code}, open(BASE/'validate-sf8b.json','w'))
json.dump({"code": code, "name": "SF8b - Approval Write-Back"}, open(BASE/'create-sf8b.json','w'))
print('sf8 + sf8b generated')
