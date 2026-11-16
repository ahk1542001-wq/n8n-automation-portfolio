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
WITH ev AS (
  UPDATE runs SET status = 'failed', finished_at = now(), notes = COALESCE(notes, '') || ' [' || $1 || ' | event-flip]'
  WHERE status = 'started' AND started_at > now() - interval '1 hour' AND config_snapshot->>'orchestrator' = 'wf00-vnext'
  RETURNING id
), sw AS (
  UPDATE runs SET status = 'failed', finished_at = now(), notes = COALESCE(notes, '') || ' [' || $1 || ' | sweep]'
  WHERE status = 'started' AND started_at < now() - interval '1 hour'
  RETURNING id
)
SELECT id FROM ev UNION ALL SELECT id FROM sw
""".strip()

ALERT_JS = r"""
const rows = $input.all().map(i => i.json).filter(r => r.id);
const ids = rows.map(r => r.id);
const body = 'ERR v-next.2 flipped ' + ids.length + ' stuck run(s) to failed:\n' + ids.join('\n');
return [{ json: { count: ids.length, has_flips: ids.length > 0, sendTo: 'owner@example.com', subject: 'ERR v-next.2 ALERT - runs flipped (event + sweep)', body } }];
""".strip()

RET_JS = r"""
return [{ json: { success: true } }];
""".strip()

out = []
out.append("import { workflow, node, trigger, sticky, expr, ifElse } from '@n8n/workflow-sdk';")
out.append(f"const aboutNote = sticky({J('ERR v-next.2 (D12 combined error rule, Wonder FINAL VERIFY fix, 2026-11-16). On an error event from WF00 v-next: (a) EVENT FLIP - fresh runs of the v-next orchestrator (config_snapshot orchestrator = wf00-vnext) stuck under 1 hour flip to failed immediately; (b) SWEEP - any run still started after 1 hour flips, NO upper age bound. Together an errored run flips at any age. Known residual: a concurrent healthy v-next run inside the fresh window can be flipped by the event half (same semantics the old v8 handler had). Flips get failed + note + a Gmail-draft alert. Sends nothing.')}, [], {{ color: 5 }});")
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
    name: 'DB - Mark Runs Failed (v-next.2 combined)',
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
        conditions: [{ leftValue: expr('{{ $json.has_flips }}'), operator: { type: 'boolean', operation: 'true' } }],
        combinator: 'and'
      }
    }
  }
});""")
out.append("""
export default workflow('leadfinder-err-vnext2', 'ERR v-next.2 - Lead Finder Run Failure Handler (D12)')
  .add(aboutNote)
  .add(errTrigger)
  .to(buildNode)
  .to(markNode)
  .to(alertNode)
  .to(hasFlips
    .onTrue(gmailDraft)
    .onFalse(retNode));""")
code = '\n'.join(out) + '\n'
(BASE/'err-vnext2.ts').write_text(code)
json.dump({"code": code, "name": "ERR v-next.2 - Lead Finder Run Failure Handler (D12)"}, open(BASE/'create-err-vnext2.json', 'w'))
print('err v-next.2 generated', len(code))
