import json, pathlib
BASE = pathlib.Path('pathlib.Path(__file__).resolve().parent/sf6')
def J(s): return json.dumps(s)

# ---------- SQL (module-level constants; $ params via queryReplacement) ----------
SPENT_SQL = "SELECT COALESCE(SUM(cost_usd), 0)::float AS spent_usd FROM cost_ledger WHERE run_id = $1"

PICK_SQL = """
WITH cand AS (
  SELECT c.id, c.name, c.location, c.website, c.phone, s.fit_score,
         ROW_NUMBER() OVER (ORDER BY s.fit_score DESC, c.id ASC) AS rn
  FROM companies c
  JOIN scores s ON s.company_id = c.id
    AND s.search_profile_id = $1 AND s.profile_version = $2
  WHERE s.fit_score >= $3
    AND c.contact_enriched_at IS NULL
    AND (c.contact_claimed_at IS NULL OR c.contact_claimed_at < now() - interval '1 hour')
),
audit AS (
  INSERT INTO selection_audit (run_id, workflow, company_id, rank, fit_score, cutoff, selection_reason, is_first_skipped)
  SELECT $5, 'SF6', id::text, rn::int, fit_score, $3,
         CASE WHEN rn <= $4 THEN 'selected' ELSE 'cap_reached' END,
         (rn = $4 + 1)
  FROM cand WHERE rn <= $4 + 1
  ON CONFLICT DO NOTHING
  RETURNING 1
),
claim AS (
  UPDATE companies c
  SET contact_claimed_at = now(), contact_claim_run_id = $5
  FROM cand
  WHERE c.id = cand.id AND cand.rn <= $4
  RETURNING c.id AS company_id, cand.name, cand.location, cand.website, cand.phone, cand.fit_score AS fit
)
SELECT company_id::text AS company_id, name, location, website, phone, fit, false AS empty_run FROM claim
UNION ALL
SELECT NULL, NULL, NULL, NULL, NULL, NULL, true AS empty_run
WHERE NOT EXISTS (SELECT 1 FROM claim)
""".strip()

CAP_LEDGER_SQL = """
INSERT INTO cost_ledger (run_id, workflow, provider, event_type, units, cost_usd, company_id, idempotency_key)
VALUES ($1, 'SF6', 'tavily', 'cap_blocked', 1, 0.016, $2, 'sf6:cap:' || $1 || ':' || $2)
ON CONFLICT (idempotency_key) DO NOTHING
""".strip()

SAVE_SQL = """
WITH u AS (
  UPDATE companies SET
    facebook_url = COALESCE(NULLIF($3, ''), facebook_url),
    email = COALESCE(NULLIF($4, ''), email),
    email_source = CASE WHEN NULLIF($4, '') IS NOT NULL THEN 'website' ELSE email_source END,
    company_size = COALESCE(NULLIF($5, ''), company_size),
    size_source = CASE WHEN NULLIF($5, '') IS NOT NULL THEN 'website' ELSE size_source END,
    contact_enriched_at = now()
  WHERE id = $1 AND contact_claim_run_id = $2
  RETURNING id
),
l1 AS (
  INSERT INTO cost_ledger (run_id, workflow, provider, event_type, units, cost_usd, company_id, idempotency_key)
  VALUES ($2, 'SF6', 'tavily', 'charge', 1, 0.008, $1::text, 'sf6:search:' || $2 || ':' || $1::text)
  ON CONFLICT (idempotency_key) DO NOTHING
  RETURNING 1
),
l2 AS (
  INSERT INTO cost_ledger (run_id, workflow, provider, event_type, units, cost_usd, company_id, idempotency_key)
  SELECT $2, 'SF6', 'tavily', 'charge', 1, 0.008, $1::text, 'sf6:extract:' || $2 || ':' || $1::text
  WHERE $6
  ON CONFLICT (idempotency_key) DO NOTHING
  RETURNING 1
)
SELECT (SELECT count(*) FROM u)::int AS updated
""".strip()

