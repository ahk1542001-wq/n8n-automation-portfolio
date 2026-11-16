import json, pathlib
BASE = pathlib.Path(__file__).resolve().parent
def J(s): return json.dumps(s)
DOC = '1dF2mdjUFc6D0jFTvhxbby6DJxWo4T6Fw0UrWEHI20JM'  # v-next Sheet COPY (F32) - never the live approval sheet
FIELDS = ['run_id','company_id','Company','Category','Location','Website','Rating','Reviews','Fit','Timing','Band']

# ---------------- SF8 v-next publish (F32) ----------------
out = []
out.append("import { workflow, node, trigger, sticky, expr, ifElse } from '@n8n/workflow-sdk';")
out.append(f"const aboutNote = sticky({J('SF8 v-next - Approval View Sync (F32). Publishes ranked scored leads into the v-next Sheet COPY keyed by run_id + company_id. Header gate: run_id, company_id, Decision, Note must exist on the copy or zero rows are written and a Gmail draft names the missing header. Decision and Note columns are never written. insufficient_data rows show as Unknown - insufficient data (F31).')}, [], {{ color: 5 }});")
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
        { name: 'approval_sheet_id_vnext', type: 'string' }
      ] }
    },
    position: [40, 400]
  },
  output: [{ search_profile_id: 'uuid', profile_version: 1, run_id: 'run', approval_sheet_id_vnext: '' }]
});""")
QUERY = """
SELECT $3::text AS run_id, c.id::text AS company_id, c.name AS "Company", c.category AS "Category", c.location AS "Location",
       c.website AS "Website", c.rating AS "Rating", c.review_count AS "Reviews",
       s.fit_score AS "Fit", s.timing_score AS "Timing",
       CASE WHEN s.band = 'insufficient_data' THEN 'Unknown — insufficient data' ELSE s.band END AS "Band"
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
      options: {{ queryReplacement: expr('{{{{ [ $(\\'When Executed by Another Workflow\\').item.json.search_profile_id, $(\\'When Executed by Another Workflow\\').item.json.profile_version || 1, $(\\'When Executed by Another Workflow\\').item.json.run_id || \\'\\' ] }}}}') }}
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
    position: [1720, 320]
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
out.append("""
export default workflow('leadfinder-sf8-vnext', 'SF8 v-next - Approval View Sync (F32)')
  .add(aboutNote)
  .add(subTrigger)
  .to(pgNode)
  .to(readExistingNode)
  .to(keyMapNode)
  .to(headerGate
    .onTrue(sheetNode.to(retNode))
    .onFalse(errPrepNode.to(errDraftNode).to(retErrNode))
  );""")
code = '\n'.join(out) + '\n'
(BASE/'sf8-vnext.ts').write_text(code)
json.dump({"code": code, "name": "SF8 v-next - Approval View Sync (F32)"}, open(BASE/'create-sf8-vnext.json','w'))

