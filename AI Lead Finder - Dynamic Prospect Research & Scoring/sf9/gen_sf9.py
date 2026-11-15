import json, pathlib
BASE = pathlib.Path(__file__).resolve().parent
BASE.mkdir(parents=True, exist_ok=True)
def J(s): return json.dumps(s)

TIMING_SQL = """
WITH sig AS (
  SELECT s.company_id,
         SUM(CASE s.signal_type WHEN 'funding' THEN 30 WHEN 'hiring' THEN 25 WHEN 'job_change' THEN 25 WHEN 'expansion' THEN 25 WHEN 'new_post' THEN 10 WHEN 'review_activity' THEN 10 ELSE 5 END) AS raw,
         count(*) AS n,
         jsonb_agg(jsonb_build_object('type', s.signal_type, 'detail', s.detail, 'observed_at', s.observed_at) ORDER BY s.observed_at DESC) AS items
  FROM signals s
  WHERE s.observed_at > now() - (s.decay_days || ' days')::interval
  GROUP BY s.company_id
),
base AS (
  SELECT sc.id, sc.company_id FROM scores sc
  WHERE sc.search_profile_id = $1::uuid AND sc.profile_version = $2
),
calc AS (
  SELECT base.id,
         LEAST(100, COALESCE(sig.raw, 0)) AS t,
         jsonb_build_object('signals_live', COALESCE(sig.n, 0), 'points_raw', COALESCE(sig.raw, 0), 'signals', COALESCE(sig.items, '[]'::jsonb), 'computed_at', now()) AS comp
  FROM base LEFT JOIN sig ON sig.company_id = base.company_id
),
upd AS (
  UPDATE scores sc SET timing_score = calc.t, timing_components = calc.comp
  FROM calc WHERE sc.id = calc.id
  RETURNING sc.timing_score
)
SELECT count(*) AS rescored, count(*) FILTER (WHERE timing_score > 0) AS with_timing FROM upd
""".strip()

RET_JS = r"""
const r = $input.first().json || {};
return [{ json: { success: true, rescored: Number(r.rescored) || 0, with_timing: Number(r.with_timing) || 0 } }];
""".strip()

out = []
out.append("import { workflow, node, trigger, sticky, expr } from '@n8n/workflow-sdk';")
out.append(f"const aboutNote = sticky({J('SF9 - Timing Re-Score. Deterministic timing pass: recomputes timing_score for EVERY scored company of a profile from its live signals (observed inside each signals own decay window). Points: funding 30, hiring 25, job_change 25, expansion 25, new_post 10, review_activity 10, other 5; capped at 100. Companies with no live signals return to 0, so expired signals decay away on the next pass. Components are stored as JSON for audit. No LLM, no spend.')}, [], {{ color: 5 }});")
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
        { name: 'run_id', type: 'string' }
      ] }
    },
    position: [40, 400]
  },
  output: [{ search_profile_id: 'uuid', profile_version: 1, run_id: '' }]
});""")
out.append(f"""
const timingNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Recompute Timing',
    position: [320, 400],
    parameters: {{
      operation: 'executeQuery',
      query: {J(TIMING_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.search_profile_id, $json.profile_version || 1 ] }}}}') }}
    }}
  }},
  output: [{{ rescored: 0, with_timing: 0 }}]
}});""")
out.append(f"""
const retNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Return',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(RET_JS)} }},
    position: [600, 400]
  }},
  output: [{{ success: true, rescored: 0, with_timing: 0 }}]
}});""")
out.append("""
export default workflow('leadfinder-sf9', 'SF9 - Timing Re-Score')
  .add(aboutNote)
  .add(subTrigger)
  .to(timingNode)
  .to(retNode);""")
code = '\n'.join(out) + '\n'
(BASE/'sf9.ts').write_text(code)
json.dump({"code": code}, open(BASE/'validate-sf9.json','w'))
json.dump({"code": code, "name": "SF9 - Timing Re-Score"}, open(BASE/'create-sf9.json','w'))
print('sf9 generated', len(code))
