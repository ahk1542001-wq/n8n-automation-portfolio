import json, pathlib
BASE = pathlib.Path(__file__).resolve().parent
def J(s): return json.dumps(s)

# SF6b v-next.2 — built to Wonder's DESIGN ruling 2026-11-17 (t3/wonder-sf6b-verdict.md).
# Zero hardcoded targeting: decision-maker status comes ONLY from the pinned search
# profile's decision_maker_titles (deterministic phrase match). Save gate = DM match
# AND headline association gate (SF6 distinctive-token rule). Async Apify with run-id
# persistence + polling + dataset fetch by id; actor build pinned.

APIFY_ACTOR = 'george.the.developer~linkedin-company-employees-scraper'
APIFY_BUILD = '2.3.42'  # pin by build NUMBER (buildId Eolzg5lgjNDMRXJl1 rejected as unknown-build-tag, proven 2026-11-17)
APIFY_START_URL = f'https://api.apify.com/v2/acts/{APIFY_ACTOR}/runs?memory=1024&build={APIFY_BUILD}'

# ---------- SQL ----------
LOAD_SQL = """
SELECT
  (SELECT profile->'decision_maker_titles' FROM search_profiles WHERE id = $1 AND version = $2) AS dm_titles,
  (SELECT COALESCE(SUM(cost_usd), 0)::float FROM cost_ledger WHERE run_id = $3) AS spent_usd,
  (SELECT COALESCE(SUM(cost_usd), 0)::float FROM cost_ledger WHERE provider = 'apify' AND created_at >= date_trunc('month', now())) AS mtd_apify_usd
""".strip()

PICK_SQL = """
WITH cand AS (
  SELECT c.id, c.name, c.location, c.website, c.linkedin_url, s.fit_score,
         ROW_NUMBER() OVER (ORDER BY s.fit_score DESC, c.id ASC) AS rn
  FROM companies c
  JOIN scores s ON s.company_id = c.id
    AND s.search_profile_id = $1 AND s.profile_version = $2
  WHERE s.fit_score >= $3
    AND (c.linkedin_people_checked_at IS NULL OR (c.linkedin_people_next_check_at IS NOT NULL AND c.linkedin_people_next_check_at <= now()))
    AND (c.linkedin_people_claimed_at IS NULL OR c.linkedin_people_claimed_at < now() - interval '1 hour')
    AND $6 = 1
    AND $7 = 1
),
audit AS (
  INSERT INTO selection_audit (run_id, workflow, company_id, rank, fit_score, cutoff, selection_reason, is_first_skipped)
  SELECT $5, 'SF6b', id::text, rn::int, fit_score, $3,
         CASE WHEN rn <= $4 THEN 'selected' ELSE 'cap_reached' END,
         (rn = $4 + 1)
  FROM cand WHERE rn <= $4 + 1
  ON CONFLICT DO NOTHING
  RETURNING 1
),
claim AS (
  UPDATE companies c
  SET linkedin_people_claimed_at = now(), linkedin_people_claim_run_id = $5
  FROM cand
  WHERE c.id = cand.id AND cand.rn <= $4
  RETURNING c.id AS company_id, cand.name, cand.location, cand.website, cand.linkedin_url, cand.fit_score AS fit
)
SELECT company_id::text AS company_id, name, location, website, linkedin_url, fit, false AS empty_run, (SELECT count(*)::int FROM cand) AS candidates, false AS gate_fail, false AS linkedin_disabled FROM claim
UNION ALL
SELECT NULL, NULL, NULL, NULL, NULL, NULL, true AS empty_run, (SELECT count(*)::int FROM cand) AS candidates, ($6 = 0) AS gate_fail, ($7 = 0) AS linkedin_disabled
WHERE NOT EXISTS (SELECT 1 FROM claim)
""".strip()

MARK_SQL = """
WITH u AS (
  UPDATE companies SET
    linkedin_url = CASE WHEN $4 = 'resolved' THEN COALESCE(NULLIF(linkedin_url, ''), NULLIF($3, '')) ELSE linkedin_url END,
    linkedin_people_checked_at = CASE WHEN $4 IN ('none', 'ambiguous', 'slug_conflict') THEN now() ELSE linkedin_people_checked_at END,
    linkedin_people_next_check_at = CASE WHEN $4 IN ('none', 'ambiguous', 'slug_conflict') THEN now() + interval '90 days' ELSE linkedin_people_next_check_at END
  WHERE id = $1
  RETURNING id
),
l AS (
  INSERT INTO cost_ledger (run_id, workflow, provider, event_type, units, cost_usd, company_id, idempotency_key)
  SELECT $2, 'SF6b', 'tavily', 'charge', 1, 0.008, $1::text, 'sf6b:slug:' || $2 || ':' || $1::text
  WHERE EXISTS (SELECT 1 FROM u)
  ON CONFLICT (idempotency_key) DO NOTHING
  RETURNING id
),
e AS (
  INSERT INTO people_search_events (run_id, company_id, workflow, stage, detail)
  SELECT $2, id, 'SF6b', 'apify_linkedin',
         jsonb_build_object('outcome', CASE $4 WHEN 'none' THEN 'no_linkedin_page' WHEN 'ambiguous' THEN 'ambiguous_slug' ELSE 'slug_conflict' END)
  FROM u WHERE $4 IN ('none', 'ambiguous', 'slug_conflict')
  RETURNING id
)
SELECT (SELECT count(*) FROM u)::int AS updated
""".strip()

PERSIST_RUN_SQL = """
INSERT INTO cost_ledger (run_id, workflow, provider, event_type, units, cost_usd, company_id, idempotency_key)
SELECT $1, 'SF6b', 'apify', 'estimate', 0, 0, '', 'sf6b:run:' || $1 || ':' || $2
WHERE $3 = 1
ON CONFLICT (idempotency_key) DO NOTHING
""".strip()