# ---------- JS (module-level constants) ----------
STAGE_JS = r"""
const t = $('When Executed by Another Workflow').first().json;
const spent = Number($input.first().json.spent_usd || 0);
return [{ json: {
  search_profile_id: t.search_profile_id,
  profile_version: Number(t.profile_version || 1),
  run_id: t.run_id || '',
  contact_min_fit: Number(t.contact_min_fit ?? 30),
  max_contact_companies: Number(t.max_contact_companies ?? 10),
  spend_cap_usd: (t.spend_cap_usd === undefined || t.spend_cap_usd === null || t.spend_cap_usd === '') ? null : Number(t.spend_cap_usd),
  provider_enabled: t.provider_enabled === true,
  spent_usd: spent
} }];
""".strip()

CAPGATE_JS = r"""
const ctx = $('Stage Context').first().json;
const rows = $input.all().map(i => i.json);
const picked = rows.filter(r => !r.empty_run);
const EST_PER_COMPANY = 0.016;
const cap = ctx.spend_cap_usd;
const blocked = cap !== null && picked.length > 0 && (ctx.spent_usd + EST_PER_COMPANY) > cap;
if (!picked.length) {
  return [{ json: { has_work: false, empty_run: true, cap_blocked: false, picked: 0, run_id: ctx.run_id } }];
}
return picked.map(r => ({ json: Object.assign({}, r, {
  has_work: !blocked, cap_blocked: blocked, empty_run: false,
  run_id: ctx.run_id, search_profile_id: ctx.search_profile_id,
  profile_version: ctx.profile_version, provider_enabled: ctx.provider_enabled
}) }));
""".strip()

BUILD_JS = r"""
function contactUrl(w) {
  const base = String(w).replace(/\/+$/, '');
  return base + '/contact';
}
return $input.all().map(i => {
  const j = i.json;
  const website = j.website || '';
  const urls = website ? [website, contactUrl(website)] : [];
  return { json: Object.assign({}, j, {
    has_website: !!website,
    mcp_fb: JSON.stringify({ query: '"' + j.name + '" ' + (j.location || '') + ' facebook', search_depth: 'basic', max_results: 5 }),
    mcp_extract: JSON.stringify({ urls: urls, extract_depth: 'basic' })
  }) };
});
""".strip()

REATTACH_A_JS = r"""
const jobs = $('Build Jobs').all().map(i => i.json);
return $input.all().map((item, idx) => {
  const job = jobs[idx] || {};
  let t = '';
  try { t = typeof item.json === 'string' ? item.json : JSON.stringify(item.json); } catch (e) { t = String(item.json); }
  return { json: Object.assign({}, job, { fb_text: t }) };
});
""".strip()

REATTACH_B_JS = r"""
const prev = $('Reattach A').all().map(i => i.json);
return $input.all().map((item, idx) => {
  const p = prev[idx] || {};
  let t = '';
  const j = item.json || {};
  if (!j.error && !j.message) {
    try { t = typeof j === 'string' ? j : JSON.stringify(j); } catch (e) { t = String(j); }
  }
  return { json: Object.assign({}, p, { extract_text: t, extract_attempted: !!p.has_website }) };
});
""".strip()

