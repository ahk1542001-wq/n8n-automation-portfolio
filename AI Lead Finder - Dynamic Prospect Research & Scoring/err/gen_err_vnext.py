import json, pathlib
BASE = pathlib.Path(__file__).resolve().parent
def J(s): return json.dumps(s)

BUILD_JS = r"""
const j = $input.first().json || {};
const exec = j.execution || {};
const err = (exec.error && exec.error.message) || (j.error && j.error.message) || 'unknown error';
const wf = (j.workflow && j.workflow.name) || 'unknown workflow';
const note = ('error handler v-next: ' + wf + ' failed at ' + (exec.lastNodeExecuted || 'unknown node') + ' - ' + String(err)).slice(0, 300);
return [{ json: { note } }];
""".strip()

MARK_SQL = """
UPDATE runs SET status = 'failed', finished_at = now(), notes = COALESCE(notes, '') || ' [' || $1 || ']'
WHERE status = 'started' AND started_at < now() - interval '1 hour'
RETURNING id
""".strip()

ALERT_JS = r"""
const rows = $input.all().map(i => i.json).filter(r => r.id);
const ids = rows.map(r => r.id);
const body = 'ERR v-next flipped ' + ids.length + ' stuck run(s) to failed:\n' + ids.join('\n');
return [{ json: { count: ids.length, sendTo: 'owner@example.com', subject: 'ERR v-next ALERT - stuck runs flipped', body } }];
""".strip()

RET_JS = r"""
return [{ json: { success: true } }];
""".strip()

out = []
out.append("import { workflow, node, trigger, sticky, expr, ifElse } from '@n8n/workflow-sdk';")
out.append(f"const aboutNote = sticky({J('ERR v-next (Wonder fix plan F6, 2026-11-16). Stuck-run sweeper: flips runs still at status started after 1 hour, with NO upper age bound (the old handler window abandoned runs older than 2h). Flipped runs get failed + note + a Gmail-draft alert. NOT attached to WF00 v8 yet - activation is a separate promotion decision. Sends nothing; the alert is a draft.')}, [], {{ color: 5 }});")
out.append("""
const errTrigger = trigger({
  type: 'n8n-nodes-base.errorTrigger',
  version: 1,
  config: { name: 'Error Trigger', position: [40, 400] },
  output: [{ execution: { id: '0', error: { message: 'boom' }, lastNodeExecuted: 'Some Node', mode: 'manual' }, workflow: { id: 'wf', name: 'WF00 - Lead Finder Orchestrator' } }]
});""")
out.append(f"""
const buildNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Build Failure Note',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(BUILD_JS)} }},
    position: [320, 400]
  }},
  output: [{{ note: 'error handler v-next: ...' }}]
}});""")
out.append(f"""
const markNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Mark Stuck Runs Failed (v-next)',
    position: [600, 400],
    parameters: {{
      operation: 'executeQuery',
      query: {J(MARK_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.note ] }}}}') }}
    }},
    credentials: {{ postgres: newCredential('Postgres') }}
  }},
  output: [{{ id: 'run-uuid' }}]
}});""")
out.append(f"""
const alertNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Build Alert',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(ALERT_JS)} }},
    position: [880, 400]
  }},
  output: [{{ count: 0, sendTo: 'owner@example.com', subject: 's', body: 'b' }}]
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
    position: [1160, 400]
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
    position: [1160, 640]
  }},
  output: [{{ success: true }}]
}});""")
out.append("""
const hasFlips = ifElse({
  version: 2.2,
  config: {
    name: 'Any Flipped?',
    position: [1020, 400],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ $json.count }}'), rightValue: 0, operator: { type: 'number', operation: 'larger' } }],
        combinator: 'and'
      }
    }
  }
});""")
out.append("""
export default workflow('leadfinder-err-vnext', 'ERR v-next - Lead Finder Run Failure Handler')
  .add(aboutNote)
  .add(errTrigger)
  .to(buildNode)
  .to(markNode)
  .to(alertNode)
  .to(hasFlips
    .onTrue(gmailDraft)
    .onFalse(retNode));""")
code = '\n'.join(out) + '\n'
(BASE/'err-vnext.ts').write_text(code)
json.dump({"code": code, "name": "ERR v-next - Lead Finder Run Failure Handler"}, open(BASE/'create-err-vnext.json', 'w'))
print('err v-next generated', len(code))