SAVE_PERSON_SQL = """
WITH exist AS (SELECT company_id FROM people WHERE linkedin_url = $4 LIMIT 1),
ins AS (
  INSERT INTO people (company_id, full_name, title, linkedin_url, is_decision_maker, source, raw_payload, source_url, evidence_quote, fetched_at, retention_until, retention_basis)
  SELECT $1::uuid, $2, $3, $4, true, 'apify_linkedin', $6::jsonb, $7, $8, now(), now() + interval '12 months', 'legitimate_interest_b2b_public'
  WHERE $5 = 1 AND NOT EXISTS (SELECT 1 FROM exist)
  RETURNING id
),
led AS (
  INSERT INTO cost_ledger (run_id, workflow, provider, event_type, units, cost_usd, company_id, idempotency_key)
  SELECT $9, 'SF6b', 'apify', 'charge', 1, 0.01, $1::text, 'sf6b:apify:' || $9 || ':' || $1::text || ':' || $10
  WHERE $11 = 1
  ON CONFLICT (idempotency_key) DO NOTHING
  RETURNING id
)
SELECT CASE
  WHEN EXISTS (SELECT 1 FROM ins) THEN 'inserted'
  WHEN $5 = 1 AND EXISTS (SELECT 1 FROM exist) AND (SELECT company_id FROM exist) = $1::uuid THEN 'dup_same'
  WHEN $5 = 1 AND EXISTS (SELECT 1 FROM exist) THEN 'dup_cross'
  WHEN $5 = 1 THEN 'save_failed'
  ELSE 'dropped'
END AS outcome
""".strip()

MARK_CHECKED_SQL = """
WITH u AS (
  UPDATE companies SET linkedin_people_checked_at = now(), linkedin_people_next_check_at = NULL WHERE id = $1 AND $5 = 1
  RETURNING id
),
e AS (
  INSERT INTO people_search_events (run_id, company_id, workflow, stage, detail)
  SELECT $2, id, 'SF6b', 'apify_linkedin', $3::jsonb FROM u
  RETURNING id
),
l AS (
  INSERT INTO cost_ledger (run_id, workflow, provider, event_type, units, cost_usd, company_id, idempotency_key)
  SELECT $2, 'SF6b', 'apify', 'charge', 1, 0.005, $1::text, 'sf6b:apify-start:' || $2
  WHERE $4 = 1 AND EXISTS (SELECT 1 FROM u)
  ON CONFLICT (idempotency_key) DO NOTHING
  RETURNING id
)
SELECT (SELECT count(*) FROM u)::int AS updated
""".strip()

FAIL_SQL = """
WITH u AS (
  UPDATE companies SET linkedin_people_claimed_at = NULL, linkedin_people_claim_run_id = NULL WHERE id = $1 AND linkedin_people_claim_run_id = $2
  RETURNING id
),
e AS (
  INSERT INTO people_search_events (run_id, company_id, workflow, stage, detail)
  SELECT $2, id, 'SF6b', 'apify_linkedin', '{"outcome":"apify_failed"}'::jsonb FROM u
  RETURNING id
),
l AS (
  INSERT INTO cost_ledger (run_id, workflow, provider, event_type, units, cost_usd, company_id, idempotency_key)
  SELECT $2, 'SF6b', 'apify', 'charge', 1, $3, $1::text, 'sf6b:apify-usage:' || $2 || ':' || $4
  WHERE $5 = 1 AND EXISTS (SELECT 1 FROM u)
  ON CONFLICT (idempotency_key) DO NOTHING
  RETURNING id
)
SELECT (SELECT count(*) FROM u)::int AS updated
""".strip()

# ---------- JS ----------
TOKEN_JS = r"""
const STOPWORDS = new Set(['the', 'and', 'co', 'ltd', 'company', 'store', 'shop', 'hotel', 'resort', 'bangkok', 'yangon', 'thailand', 'myanmar', 'facebook', 'page', 'official']);
const GENERIC = new Set(['training', 'service', 'services', 'mobile', 'phone', 'computer', 'electronics', 'hardware', 'fashion', 'trading', 'enterprise', 'enterprises', 'solution', 'solutions', 'technology', 'technologies', 'digital', 'media', 'express', 'global', 'international', 'modern', 'center', 'centre', 'group', 'beauty', 'star', 'king', 'best', 'top', 'world', 'accessories', 'garment', 'textile', 'food', 'travel', 'tour', 'tours', 'clinic', 'school', 'academy', 'studio', 'salon', 'cafe', 'restaurant', 'bakery', 'pharmacy', 'mart', 'market', 'online']);
function normTokens(s) {
  return String(s || '').toLowerCase().replace(/[^\p{L}\p{N}\s]/gu, ' ').split(/\s+/).filter(w => w.length >= 3 && !STOPWORDS.has(w));
}
function normPhrase(s) {
  return String(s || '').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').replace(/\s+/g, ' ').trim();
}
function hashId(s) { let h = 5381; const str = String(s || ''); for (let i = 0; i < str.length; i++) { h = ((h * 33) ^ str.charCodeAt(i)) >>> 0; } return h.toString(16); }
""".strip()

STAGE_JS = r"""
const t = $('When Executed by Another Workflow').first().json;
const prof = $input.first().json || {};
const spent = Number(prof.spent_usd || 0);
const mtd = Number(prof.mtd_apify_usd || 0);
let titles = [];
try { const raw = typeof prof.dm_titles === 'string' ? JSON.parse(prof.dm_titles) : prof.dm_titles; if (Array.isArray(raw)) titles = raw.map(x => String(x || '').trim()).filter(Boolean); } catch (e) { titles = []; }
const maxEmployees = Number(t.max_employees ?? 10);
const maxCompanies = Number(t.max_linkedin_companies ?? 10);
const cap = (t.spend_cap_usd === undefined || t.spend_cap_usd === null || t.spend_cap_usd === '') ? null : Number(t.spend_cap_usd);
const perCompany = 0.008 + maxEmployees * 0.01;
let affordable = maxCompanies;
if (cap !== null) affordable = Math.max(0, Math.min(maxCompanies, Math.floor((cap - spent - 0.005) / perCompany)));
return [{ json: {
  search_profile_id: t.search_profile_id,
  profile_version: Number(t.profile_version || 1),
  run_id: t.run_id || '',
  linkedin_min_fit: Number(t.linkedin_min_fit ?? 30),
  max_linkedin_companies: maxCompanies,
  max_employees: maxEmployees,
  spend_cap_usd: cap,
  spent_usd: spent,
  mtd_apify_usd: mtd,
  dm_titles: titles,
  titles_ok: titles.length > 0,
  titles_ok_int: titles.length > 0 ? 1 : 0,
  linkedin_enabled_int: t.linkedin_people_enabled === true ? 1 : 0,
  affordable: affordable,
  per_company_est: perCompany
} }];
""".strip()