PARSE_JS = r"""
const STOPWORDS = new Set(['the','and','co','ltd','company','store','shop','hotel','resort','bangkok','yangon','thailand','myanmar','facebook','page','official']);
function normTokens(s) {
  return String(s || '').toLowerCase().replace(/[^\p{L}\p{N}\s]/gu, ' ').split(/\s+/).filter(w => w.length >= 3 && !STOPWORDS.has(w));
}
const GENERIC = new Set(['training','service','services','mobile','phone','computer','electronics','hardware','fashion','trading','enterprise','enterprises','solution','solutions','technology','technologies','digital','media','express','global','international','modern','center','centre','group','beauty','star','king','best','top','world','accessories','garment','textile','food','travel','tour','tours','clinic','school','academy','studio','salon','cafe','restaurant','bakery','pharmacy','mart','market','online']);
function pickFacebook(companyName, results) {
  const nameToks = new Set(normTokens(companyName));
  if (!nameToks.size || !Array.isArray(results)) return null;
  for (const r of results) {
    const url = String((r && r.url) || '');
    const m = url.match(/^https?:\/\/(?:www\.)?facebook\.com\/([^/?#]+)/i);
    if (!m) continue;
    const slug = decodeURIComponent(m[1]);
    if (['sharer','login','help','groups','watch','marketplace','gaming','profile.php'].includes(slug.toLowerCase())) continue;
    const candToks = new Set([...normTokens(slug.replace(/[-_.]/g, ' ')), ...normTokens(r.title || '')]);
    const matched = [];
    for (const t of nameToks) { if (candToks.has(t)) matched.push(t); }
    const slugFlat = slug.toLowerCase().replace(/[^a-z0-9]/g, '');
    for (const t of nameToks) { if (!matched.includes(t) && t.length >= 4 && slugFlat.includes(t)) matched.push(t); }
    const distinctive = matched.filter(t => !GENERIC.has(t));
    if (distinctive.length >= 1 || matched.length >= 2) {
      return { facebook_url: 'https://www.facebook.com/' + slug, matched_token: distinctive[0] || matched[0] };
    }
  }
  return null;
}
function pickFacebookFromText(companyName, text) {
  if (!text) return null;
  const urls = String(text).match(/https?:\/\/(?:www\.)?facebook\.com\/[A-Za-z0-9_.\-%]+/gi) || [];
  return pickFacebook(companyName, urls.map(u => ({ url: u, title: '' })));
}
const EMAIL_RE = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
function pickEmail(text) {
  if (!text) return null;
  const found = String(text).match(EMAIL_RE) || [];
  for (const e of found) {
    if (/^(noreply|no-reply|donotreply|mailer-daemon|postmaster)@/i.test(e)) continue;
    if (/\.(png|jpe?g|gif|svg|webp|css|js)$/i.test(e)) continue;
    if (/example\.(com|org|net)$/i.test(e)) continue;
    if (/^(your|user|name|email)@/i.test(e)) continue;
    return e;
  }
  return null;
}
function pickSize(text) {
  if (!text) return null;
  const s = String(text);
  let m = s.match(/(\d{1,4})\s*(?:\+\s*)?(employees|staff members|team members)/i);
  if (m) return m[1] + ' ' + m[2].toLowerCase();
  m = s.match(/team of\s*(\d{1,4})/i);
  if (m) return m[1] + ' team members';
  m = s.match(/(\d{1,4})\s*(?:\+\s*)?(rooms|guest rooms)/i);
  if (m) return m[1] + ' ' + m[2].toLowerCase();
  return null;
}
function searchResults(text) {
  try {
    const outer = JSON.parse(text);
    const inner = typeof outer === 'string' ? JSON.parse(outer) : outer;
    if (inner && Array.isArray(inner.results)) return inner.results;
    if (inner && inner.content) {
      const c = typeof inner.content === 'string' ? JSON.parse(inner.content) : inner.content;
      if (c && Array.isArray(c.results)) return c.results;
    }
  } catch (e) {}
  return null;
}
return $input.all().map(i => {
  const j = i.json;
  let fb = null;
  const res = searchResults(j.fb_text || '');
  if (res) fb = pickFacebook(j.name, res);
  if (!fb) fb = pickFacebookFromText(j.name, j.fb_text || '');
  if (!fb) fb = pickFacebookFromText(j.name, j.extract_text || '');
  const email = pickEmail(j.extract_text || '');
  const size = pickSize(j.extract_text || '');
  return { json: {
    company_id: j.company_id, run_id: j.run_id, name: j.name,
    facebook_url: fb ? fb.facebook_url : '',
    email: email || '',
    company_size: size || '',
    fb_found: !!fb, email_found: !!email, size_found: !!size,
    extract_attempted: !!j.extract_attempted,
    provider_enabled: !!j.provider_enabled
  } };
});
""".strip()

SUMMARY_JS = r"""
const parsed = $('Parse Contacts').all().map(i => i.json);
return [{ json: {
  success: true, stage: 'SF6',
  picked: parsed.length,
  fb_found: parsed.filter(p => p.fb_found).length,
  emails_found: parsed.filter(p => p.email_found).length,
  size_found: parsed.filter(p => p.size_found).length,
  provider_pending: parsed.filter(p => p.provider_enabled && !p.email_found).length,
  tavily_credits: parsed.length + parsed.filter(p => p.extract_attempted).length
} }];
""".strip()

