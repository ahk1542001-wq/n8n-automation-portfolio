import json, pathlib
BASE = pathlib.Path('pathlib.Path(__file__).resolve().parent/err')
def J(s): return json.dumps(s)

ANON_SQL = """
UPDATE people
SET full_name = 'ANONYMISED', linkedin_url = NULL, email = NULL, email_status = NULL, raw_payload = NULL
WHERE retention_until IS NOT NULL AND retention_until < now() AND full_name <> 'ANONYMISED'
RETURNING id
""".strip()

ALERT_JS = r"""
const rows = $input.all().map(i => i.json).filter(r => r.id);
const body = 'RETENTION v-next (F21, mode=anonymise): ' + rows.length + ' people row(s) passed their retention date and were anonymised (name, LinkedIn, email and raw payload cleared; company link, title and evidence kept).\nIDs: ' + rows.map(r => r.id).join(', ');
return [{ json: { count: rows.length, has_due: rows.length > 0, sendTo: 'owner@example.com', subject: 'RETENTION v-next - people rows anonymised', body } }];
""".strip()

RET_JS = r"""
return [{ json: { success: true, anonymised: 0 } }];
""".strip()

out = []
out.append("import { workflow, node, trigger, sticky, expr, ifElse } from '@n8n/workflow-sdk';")
out.append(f"const aboutNote = sticky({J('RETENTION v-next (F21, 2026-11-16). Implements the F14 privacy decision (owner-approved 2026-11-16): people data basis = legitimate interest, B2B public sources only; retention = 12 months from fetch/creation (people.retention_until). CONFIG mode = anonymise: due rows get full_name tombstoned to ANONYMISED (column is NOT NULL) and lose linkedin_url, email, email_status, raw_payload; company link, title and evidence quote stay for aggregate reporting. Runs monthly (1st, 03:00 Bangkok); manual test runs use the editor execute or a pinned test run. Alert is a Gmail DRAFT only - this workflow never sends. No person data is ever written to any Sheet by this workflow.')}, [], {{ color: 5 }});")
out.append("""
const schedTrigger = trigger({
  type: 'n8n-nodes-base.scheduleTrigger',
  version: 1.2,
  config: { name: 'Monthly (1st, 03:00)', position: [40, 300], parameters: { rule: { interval: [{ field: 'months', monthsInterval: 1, triggerAtDay: 1, triggerAtHour: 3, triggerAtMinute: 0 }] } } },
  output: [{}]
});""")

out.append(f"""
const anonNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Anonymise Due People (F21)',
    position: [320, 400],
    parameters: {{
      operation: 'executeQuery',
      query: {J(ANON_SQL)},
      options: {{}}
    }},
    credentials: {{ postgres: newCredential('Postgres') }}
  }},
  output: [{{ id: 'person-uuid' }}]
}});""")
out.append(f"""
const alertNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Build Alert',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(ALERT_JS)} }},
    position: [600, 400]
  }},
  output: [{{ count: 0, has_due: false, sendTo: 'owner@example.com', subject: 's', body: 'b' }}]
}});""")
out.append("""
const gmailDraft = node({
  type: 'n8n-nodes-base.gmail',
  version: 2.1,
  config: {
    name: 'Gmail - Alert Draft (NEVER SENDS)',
    parameters: {
      resource: 'draft',
      operation: 'create',
      sendTo: expr('{{ $json.sendTo }}'),
      subject: expr('{{ $json.subject }}'),
      emailType: 'text',
      message: expr('{{ $json.body }}'),
      options: {}
    },
    credentials: { gmailOAuth2: newCredential('Gmail') },
    position: [880, 320]
  },
  output: [{ id: 'draft-id' }]
});""")
out.append(f"""
const retNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Return',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(RET_JS)} }},
    position: [880, 520]
  }},
  output: [{{ success: true, anonymised: 0 }}]
}});""")
out.append("""
const hasDue = ifElse({
  version: 2.2,
  config: {
    name: 'Any Due?',
    position: [760, 400],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ $json.has_due }}'), operator: { type: 'boolean', operation: 'true' } }],
        combinator: 'and'
      }
    }
  }
});""")
out.append("""
export default workflow('leadfinder-retention-vnext', 'RETENTION v-next - People Data Retention (F21)')
  .add(aboutNote)
  .add(schedTrigger)
  .to(anonNode)
  .to(alertNode)
  .to(hasDue
    .onTrue(gmailDraft)
    .onFalse(retNode));""")
code = '\n'.join(out) + '\n'
(BASE/'retention-vnext.ts').write_text(code)
json.dump({"code": code, "name": "RETENTION v-next - People Data Retention (F21)"}, open(BASE/'create-retention-vnext.json', 'w'))
print('retention v-next generated', len(code))