CAPGATE_JS = r"""
const ctx = $('Stage Context').first().json;
const rows = $input.all().map(i => i.json);
const picked = rows.filter(r => !r.empty_run);
const sentinel = rows.find(r => r.empty_run) || {};
const candidates = Number(sentinel.candidates || 0);
if (!picked.length) {
  return [{ json: { has_work: false, empty_run: candidates === 0 && !sentinel.linkedin_disabled, cap_blocked: candidates > 0 && !sentinel.linkedin_disabled, gate_fail: !!sentinel.gate_fail, linkedin_disabled: !!sentinel.linkedin_disabled, picked: 0, candidates: candidates, run_id: ctx.run_id } }];
}
return picked.map(r => ({ json: Object.assign({}, r, {
  has_work: true, cap_blocked: false, empty_run: false,
  run_id: ctx.run_id, search_profile_id: ctx.search_profile_id,
  profile_version: ctx.profile_version, max_employees: ctx.max_employees
}) }));
""".strip()

BUILD_JS = TOKEN_JS + r"""

return $input.all().map(i => {
  const j = i.json;
  const nameToks = normTokens(j.name);
  const distinctive = nameToks.filter(t => !GENERIC.has(t));
  return { json: Object.assign({}, j, {
    name_tokens: nameToks,
    distinctive_tokens: distinctive,
    mcp_slug: JSON.stringify({ query: '"' + j.name + '" linkedin company', search_depth: 'basic', max_results: 5 }),
    mcp_extract: JSON.stringify({ urls: j.website ? [j.website] : [], query: 'linkedin company page', extract_depth: 'basic', format: 'text' })
  }) };
});
""".strip()

REATTACH_A_JS = r"""
const jobs = $('Build Jobs').all().map(i => i.json);
return $input.all().map((item, idx) => {
  const job = jobs[idx] || {};
  let t = '';
  try { t = typeof item.json === 'string' ? item.json : JSON.stringify(item.json); } catch (e) { t = String(item.json); }
  return { json: Object.assign({}, job, { slug_text: t }) };
});
""".strip()

RESOLVE_JS = TOKEN_JS + r"""

function digResults(text) {
  let cur = text;
  for (let depth = 0; depth < 4; depth++) {
    let obj = null;
    try { obj = typeof cur === 'string' ? JSON.parse(cur) : cur; } catch (e) { break; }
    if (!obj || typeof obj !== 'object') break;
    if (Array.isArray(obj.results)) return obj.results;
    if (Array.isArray(obj.content)) { const c = obj.content.find(x => x && typeof x.text === 'string'); cur = c ? c.text : ''; continue; }
    if (typeof obj.text === 'string') { cur = obj.text; continue; }
    if (obj.data) { cur = obj.data; continue; }
    break;
  }
  return null;
}
function slugOf(url) {
  const m = String(url || '').match(/linkedin\.com\/company\/([a-zA-Z0-9\-_%\.]+)/i);
  return m ? m[1].replace(/\.+$/, '') : '';
}
function verifySlug(j, slug, title) {
  if (!slug) return false;
  const candToks = new Set([...normTokens(slug.replace(/[-_%\.]/g, ' ')), ...normTokens(title || '')]);
  const matched = (j.name_tokens || []).filter(t => candToks.has(t));
  const distinctive = matched.filter(t => (j.distinctive_tokens || []).includes(t));
  if (distinctive.length >= 1 || matched.length >= 2) return true;
  const flat = slug.toLowerCase().replace(/[^a-z0-9]/g, '');
  return (j.distinctive_tokens || []).some(t => t.length >= 4 && flat.includes(t));
}
return $input.all().map(item => {
  const j = item.json;
  const text = String(j.slug_text || '');
  let candidates = [];
  const results = digResults(text);
  if (results) {
    for (const r of results) { const s = slugOf(r && r.url); if (s) candidates.push({ slug: s, title: String((r && r.title) || '') }); }
  } else {
    const urls = text.match(/https?:\/\/[^\s"'\)]+linkedin\.com\/company\/[^\s"'\)]+/gi) || [];
    for (const u of urls) { const s = slugOf(u); if (s) candidates.push({ slug: s, title: '' }); }
  }
  // The company's OWN website outranks search results: a LinkedIn link in the
  // site text is the company pointing at its own page (highest precision).
  const siteText = String(j.site_text || '');
  const siteUrls = siteText.match(/https?:\/\/[^\s"'\)]+linkedin\.com\/company\/[^\s"'\)]+/gi) || [];
  const siteCandidates = [];
  for (const u of siteUrls) { const s = slugOf(u); if (s && !siteCandidates.includes(s)) siteCandidates.push({ slug: s, title: '' }); }
  const allCandidates = [...siteCandidates, ...candidates];
  const storedSlug = j.linkedin_url ? slugOf(j.linkedin_url) : '';
  const passing = [];
  for (const c of allCandidates) { if (verifySlug(j, c.slug, c.title) && !passing.includes(c.slug)) passing.push(c.slug); }
  let resolution, slug = '', url = '';
  if (storedSlug) {
    const storedOk = verifySlug(j, storedSlug, '');
    if (!storedOk) { resolution = 'slug_conflict'; }
    else if (passing.length && !passing.includes(storedSlug)) { resolution = 'slug_conflict'; }
    else { resolution = 'stored_verified'; slug = storedSlug; url = j.linkedin_url; }
  } else if (!passing.length) { resolution = 'none'; }
  else {
    const flatName = normPhrase(j.name || '').replace(/ /g, '');
    const exact = passing.find(s => s.toLowerCase() === flatName);
    if (exact) { resolution = 'resolved'; slug = exact; url = 'https://www.linkedin.com/company/' + exact; }
    else if (passing.length > 1) { resolution = 'ambiguous'; }
    else { resolution = 'resolved'; slug = passing[0]; url = 'https://www.linkedin.com/company/' + slug; }
  }
  return { json: Object.assign({}, j, { resolution: resolution, slug: slug, resolved_url: url }) };
});
""".strip()

REATTACH_A2_JS = r"""
const jobs = $('Reattach A').all().map(i => i.json);
return $input.all().map((item, idx) => {
  const job = jobs[idx] || {};
  let t = '';
  try { t = typeof item.json === 'string' ? item.json : JSON.stringify(item.json); } catch (e) { t = String(item.json); }
  return { json: Object.assign({}, job, { site_text: t }) };
});
""".strip()

REATTACH_B_JS = r"""
const jobs = $('Resolve Slugs').all().map(i => i.json);
return $input.all().map((item, idx) => {
  const job = jobs[idx] || {};
  return { json: Object.assign({}, job, { mark_updated: (item.json || {}).updated }) };
});
""".strip()