BLOCKED_SUMMARY_JS = r"""
const rows = $input.all().map(i => i.json);
const first = rows[0] || {};
return [{ json: {
  success: true, stage: 'SF6',
  picked: 0, fb_found: 0, emails_found: 0, size_found: 0, provider_pending: 0, tavily_credits: 0,
  empty_run: !!first.empty_run, cap_blocked: !!first.cap_blocked
} }];
""".strip()

# ---------- node blocks ----------
out = []
out.append("import { workflow, node, trigger, sticky, ifElse, expr } from '@n8n/workflow-sdk';")
out.append(f"const aboutNote = sticky({J('SF6 v-next - Contact Waterfall (owner-approved 2026-11-16). For scored companies (fit >= contact_min_fit, cap max_contact_companies, atomic claim, enrichment-once): (1) Facebook page via Tavily search with deterministic name match, (2) website + /contact extract for verbatim emails, FB links and stated size, (3) provider reveal SLOT - counted as provider_pending when provider_enabled and no email found; the Apollo HTTP node lands when the owner creates the Apollo credential (free-plan API access to be verified). Phone already lives on companies from Places and is surfaced by SF8 v-next.5. Every Tavily call writes cost_ledger rows (search $0.008, extract $0.008); spend_cap_usd honoured before any paid node. No send node anywhere.')}, [], {{ color: 5 }});")
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
        { name: 'contact_min_fit', type: 'number' },
        { name: 'max_contact_companies', type: 'number' },
        { name: 'spend_cap_usd', type: 'number' },
        { name: 'provider_enabled', type: 'boolean' }
      ] }
    },
    position: [40, 400]
  },
  output: [{ search_profile_id: 'uuid', profile_version: 1, run_id: '', contact_min_fit: 30, max_contact_companies: 10, spend_cap_usd: 0, provider_enabled: false }]
});""")
out.append(f"""
const spentNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Load Spent',
    position: [320, 400],
    parameters: {{
      operation: 'executeQuery',
      query: {J(SPENT_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.run_id || \\'\\' ] }}}}') }}
    }},
    credentials: {{ postgres: newCredential('Postgres') }}
  }},
  output: [{{ spent_usd: 0 }}]
}});""")
out.append(f"""
const stageNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Stage Context',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(STAGE_JS)} }},
    position: [600, 400]
  }},
  output: [{{ run_id: '', spent_usd: 0 }}]
}});""")
out.append(f"""
const pickNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Pick + Claim + Audit',
    position: [880, 400],
    parameters: {{
      operation: 'executeQuery',
      query: {J(PICK_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.search_profile_id, $json.profile_version, $json.contact_min_fit, $json.max_contact_companies, $json.run_id ] }}}}') }}
    }},
    credentials: {{ postgres: newCredential('Postgres') }}
  }},
  output: [{{ company_id: 'uuid', empty_run: false }}]
}});""")
out.append(f"""
const capGateNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Cap Gate',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(CAPGATE_JS)} }},
    position: [1160, 400]
  }},
  output: [{{ has_work: true, cap_blocked: false }}]
}});""")
out.append("""
const hasWork = ifElse({
  version: 2.2,
  config: {
    name: 'Has Work?',
    position: [1440, 400],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ $json.has_work }}'), operator: { type: 'boolean', operation: 'true' } }],
        combinator: 'and'
      }
    }
  }
});""")
out.append(f"""
const buildNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Build Jobs',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(BUILD_JS)} }},
    position: [1720, 320]
  }},
  output: [{{ company_id: 'uuid', mcp_fb: '{{}}', mcp_extract: '{{}}' }}]
}});""")
mcp_params = {
    'serverTransport': 'httpStreamable',
    'endpointUrl': 'https://mcp.tavily.com/mcp/',
    'authentication': 'mcpOAuth2Api',
    'inputMode': 'json',
    'options': { 'timeout': 120000, 'convertToBinary': False }
}
def mcp_node(var, name, pos, tool, field, on_error=False):
    p = dict(mcp_params)
    p['tool'] = { '__rl': True, 'mode': 'list', 'value': tool, 'cachedResultName': tool }
    params = ', '.join(f'{k}: {J(v)}' for k, v in p.items())
    oe = "    onError: 'continueRegularOutput',\n" if on_error else ""
    return f"""
