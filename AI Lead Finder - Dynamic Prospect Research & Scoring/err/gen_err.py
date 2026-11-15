import json, pathlib
BASE = pathlib.Path(__file__).resolve().parent
BASE.mkdir(parents=True, exist_ok=True)
def J(s): return json.dumps(s)

BUILD_JS = r"""
const j = $input.first().json || {};
const exec = j.execution || {};
const err = (exec.error && exec.error.message) || (j.error && j.error.message) || 'unknown error';
const wf = (j.workflow && j.workflow.name) || 'unknown workflow';
const note = ('error handler: ' + wf + ' failed at ' + (exec.lastNodeExecuted || 'unknown node') + ' - ' + String(err)).slice(0, 300);
return [{ json: { note } }];
""".strip()

MARK_SQL = """
UPDATE runs SET status = 'failed', finished_at = now(), notes = COALESCE(notes, '') || ' [' || $1 || ']'
WHERE status = 'started' AND started_at > now() - interval '2 hours'
RETURNING id
""".strip()

RET_JS = r"""
return [{ json: { success: true, marked_failed: $input.all().length } }];
""".strip()

out = []
out.append("import { workflow, node, trigger, sticky, expr } from '@n8n/workflow-sdk';")
out.append(f"const aboutNote = sticky({J('ERR - Lead Finder Run Failure Handler. Registered as the error workflow for WF00. When an orchestrated run dies mid-chain, n8n fires this handler: it marks any run still at status started (begun within the last 2 hours - the live run) as failed and appends the failing workflow, node and error message to the run notes. Single-orchestrator system: at most one run is live at a time, so the recent-started window identifies it. This handler only writes to the runs table; it sends nothing.')}, [], {{ color: 5 }});")
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
  output: [{{ note: 'error handler: ...' }}]
}});""")
out.append(f"""
const markNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Mark Stuck Runs Failed',
    position: [600, 400],
    parameters: {{
      operation: 'executeQuery',
      query: {J(MARK_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.note ] }}}}') }}
    }}
  }},
  output: [{{ id: 'run-uuid' }}]
}});""")
out.append(f"""
const retNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Return',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(RET_JS)} }},
    position: [880, 400]
  }},
  output: [{{ success: true, marked_failed: 0 }}]
}});""")
out.append("""
export default workflow('leadfinder-err', 'ERR - Lead Finder Run Failure Handler')
  .add(aboutNote)
  .add(errTrigger)
  .to(buildNode)
  .to(markNode)
  .to(retNode);""")
code = '\n'.join(out) + '\n'
(BASE/'err.ts').write_text(code)
json.dump({"code": code}, open(BASE/'validate-err.json','w'))
json.dump({"code": code, "name": "ERR - Lead Finder Run Failure Handler"}, open(BASE/'create-err.json','w'))
print('err generated', len(code))