BATCH_JS = r"""
const ctx = $('Stage Context').first().json;
const items = $input.all().map(i => i.json);
const ok = items.filter(r => r.resolution === 'resolved' || r.resolution === 'stored_verified');
const batch = ok.map(r => ({ company_id: r.company_id, name: r.name, slug: r.slug, linkedin_url: r.resolved_url, distinctive_tokens: r.distinctive_tokens || [] }));
const urls = batch.map(b => b.linkedin_url);
return [{ json: {
  run_id: ctx.run_id, batch: batch, batch_empty: batch.length === 0,
  apify_input: { companies: urls, companyUrls: urls, maxEmployees: ctx.max_employees, maxItems: urls.length * ctx.max_employees },
  picked_count: items.length
} }];
""".strip()

PREP_JS = r"""
const batchItem = $('Build Apify Batch').first().json;
const j = $input.first().json || {};
const data = j.data || {};
const ok = !!data.id;
return [{ json: {
  apify_run_id: ok ? String(data.id) : '',
  dataset_id: ok ? String(data.defaultDatasetId || '') : '',
  start_ok: ok,
  start_ok_int: ok ? 1 : 0,
  run_id: batchItem.run_id,
  start_error: ok ? '' : JSON.stringify(j).slice(0, 300)
} }];
""".strip()

POLL_JS = r"""
const prep = $('Prep Poll').first().json;
const j = $input.first().json || {};
const data = j.data || {};
const status = String(data.status || '');
const startedAt = data.startedAt ? Date.parse(data.startedAt) : 0;
const elapsedMin = startedAt ? (Date.now() - startedAt) / 60000 : 0;
const finished = ['SUCCEEDED', 'FAILED', 'ABORTED', 'TIMED-OUT'].includes(status);
const giveUp = !finished && elapsedMin > 8;
return [{ json: {
  apify_run_id: prep.apify_run_id,
  dataset_id: prep.dataset_id || String(data.defaultDatasetId || ''),
  status: status,
  finished: finished || giveUp,
  succeeded: status === 'SUCCEEDED',
  usage_usd: Number(data.usageTotalUsd || 0),
  run_id: prep.run_id
} }];
""".strip()

PARSE_JS = TOKEN_JS + r"""

const batchItem = $('Build Apify Batch').first().json;
const ctx = $('Stage Context').first().json;
const titles = (ctx.dm_titles || []).map(t => ({ raw: t, norm: normPhrase(t) })).filter(t => t.norm);
const meta = batchItem.batch || [];
const bySlug = {};
for (const m of meta) bySlug[m.slug] = m;
let droppedSchema = 0;
const out = [];
for (const item of $input.all()) {
  const p = item.json || {};
  if (!p.fullName || !p.profileUrl || !p.publicIdentifier || !p.company) { droppedSchema++; continue; }
  const m = bySlug[String(p.company)];
  if (!m) { droppedSchema++; continue; }
  const headline = String(p.headline || '');
  const hNorm = ' ' + normPhrase(headline) + ' ';
  let matchedTitle = '';
  for (const t of titles) { if (hNorm.includes(' ' + t.norm + ' ')) { matchedTitle = t.raw; break; } }
  const hToks = new Set(normTokens(headline));
  const assoc = (m.distinctive_tokens || []).some(t => hToks.has(t)) || normPhrase(headline).replace(/ /g, '').includes(String(m.slug || '').toLowerCase().replace(/[^a-z0-9]/g, ''));
  const dm = !!matchedTitle;
  const save = dm && assoc;
  const canonical = 'https://www.linkedin.com/in/' + String(p.publicIdentifier).toLowerCase();
  const raw = Object.assign({}, p, { dm_matched_title: matchedTitle || null, dm_profile_version: ctx.profile_version });
  out.push({ json: {
    company_id: m.company_id, full_name: String(p.fullName), title: headline,
    linkedin_url: canonical, save_flag: save ? 1 : 0,
    is_dm_match: dm, assoc_ok: assoc,
    drop_reason: save ? '' : (dm ? 'association_unverified' : 'non_dm'),
    raw_json: JSON.stringify(raw), source_url: canonical, evidence_quote: headline,
    run_id: batchItem.run_id, id_hash: hashId(p.publicIdentifier),
    charged: p.charged === true ? 1 : 0,
    run_counts: null
  } });
}
const counts = { returned: out.length, dropped_schema: droppedSchema };
for (const o of out) o.json.run_counts = counts;
if (!out.length) {
  out.push({ json: { company_id: '00000000-0000-0000-0000-000000000000', full_name: '', title: '', linkedin_url: '', save_flag: 0, is_dm_match: false, assoc_ok: false, drop_reason: 'none', raw_json: '{}', source_url: '', evidence_quote: '', run_id: batchItem.run_id, id_hash: '', charged: 0, run_counts: counts, sentinel: true } });
}
return out;
""".strip()

ROLLUP_JS = r"""
const batchItem = $('Build Apify Batch').first().json;
const people = $('Parse People').all().map(i => i.json).filter(p => !p.sentinel);
const saves = $('DB - Save Person').all().map(i => i.json);
const byCompany = {};
for (const m of (batchItem.batch || [])) byCompany[m.company_id] = { returned: 0, charged: 0, dm_saved: 0, dup_same: 0, dup_cross: 0, non_dm_dropped: 0, association_dropped: 0 };
people.forEach((p, idx) => {
  const c = byCompany[p.company_id]; if (!c) return;
  c.returned++; c.charged += Number(p.charged || 0);
  const outcome = (saves[idx] || {}).outcome || '';
  if (p.save_flag === 1) {
    if (outcome === 'inserted') c.dm_saved++;
    else if (outcome === 'dup_same') c.dup_same++;
    else if (outcome === 'dup_cross') c.dup_cross++;
  } else if (p.drop_reason === 'non_dm') c.non_dm_dropped++;
  else if (p.drop_reason === 'association_unverified') c.association_dropped++;
});
const batch = batchItem.batch || [];
if (!batch.length) return [{ json: { company_id: '00000000-0000-0000-0000-000000000000', run_id: batchItem.run_id, detail_json: '{}', is_first: 0, act: 0 } }];
return batch.map((m, i) => {
  const c = byCompany[m.company_id];
  const detail = Object.assign({ outcome: c.returned === 0 ? 'searched_zero' : 'searched', source: 'apify_linkedin', linkedin_url: m.linkedin_url }, c);
  return { json: { company_id: m.company_id, run_id: batchItem.run_id, detail_json: JSON.stringify(detail), is_first: i === 0 ? 1 : 0, act: 1 } };
});
""".strip()