const {var} = node({{
  type: '@n8n/n8n-nodes-langchain.mcpClient',
  version: 1.1,
  config: {{
    name: {J(name)},
    position: [{pos}, 320],
{oe}    parameters: {{ {params}, jsonInput: expr('{{{{ $json.{field} }}}}') }},
    credentials: {{ mcpOAuth2Api: newCredential('Tavily MCP (generic)') }}
  }},
  output: [{{}}]
}});"""
out.append(mcp_node('mcpFb', 'Tavily MCP - Search Facebook', 2000, 'tavily_search', 'mcp_fb'))
out.append(f"""
const reattachANode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Reattach A',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(REATTACH_A_JS)} }},
    position: [2280, 320]
  }},
  output: [{{ company_id: 'uuid', fb_text: '' }}]
}});""")
out.append(mcp_node('mcpExtract', 'Tavily MCP - Extract Site', 2560, 'tavily_extract', 'mcp_extract', on_error=True))
out.append(f"""
const reattachBNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Reattach B',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(REATTACH_B_JS)} }},
    position: [2840, 320]
  }},
  output: [{{ company_id: 'uuid', extract_text: '' }}]
}});""")
out.append(f"""
const parseNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Parse Contacts',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(PARSE_JS)} }},
    position: [3120, 320]
  }},
  output: [{{ company_id: 'uuid', facebook_url: '', email: '', fb_found: false }}]
}});""")
out.append(f"""
const saveNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Save Contacts',
    position: [3400, 320],
    parameters: {{
      operation: 'executeQuery',
      query: {J(SAVE_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.company_id, $json.run_id, $json.facebook_url || \\'\\', $json.email || \\'\\', $json.company_size || \\'\\', $json.extract_attempted === true ] }}}}') }}
    }},
    credentials: {{ postgres: newCredential('Postgres') }}
  }},
  output: [{{ updated: 1 }}]
}});""")
out.append(f"""
const summaryNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Return - Summary',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(SUMMARY_JS)} }},
    position: [3680, 320]
  }},
  output: [{{ success: true, stage: 'SF6', picked: 0 }}]
}});""")
out.append(f"""
const capLedgerNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Cap Blocked Ledger',
    position: [1720, 560],
    parameters: {{
      operation: 'executeQuery',
      query: {J(CAP_LEDGER_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.run_id, $json.company_id || \\'\\' ] }}}}') }}
    }},
    credentials: {{ postgres: newCredential('Postgres') }}
  }},
  output: [{{}}]
}});""")
out.append(f"""
const blockedSummaryNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Return - Blocked/Empty Summary',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(BLOCKED_SUMMARY_JS)} }},
    position: [2000, 560]
  }},
  output: [{{ success: true, stage: 'SF6', picked: 0, cap_blocked: false }}]
}});""")
out.append("""
export default workflow('leadfinder-sf6-vnext', 'Lead Finder - SF6 Contact Waterfall v-next')
  .add(aboutNote)
  .add(subTrigger)
  .to(spentNode)
  .to(stageNode)
  .to(pickNode)
  .to(capGateNode)
  .to(hasWork
    .onTrue(buildNode
      .to(mcpFb)
      .to(reattachANode)
      .to(mcpExtract)
      .to(reattachBNode)
      .to(parseNode)
      .to(saveNode)
      .to(summaryNode))
    .onFalse(capLedgerNode
      .to(blockedSummaryNode)));""")
code = '\n'.join(out) + '\n'
(BASE/'sf6-vnext.ts').write_text(code)
json.dump({"code": code, "name": "Lead Finder - SF6 Contact Waterfall v-next"}, open(BASE/'create-sf6-vnext.json', 'w'))
import subprocess
r = subprocess.run(['node', '--check', str(BASE/'sf6-vnext.ts')], capture_output=True, text=True)
print('node --check:', 'OK' if r.returncode == 0 else r.stderr[:400])
print('generated', len(code))