# ---------------- SF8b v-next write-back (F32) ----------------
out = []
out.append("import { workflow, node, trigger, sticky, expr, ifElse } from '@n8n/workflow-sdk';")
out.append(f"const aboutNote = sticky({J('SF8b v-next - Approval Write-Back (F32). Reads the v-next Sheet COPY, validates the run_id/company_id/Decision/Note headers (missing header = zero writes + Gmail draft naming it), applies only rows whose run_id matches the expected run, keys decisions by run_id|company_id, and skips decisions already recorded with the same note (skipped_duplicate).')}, [], {{ color: 5 }});")
out.append("""
const subTrigger = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger',
  version: 1.1,
  config: {
    name: 'When Executed by Another Workflow',
    parameters: {
      workflowInputs: { values: [
        { name: 'decided_by', type: 'string' },
        { name: 'run_id', type: 'string' },
        { name: 'approval_sheet_id_vnext', type: 'string' }
      ] }
    },
    position: [40, 400]
  },
  output: [{ decided_by: 'sheet', run_id: 'run', approval_sheet_id_vnext: '' }]
});""")
out.append(f"""
const readNode = node({{
  type: 'n8n-nodes-base.googleSheets',
  version: 4.2,
  config: {{
    name: 'Sheet - Read Decisions',
    alwaysOutputData: true,
    position: [320, 400],
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
EXIST_SQL = "SELECT company_id::text AS company_id, decision, COALESCE(note, '') AS note FROM approvals"
out.append(f"""
const existNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Existing Approvals',
    position: [600, 400],
    parameters: {{
      operation: 'executeQuery',
      query: {J(EXIST_SQL)},
      options: {{}}
    }}
  }},
  output: [{{ company_id: 'uuid', decision: 'approved', note: '' }}]
}});""")
COLLECT_JS = r"""
const REQUIRED = ['run_id', 'company_id', 'Decision', 'Note'];
const rows = $('Sheet - Read Decisions').all().map(i => i.json);
const headerSet = new Set();
for (const r of rows) for (const k of Object.keys(r)) headerSet.add(k);
const missing = headerSet.size ? REQUIRED.filter(h => !headerSet.has(h)) : [];
const trig = $('When Executed by Another Workflow').item.json;
if (missing.length) {
  return [{ json: { header_error: missing[0], missing_headers: missing, payload: '[]', count: 0, skipped_duplicate: 0, stale_ignored: 0, decided_by: trig.decided_by || 'sheet:Lead Review (v-next)' } }];
}
const ok = { approved: 1, rejected: 1, hold: 1 };
const existing = new Set($('DB - Existing Approvals').all().map(i => {
  const j = i.json; return String(j.company_id) + '|' + String(j.decision) + '|' + String(j.note || '');
}));
const byKey = new Map();
let stale = 0;
for (const r of rows) {
  const d = String(r.Decision || '').trim().toLowerCase();
  if (!r.company_id || !ok[d]) continue;
  if (trig.run_id && String(r.run_id || '') !== String(trig.run_id)) { stale++; continue; }
  byKey.set(String(r.run_id || '') + '|' + String(r.company_id), { company_id: String(r.company_id), decision: d, note: String(r.Note || '') });
}
const fresh = [];
let skippedDup = 0;
for (const dec of byKey.values()) {
  if (existing.has(dec.company_id + '|' + dec.decision + '|' + dec.note)) skippedDup++;
  else fresh.push(dec);
}
return [{ json: { header_error: '', payload: JSON.stringify(fresh), count: fresh.length, skipped_duplicate: skippedDup, stale_ignored: stale, decided_by: trig.decided_by || 'sheet:Lead Review (v-next)' } }];
""".strip()
out.append(f"""
const collectNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Collect Decisions (F32)',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(COLLECT_JS)} }},
    position: [880, 400]
  }},
  output: [{{ payload: '[]', count: 0, skipped_duplicate: 0, stale_ignored: 0, decided_by: 'sheet', header_error: '' }}]
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
for var, nm, pos, sql in [('recNode','DB - Record Approvals', 1440, SQL1), ('applyNode','DB - Apply Status', 1720, SQL2)]:
    out.append(f"""
const {var} = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: {J(nm)},
    position: [{pos}, 320],
    parameters: {{
      operation: 'executeQuery',
      query: {J(sql)},
      options: {{ queryReplacement: expr('{{{{ [ $(\\'Collect Decisions (F32)\\').item.json.payload, $(\\'Collect Decisions (F32)\\').item.json.decided_by ] }}}}') }}
    }}
  }},
  output: [{{}}]
}});""")
ERRDRAFT_JS = r"""
const c = $('Collect Decisions (F32)').first().json;
return [{ json: { subject: 'SF8b v-next header error - missing header: ' + (c.header_error || ''), text: 'SF8b v-next (F32) refused to write back any decisions.\nMissing/renamed header: ' + (c.header_error || '') + '\nAll missing: ' + JSON.stringify(c.missing_headers || []) + '\nZero approvals were recorded. Rename the header back to continue.' } }];
""".strip()
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
out.append(f"""
const errDraftNode = node({{
  type: 'n8n-nodes-base.gmail',
  version: 2.1,
  config: {{
    name: 'Gmail - Header Error Draft (F32)',
    position: [1580, 560],
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
RET2_JS = r"""
const c = $('Collect Decisions (F32)').item.json;
const recorded = $('DB - Record Approvals').all().length;
return [{ json: { success: true, recorded, skipped_duplicate: c.skipped_duplicate || 0, stale_ignored: c.stale_ignored || 0, decisions_seen: (c.count || 0) + (c.skipped_duplicate || 0) } }];
""".strip()
out.append(f"""
const retNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Return',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(RET2_JS)} }},
    position: [2000, 320]
  }},
  output: [{{ success: true, recorded: 0, skipped_duplicate: 0, stale_ignored: 0 }}]
}});""")
RET_ERR_JS = "const c = $('Collect Decisions (F32)').first().json; return [{ json: { success: false, header_error: c.header_error || '', recorded: 0 } }];"
out.append(f"""
const retErrNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Return - Header Error',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(RET_ERR_JS)} }},
    position: [1860, 560]
  }},
  output: [{{ success: false, header_error: '' }}]
}});""")
out.append("""
export default workflow('leadfinder-sf8b-vnext', 'SF8b v-next - Approval Write-Back (F32)')
  .add(aboutNote)
  .add(subTrigger)
  .to(readNode)
  .to(existNode)
  .to(collectNode)
  .to(headerGate
    .onTrue(recNode.to(applyNode).to(retNode))
    .onFalse(errPrepNode.to(errDraftNode).to(retErrNode))
  );""")
code = '\n'.join(out) + '\n'
(BASE/'sf8b-vnext.ts').write_text(code)
json.dump({"code": code, "name": "SF8b v-next - Approval Write-Back (F32)"}, open(BASE/'create-sf8b-vnext.json','w'))
print('sf8 v-next + sf8b v-next generated')