FAIL_ITEMS_JS = r"""
const batchItem = $('Build Apify Batch').first().json;
let usage = 0; let runId = '';
try { const pc = $('Poll Check').first().json; usage = Number(pc.usage_usd || 0); runId = String(pc.apify_run_id || ''); } catch (e) {}
try { const prep = $('Prep Poll').first().json; if (!runId) runId = String(prep.apify_run_id || ''); } catch (e) {}
const batch = batchItem.batch || [];
if (!batch.length) return [{ json: { company_id: '00000000-0000-0000-0000-000000000000', run_id: batchItem.run_id, usage_usd: 0, apify_run_id: runId, is_first: 0 } }];
return batch.map((m, i) => ({ json: { company_id: m.company_id, run_id: batchItem.run_id, usage_usd: usage, apify_run_id: runId, is_first: i === 0 ? 1 : 0 } }));
""".strip()

SUMMARY_JS = r"""
function tryAll(name) { try { return $(name).all().map(i => i.json); } catch (e) { return []; } }
function tryFirst(name) { try { return $(name).first().json || {}; } catch (e) { return {}; } }
const ctx = tryFirst('Stage Context');
const cap = tryAll('Cap Gate');
const picked = cap.filter(r => !r.empty_run && r.has_work).length;
const batchItem = tryFirst('Build Apify Batch');
const people = tryAll('Parse People').filter(p => !p.sentinel);
const saves = tryAll('DB - Save Person');
const saved = saves.filter(s => s.outcome === 'inserted').length;
const counts = (people[0] && people[0].run_counts) || { returned: people.length, dropped_schema: 0 };
const chargedProfiles = people.reduce((a, p) => a + Number(p.charged || 0), 0);
const runApifyCost = chargedProfiles * 0.01 + ((batchItem.batch || []).length ? 0.005 : 0);
const mtdAfter = Number(ctx.mtd_apify_usd || 0) + runApifyCost;
let failed = false;
try { failed = $('Build Failure Items A').all().length > 0; } catch (e) {}
if (!failed) { try { failed = $('Build Failure Items B').all().length > 0; } catch (e) {} }
return [{ json: {
  success: !failed, stage: 'SF6b',
  picked: picked, slug_resolved: (batchItem.batch || []).length,
  people_returned: counts.returned, dropped_schema: counts.dropped_schema,
  people_saved: saved, decision_makers_saved: saved,
  non_dm_dropped: people.filter(p => p.drop_reason === 'non_dm').length,
  association_dropped: people.filter(p => p.drop_reason === 'association_unverified').length,
  dup_cross_company: saves.filter(s => s.outcome === 'dup_cross').length,
  apify_profiles_charged: chargedProfiles,
  apify_run_cost_usd: Math.round(runApifyCost * 1000) / 1000,
  slug_search_cost_usd: Math.round(picked * 0.008 * 1000) / 1000,
  total_stage_cost_usd: Math.round((runApifyCost + picked * 0.008) * 1000) / 1000,
  mtd_apify_usd: Math.round(mtdAfter * 1000) / 1000,
  mtd_warning: mtdAfter > 4.5,
  apify_failed: failed,
  cap_blocked: false, empty_run: picked === 0
} }];
""".strip()

GATE_FAIL_JS = r"""
return [{ json: {
  success: false, stage: 'SF6b', reason: 'no_decision_maker_titles_in_profile',
  picked: 0, slug_resolved: 0, people_returned: 0, dropped_schema: 0,
  people_saved: 0, decision_makers_saved: 0, non_dm_dropped: 0, association_dropped: 0,
  dup_cross_company: 0, apify_profiles_charged: 0, apify_run_cost_usd: 0,
  mtd_apify_usd: 0, mtd_warning: false, apify_failed: false,
  cap_blocked: false, empty_run: false
} }];
""".strip()

BLOCKED_SUMMARY_JS = r"""
const rows = $input.all().map(i => i.json);
const first = rows[0] || {};
return [{ json: {
  success: true, stage: 'SF6b',
  picked: 0, slug_resolved: 0, people_returned: 0, dropped_schema: 0,
  people_saved: 0, decision_makers_saved: 0, non_dm_dropped: 0, association_dropped: 0,
  dup_cross_company: 0, apify_profiles_charged: 0, apify_run_cost_usd: 0,
  mtd_apify_usd: 0, mtd_warning: false, apify_failed: false,
  empty_run: !!first.empty_run, cap_blocked: !!first.cap_blocked
} }];
""".strip()


BLOCKED_GATE_JS = r"""
const rows = $input.all().map(i => i.json);
const first = rows[0] || {};
if (first.gate_fail) {
  return [{ json: {
    success: false, stage: 'SF6b', reason: 'no_decision_maker_titles_in_profile',
    picked: 0, slug_resolved: 0, people_returned: 0, dropped_schema: 0,
    people_saved: 0, decision_makers_saved: 0, non_dm_dropped: 0, association_dropped: 0,
    dup_cross_company: 0, apify_profiles_charged: 0, apify_run_cost_usd: 0,
    mtd_apify_usd: 0, mtd_warning: false, apify_failed: false,
    cap_blocked: false, empty_run: false, gate_fail: true
  } }];
}
if (first.linkedin_disabled) {
  return [{ json: {
    success: true, stage: 'SF6b', reason: 'linkedin_people_disabled',
    picked: 0, slug_resolved: 0, people_returned: 0, dropped_schema: 0,
    people_saved: 0, decision_makers_saved: 0, non_dm_dropped: 0, association_dropped: 0,
    dup_cross_company: 0, apify_profiles_charged: 0, apify_run_cost_usd: 0,
    mtd_apify_usd: 0, mtd_warning: false, apify_failed: false,
    cap_blocked: false, empty_run: false, gate_fail: false, linkedin_disabled: true
  } }];
}
return [{ json: {
  success: true, stage: 'SF6b',
  picked: 0, slug_resolved: 0, people_returned: 0, dropped_schema: 0,
  people_saved: 0, decision_makers_saved: 0, non_dm_dropped: 0, association_dropped: 0,
  dup_cross_company: 0, apify_profiles_charged: 0, apify_run_cost_usd: 0,
  mtd_apify_usd: 0, mtd_warning: false, apify_failed: false,
  empty_run: !!first.empty_run, cap_blocked: !!first.cap_blocked, gate_fail: false, linkedin_disabled: false
} }];
""".strip()

