import json, pathlib
BASE = pathlib.Path(__file__).resolve().parent
def J(s): return json.dumps(s)

# F30: weights normalised from the legacy set (30/25/25/25/10/10/5, sum 130) to sum exactly 100.
# normalised_i = round(legacy_i / 130 * 100, 2); residual (0.00 here) would go to the largest weight.
DEFAULT_WEIGHTS = {"funding": 23.08, "hiring": 19.23, "job_change": 19.23, "expansion": 19.23, "new_post": 7.69, "review_activity": 7.69, "other": 3.85}

TIMING_SQL = """
WITH cfg AS (
  SELECT profile->'timing_weights' AS w
  FROM search_profiles WHERE id = $1::uuid AND version = $2
),
wchk AS (
  SELECT
    CASE WHEN w IS NOT NULL AND jsonb_typeof(w) = 'object'
      AND ABS(COALESCE((SELECT sum(v::numeric) FROM jsonb_each_text(w) e(k, v) WHERE k IN ('funding','hiring','job_change','expansion','new_post','review_activity','other') AND v ~ '^-?[0-9]+(\.[0-9]+)?$'), -1) - 100) <= 0.01
    THEN w ELSE $3::jsonb END AS w,
    CASE WHEN w IS NOT NULL AND jsonb_typeof(w) = 'object'
      AND ABS(COALESCE((SELECT sum(v::numeric) FROM jsonb_each_text(w) e(k, v) WHERE k IN ('funding','hiring','job_change','expansion','new_post','review_activity','other') AND v ~ '^-?[0-9]+(\.[0-9]+)?$'), -1) - 100) <= 0.01
    THEN false ELSE (w IS NOT NULL) END AS invalid
  FROM cfg
),
sig AS (
  SELECT s.company_id,
         count(*) FILTER (WHERE s.signal_type = 'funding') AS n_funding,
         count(*) FILTER (WHERE s.signal_type = 'hiring') AS n_hiring,
         count(*) FILTER (WHERE s.signal_type = 'job_change') AS n_job_change,
         count(*) FILTER (WHERE s.signal_type = 'expansion') AS n_expansion,
         count(*) FILTER (WHERE s.signal_type = 'new_post') AS n_new_post,
         count(*) FILTER (WHERE s.signal_type = 'review_activity') AS n_review_activity,
         count(*) FILTER (WHERE s.signal_type NOT IN ('funding','hiring','job_change','expansion','new_post','review_activity')) AS n_other,
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
         ROUND(LEAST(100, COALESCE(
             sig.n_funding * (wchk.w->>'funding')::numeric
           + sig.n_hiring * (wchk.w->>'hiring')::numeric
           + sig.n_job_change * (wchk.w->>'job_change')::numeric
           + sig.n_expansion * (wchk.w->>'expansion')::numeric
           + sig.n_new_post * (wchk.w->>'new_post')::numeric
           + sig.n_review_activity * (wchk.w->>'review_activity')::numeric
           + sig.n_other * (wchk.w->>'other')::numeric, 0)))::int AS t,
         jsonb_build_object(
           'signals_live', COALESCE(sig.n, 0),
           'weights', wchk.w,
           'weights_status', 'unvalidated_default',
           'timing_weights_invalid', wchk.invalid,
           'signals', COALESCE(sig.items, '[]'::jsonb),
           'computed_at', now()) AS comp
  FROM base CROSS JOIN wchk LEFT JOIN sig ON sig.company_id = base.company_id
),
upd AS (
  UPDATE scores sc SET timing_score = calc.t, timing_components = calc.comp
  FROM calc WHERE sc.id = calc.id
  RETURNING sc.timing_score
)
SELECT (SELECT count(*) FROM upd) AS rescored,
       (SELECT count(*) FROM upd WHERE timing_score > 0) AS with_timing,
       (SELECT invalid FROM wchk) AS timing_weights_invalid,
       'unvalidated_default' AS timing_weights_status
""".strip()

RET_JS = r"""
const r = $input.first().json || {};
return [{ json: { success: true, rescored: Number(r.rescored) || 0, with_timing: Number(r.with_timing) || 0, timing_weights_status: r.timing_weights_status || 'unvalidated_default', timing_weights_invalid: !!r.timing_weights_invalid } }];
""".strip()

out = []
out.append("import { workflow, node, trigger, sticky, expr } from '@n8n/workflow-sdk';")
out.append(f"const aboutNote = sticky({J('SF9 v-next - Timing Re-Score (F30). Weights normalised to sum exactly 100 (funding 23.08, hiring 19.23, job_change 19.23, expansion 19.23, new_post 7.69, review_activity 7.69, other 3.85 — from the legacy 30/25/25/25/10/10/5 set, sum 130) and profile-configurable via profile.timing_weights (validated: must sum to 100 +/- 0.01, else defaults + timing_weights_invalid flag). Score = min(100, sum of live-signal counts x weights), rounded. Every output carries timing_weights_status=unvalidated_default — the weights are NOT validated against outcomes. Legacy SF9 untouched.')}, [], {{ color: 5 }});")
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
const prepNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Prep Params',
    position: [320, 400],
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J("const j = $input.first().json; return [{ json: { search_profile_id: j.search_profile_id, profile_version: j.profile_version || 1, default_weights: " + J(json.dumps(DEFAULT_WEIGHTS)) + " } }];")} }}
  }},
  output: [{{ search_profile_id: 'uuid', profile_version: 1, default_weights: '{{}}' }}]
}});""")
out.append(f"""
const timingNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Recompute Timing (v-next)',
    position: [600, 400],
    parameters: {{
      operation: 'executeQuery',
      query: {J(TIMING_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.search_profile_id, $json.profile_version || 1, $json.default_weights ] }}}}') }}
    }},
    credentials: {{ postgres: newCredential('Postgres') }}
  }},
  output: [{{ rescored: 0, with_timing: 0, timing_weights_invalid: false, timing_weights_status: 'unvalidated_default' }}]
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
  output: [{{ success: true, rescored: 0, with_timing: 0, timing_weights_status: 'unvalidated_default', timing_weights_invalid: false }}]
}});""")
out.append("""
export default workflow('leadfinder-sf9-vnext', 'SF9 v-next - Timing Re-Score')
  .add(aboutNote)
  .add(subTrigger)
  .to(prepNode)
  .to(timingNode)
  .to(retNode);""")
code = '\n'.join(out) + '\n'
(BASE/'sf9-vnext.ts').write_text(code)
json.dump({"code": code, "name": "SF9 v-next - Timing Re-Score"}, open(BASE/'create-sf9-vnext.json', 'w'))
print('sf9 v-next generated', len(code))