BUILD_FETCH_JS = r"""
const prep = $('Prep Poll').first().json;
const batchItem = $('Build Apify Batch').first().json;
const ctx = $('Stage Context').first().json;
const cap = $('Cap Gate').all().map(i => i.json);
return [{ json: {
  apify_run_id: prep.apify_run_id || '',
  dataset_id: prep.dataset_id || '',
  run_id: ctx.run_id,
  batch_json: JSON.stringify(batchItem.batch || []),
  dm_titles_json: JSON.stringify(ctx.dm_titles || []),
  profile_version: ctx.profile_version,
  mtd_apify_usd: ctx.mtd_apify_usd,
  picked_count: cap.filter(r => !r.empty_run && r.has_work).length
} }];
""".strip()

# ---------- Generator ----------
REATTACH_RUN_JS = r"""
const p = $('Prep Poll').first().json;
return [{ json: p }];
""".strip()

BUILD_RUN_URL_JS = r"""
const j = $input.first().json;
return [{ json: Object.assign({}, j, { run_url: 'https://api.apify.com/v2/actor-runs/' + j.apify_run_id }) }];
""".strip()

BUILD_DS_URL_JS = r"""
const j = $input.first().json;
return [{ json: Object.assign({}, j, { dataset_url: 'https://api.apify.com/v2/datasets/' + j.dataset_id + '/items?clean=true&limit=1000' }) }];
""".strip()

out = []
out.append("import { workflow, node, trigger, sticky, ifElse, expr } from '@n8n/workflow-sdk';")
out.append(f"const aboutNote = sticky({J('SF6b v-next.2 - LinkedIn People via Apify (2026-11-17, Wonder design ruling). DYNAMIC: decision-maker status derives ONLY from the pinned search profile decision_maker_titles (deterministic phrase match on the verbatim headline); zero hardcoded titles. Save gate = DM match AND SF6 distinctive-token association gate. Picks fit-scored companies (claim + audit, affordability truncation BEFORE claim), resolves each company LinkedIn page with token verification (no first-result trust), then ONE async Apify run (build pinned) with run-id persisted in cost_ledger, polling, dataset fetch by id. Ledger: Tavily slug search $0.008, Apify $0.01 per charged profile, $0.005 actor start per run. People saved with headline as evidence quote + 12-month retention. No send node anywhere.')}, [], {{ color: 5 }});")
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
        { name: 'linkedin_min_fit', type: 'number' },
        { name: 'max_linkedin_companies', type: 'number' },
        { name: 'spend_cap_usd', type: 'number' },
        { name: 'max_employees', type: 'number' },
        { name: 'linkedin_people_enabled', type: 'boolean' }
      ] }
    },
    position: [40, 400]
  },
  output: [{ search_profile_id: 'uuid', profile_version: 1, run_id: '', linkedin_min_fit: 30, max_linkedin_companies: 10, spend_cap_usd: 0, max_employees: 10 }]
});""")
out.append(f"""
const loadNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Load Profile + Spent',
    position: [320, 400],
    parameters: {{
      operation: 'executeQuery',
      query: {J(LOAD_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.search_profile_id, $json.profile_version, $json.run_id ] }}}}') }}
    }},
    credentials: {{ postgres: newCredential('Postgres') }}
  }},
  output: [{{ dm_titles: [], spent_usd: 0, mtd_apify_usd: 0 }}]
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
  output: [{{ run_id: '', titles_ok: true, affordable: 10 }}]
}});""")
out.append("""
const titlesGate = ifElse({
  version: 2.2,
  config: {
    name: 'Titles OK?',
    position: [880, 400],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ $json.titles_ok }}'), operator: { type: 'boolean', operation: 'true' } }],
        combinator: 'and'
      }
    }
  }
});""")
out.append(f"""
const gateFailNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Return - Gate Fail Summary',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(GATE_FAIL_JS)} }},
    position: [1160, 720]
  }},
  output: [{{ success: false, stage: 'SF6b' }}]
}});""")
out.append(f"""
const pickNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Pick + Claim + Audit',
    position: [1160, 400],
    parameters: {{
      operation: 'executeQuery',
      query: {J(PICK_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.search_profile_id, $json.profile_version, $json.linkedin_min_fit, $json.affordable, $json.run_id, $json.titles_ok_int, $json.linkedin_enabled_int ] }}}}') }}
    }},
    credentials: {{ postgres: newCredential('Postgres') }}
  }},
  output: [{{ company_id: 'uuid', empty_run: false, candidates: 0 }}]
}});""")
out.append(f"""
const capGateNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Cap Gate',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(CAPGATE_JS)} }},
    position: [1440, 400]
  }},
  output: [{{ has_work: true, cap_blocked: false }}]
}});""")
out.append("""
const hasWork = ifElse({
  version: 2.2,
  config: {
    name: 'Has Work?',
    position: [1720, 400],
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
const blockedSummaryNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Return - Blocked/Gate Summary',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(BLOCKED_GATE_JS)} }},
    position: [2000, 720]
  }},
  output: [{{ success: true, stage: 'SF6b', picked: 0, cap_blocked: false }}]
}});""")
out.append(f"""
const buildNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Build Jobs',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(BUILD_JS)} }},
    position: [2000, 320]
  }},
  output: [{{ company_id: 'uuid', mcp_slug: '{{}}' }}]
}});""")
out.append("""
const mcpSearch = node({
  type: '@n8n/n8n-nodes-langchain.mcpClient',
  version: 1.1,
  config: {
    name: 'Tavily MCP - Search LinkedIn',
    position: [2280, 320],
    parameters: { serverTransport: 'httpStreamable', endpointUrl: 'https://mcp.tavily.com/mcp/', authentication: 'mcpOAuth2Api', inputMode: 'json', options: { timeout: 120000, convertToBinary: false }, tool: { __rl: true, mode: 'list', value: 'tavily_search', cachedResultName: 'tavily_search' }, jsonInput: expr('{{ $json.mcp_slug }}') },
    credentials: { mcpOAuth2Api: newCredential('Tavily MCP (generic)') }
  },
  output: [{}]
});""")
out.append(f"""
const reattachANode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Reattach A',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(REATTACH_A_JS)} }},
    position: [2560, 320]
  }},
  output: [{{ company_id: 'uuid', slug_text: '' }}]
}});""")
out.append("""
const mcpExtract = node({
  type: '@n8n/n8n-nodes-langchain.mcpClient',
  version: 1.1,
  config: {
    name: 'Tavily MCP - Extract Website',
    onError: 'continueRegularOutput',
    position: [2840, 320],
    parameters: { serverTransport: 'httpStreamable', endpointUrl: 'https://mcp.tavily.com/mcp/', authentication: 'mcpOAuth2Api', inputMode: 'json', options: { timeout: 120000, convertToBinary: false }, tool: { __rl: true, mode: 'list', value: 'tavily_extract', cachedResultName: 'tavily_extract' }, jsonInput: expr('{{ $json.mcp_extract }}') },
    credentials: { mcpOAuth2Api: newCredential('Tavily MCP (generic)') }
  },
  output: [{}]
});""")
out.append(f"""
const reattachA2Node = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Reattach A2',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(REATTACH_A2_JS)} }},
    position: [2980, 320]
  }},
  output: [{{ company_id: 'uuid', site_text: '' }}]
}});""")
out.append(f"""
const resolveNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Resolve Slugs',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(RESOLVE_JS)} }},
    position: [2840, 320]
  }},
  output: [{{ company_id: 'uuid', resolution: 'none', resolved_url: '' }}]
}});""")
out.append(f"""
const markNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Mark + Slug Ledger',
    position: [3120, 320],
    parameters: {{
      operation: 'executeQuery',
      query: {J(MARK_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.company_id, $json.run_id, $json.resolved_url || \\'\\', $json.resolution ] }}}}') }}
    }},
    credentials: {{ postgres: newCredential('Postgres') }}
  }},
  output: [{{ updated: 1 }}]
}});""")
out.append(f"""
const reattachBNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Reattach B',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(REATTACH_B_JS)} }},
    position: [3400, 320]
  }},
  output: [{{ company_id: 'uuid', resolution: 'none' }}]
}});""")
out.append(f"""
const batchNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Build Apify Batch',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(BATCH_JS)} }},
    position: [3680, 320]
  }},
  output: [{{ run_id: '', batch: [], batch_empty: true, apify_input: {{}} }}]
}});""")
out.append("""
const batchGate = ifElse({
  version: 2.2,
  config: {
    name: 'Batch Empty?',
    position: [3960, 320],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ $json.batch_empty }}'), operator: { type: 'boolean', operation: 'true' } }],
        combinator: 'and'
      }
    }
  }
});""")
out.append(f"""
const startNode = node({{
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {{
    name: 'Apify - Start Run',
    onError: 'continueRegularOutput',
    alwaysOutputData: true,
    position: [4240, 320],
    parameters: {{
      method: 'POST',
      url: {J(APIFY_START_URL)},
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendBody: true,
      contentType: 'json',
      specifyBody: 'json',
      jsonBody: expr('{{{{ $json.apify_input }}}}'),
      options: {{ timeout: 120000 }}
    }},
    credentials: {{ httpHeaderAuth: newCredential('Apify') }}
  }},
  output: [{{ data: {{ id: 'x', defaultDatasetId: 'y' }} }}]
}});""")
out.append(f"""
const prepNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Prep Poll',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(PREP_JS)} }},
    position: [4520, 320]
  }},
  output: [{{ apify_run_id: 'x', start_ok: true }}]
}});""")
out.append("""
const startGate = ifElse({
  version: 2.2,
  config: {
    name: 'Start OK?',
    position: [4800, 320],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ $json.start_ok }}'), operator: { type: 'boolean', operation: 'true' } }],
        combinator: 'and'
      }
    }
  }
});""")
out.append(f"""
const persistNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Persist Run Id',
    position: [5080, 320],
    parameters: {{
      operation: 'executeQuery',
      query: {J(PERSIST_RUN_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.run_id, $json.apify_run_id, $json.start_ok_int ] }}}}') }}
    }},
    credentials: {{ postgres: newCredential('Postgres') }}
  }},
  output: [{{}}]
}});""")
out.append(f"""
const reattachRunNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Reattach Run',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(REATTACH_RUN_JS)} }},
    position: [5360, 320]
  }},
  output: [{{ apify_run_id: 'x' }}]
}});""")
out.append(f"""
const buildRunUrlNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Build Run URL',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(BUILD_RUN_URL_JS)} }},
    position: [5640, 320]
  }},
  output: [{{ run_url: 'u' }}]
}});""")
out.append("""
const getRunNode = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {
    name: 'Apify - Get Run',
    onError: 'continueRegularOutput',
    alwaysOutputData: true,
    position: [5920, 320],
    parameters: {
      method: 'GET',
      url: expr('{{ $json.run_url }}'),
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      options: { timeout: 60000 }
    },
    credentials: { httpHeaderAuth: newCredential('Apify') }
  },
  output: [{ data: { status: 'RUNNING' } }]
});""")
out.append(f"""
const pollCheckNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Poll Check',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(POLL_JS)} }},
    position: [6200, 320]
  }},
  output: [{{ finished: false, succeeded: false }}]
}});""")
out.append("""
const finGate = ifElse({
  version: 2.2,
  config: {
    name: 'Run Finished?',
    position: [6480, 320],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ $json.finished }}'), operator: { type: 'boolean', operation: 'true' } }],
        combinator: 'and'
      }
    }
  }
});""")
out.append("""
const waitNode = node({
  type: 'n8n-nodes-base.wait',
  version: 1.1,
  config: {
    name: 'Wait 15s',
    parameters: { amount: 15 },
    position: [6480, 560]
  },
  output: [{}]
});""")
out.append("""
const succGate = ifElse({
  version: 2.2,
  config: {
    name: 'Run Succeeded?',
    position: [6760, 320],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ $json.succeeded }}'), operator: { type: 'boolean', operation: 'true' } }],
        combinator: 'and'
      }
    }
  }
});""")
out.append(f"""
const buildDsUrlNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Build Dataset URL',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(BUILD_DS_URL_JS)} }},
    position: [7040, 320]
  }},
  output: [{{ dataset_url: 'u' }}]
}});""")
out.append("""
const getDatasetNode = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {
    name: 'Apify - Get Dataset',
    onError: 'continueRegularOutput',
    alwaysOutputData: true,
    position: [7320, 320],
    parameters: {
      method: 'GET',
      url: expr('{{ $json.dataset_url }}'),
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      options: { timeout: 120000, response: { response: { responseFormat: 'json' } } }
    },
    credentials: { httpHeaderAuth: newCredential('Apify') }
  },
  output: [{ fullName: 'x' }]
});""")
out.append(f"""
const parseNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Parse People',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(PARSE_JS)} }},
    position: [7600, 320]
  }},
  output: [{{ company_id: 'uuid', full_name: 'x' }}]
}});""")
out.append(f"""
const savePersonNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Save Person',
    position: [7880, 320],
    parameters: {{
      operation: 'executeQuery',
      query: {J(SAVE_PERSON_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.company_id, $json.full_name, $json.title, $json.linkedin_url, $json.save_flag, $json.raw_json, $json.source_url, $json.evidence_quote, $json.run_id, $json.id_hash, $json.charged ] }}}}') }}
    }},
    credentials: {{ postgres: newCredential('Postgres') }}
  }},
  output: [{{ outcome: 'inserted' }}]
}});""")
out.append(f"""
const rollupNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Company Rollup',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(ROLLUP_JS)} }},
    position: [8160, 320]
  }},
  output: [{{ company_id: 'uuid', detail_json: '{{}}' }}]
}});""")
out.append(f"""
const markCheckedNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Mark Checked + Events',
    position: [8440, 320],
    parameters: {{
      operation: 'executeQuery',
      query: {J(MARK_CHECKED_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.company_id, $json.run_id, $json.detail_json, $json.is_first, $json.act ] }}}}') }}
    }},
    credentials: {{ postgres: newCredential('Postgres') }}
  }},
  output: [{{ updated: 1 }}]
}});""")
out.append(f"""
const failItemsNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Build Failure Items',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(FAIL_ITEMS_JS)} }},
    position: [5080, 720]
  }},
  output: [{{ company_id: 'uuid', usage_usd: 0 }}]
}});""")
out.append(f"""
const failDbNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Release Claims + Failure Events',
    position: [5360, 720],
    parameters: {{
      operation: 'executeQuery',
      query: {J(FAIL_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.company_id, $json.run_id, $json.usage_usd, $json.apify_run_id, $json.is_first ] }}}}') }}
    }},
    credentials: {{ postgres: newCredential('Postgres') }}
  }},
  output: [{{ updated: 1 }}]
}});""")

out.append(f"""
const summaryEmptyNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Return - Summary (Batch Empty)',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(SUMMARY_JS)} }},
    position: [4240, 720]
  }},
  output: [{{ success: true, stage: 'SF6b', picked: 0 }}]
}});""")
out.append(f"""
const failItemsANode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Build Failure Items A',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(FAIL_ITEMS_JS)} }},
    position: [5080, 880]
  }},
  output: [{{ company_id: 'uuid', usage_usd: 0 }}]
}});""")
out.append(f"""
const failDbANode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Release Claims A',
    position: [5360, 880],
    parameters: {{
      operation: 'executeQuery',
      query: {J(FAIL_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.company_id, $json.run_id, $json.usage_usd, $json.apify_run_id, $json.is_first ] }}}}') }}
    }},
    credentials: {{ postgres: newCredential('Postgres') }}
  }},
  output: [{{ updated: 1 }}]
}});""")
out.append(f"""
const summaryFailANode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Return - Summary (Start Failed)',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(SUMMARY_JS)} }},
    position: [5640, 880]
  }},
  output: [{{ success: false, stage: 'SF6b', picked: 0 }}]
}});""")
out.append(f"""
const failItemsBNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Build Failure Items B',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(FAIL_ITEMS_JS)} }},
    position: [7040, 720]
  }},
  output: [{{ company_id: 'uuid', usage_usd: 0 }}]
}});""")
out.append(f"""
const failDbBNode = node({{
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {{
    name: 'DB - Release Claims B',
    position: [7320, 720],
    parameters: {{
      operation: 'executeQuery',
      query: {J(FAIL_SQL)},
      options: {{ queryReplacement: expr('{{{{ [ $json.company_id, $json.run_id, $json.usage_usd, $json.apify_run_id, $json.is_first ] }}}}') }}
    }},
    credentials: {{ postgres: newCredential('Postgres') }}
  }},
  output: [{{ updated: 1 }}]
}});""")
out.append(f"""
const summaryFailBNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Return - Summary (Run Failed)',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(SUMMARY_JS)} }},
    position: [7600, 720]
  }},
  output: [{{ success: false, stage: 'SF6b', picked: 0 }}]
}});""")
out.append(f"""
const summaryNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Return - Summary',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(SUMMARY_JS)} }},
    position: [8720, 320]
  }},
  output: [{{ success: true, stage: 'SF6b', picked: 0 }}]
}});""")

out.append(f"""
const fetchInputsNode = node({{
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {{
    name: 'Build Fetch Inputs',
    parameters: {{ mode: 'runOnceForAllItems', jsCode: {J(BUILD_FETCH_JS)} }},
    position: [5640, 320]
  }},
  output: [{{ apify_run_id: 'x', batch_json: '[]' }}]
}});""")
out.append("""
const callFetchNode = node({
  type: 'n8n-nodes-base.executeWorkflow',
  version: 1.2,
  config: {
    name: 'Call SF6c - People Fetch',
    parameters: {
      source: 'database',
      workflowId: { __rl: true, value: 'SF6C_PLACEHOLDER', mode: 'list', cachedResultName: 'SF6c v-next - People Fetch (poll + save)' },
      workflowInputs: { mappingMode: 'passthrough' },
      mode: 'once',
      options: { waitForSubWorkflow: true }
    },
    position: [5920, 320]
  },
  output: [{ success: true, stage: 'SF6b' }]
});""")
out.append("""
export default workflow('leadfinder-sf6b-vnext2', 'SF6b v-next.2 - LinkedIn People (Apify, dynamic)')
  .add(aboutNote)
  .add(subTrigger)
  .to(loadNode)
  .to(stageNode)
  .to(pickNode)
  .to(capGateNode)
  .to(hasWork
    .onTrue(buildNode
      .to(mcpSearch)
      .to(reattachANode)
      .to(mcpExtract)
      .to(reattachA2Node)
      .to(resolveNode)
      .to(markNode)
      .to(reattachBNode)
      .to(batchNode)
      .to(batchGate
        .onTrue(summaryEmptyNode)
        .onFalse(startNode
          .to(prepNode)
          .to(persistNode)
          .to(reattachRunNode)
          .to(fetchInputsNode)
          .to(callFetchNode))))
    .onFalse(blockedSummaryNode));
""")
code = '\n'.join(out) + '\n'
(BASE/'sf6b-vnext2.ts').write_text(code)
json.dump({"code": code, "name": "SF6b v-next.2 - LinkedIn People (Apify, dynamic)"}, open(BASE/'create-sf6b-vnext2.json', 'w'))
print('sf6b v-next.2 generated', len(code))
