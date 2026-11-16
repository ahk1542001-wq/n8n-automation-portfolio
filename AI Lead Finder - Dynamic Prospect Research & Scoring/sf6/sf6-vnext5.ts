import { workflow, node, trigger, sticky, ifElse, expr } from '@n8n/workflow-sdk';
const aboutNote = sticky("SF6 v-next - Contact Waterfall (owner-approved 2026-11-16). For scored companies (fit >= contact_min_fit, cap max_contact_companies, atomic claim, enrichment-once): (1) Facebook page via Tavily search with deterministic name match, (2) website + /contact extract for verbatim emails, FB links and stated size, (3) provider reveal SLOT - counted as provider_pending when provider_enabled and no email found; the Apollo HTTP node lands when the owner creates the Apollo credential (free-plan API access to be verified). Phone already lives on companies from Places and is surfaced by SF8 v-next.5. Every Tavily call writes cost_ledger rows (search $0.008, extract $0.008); spend_cap_usd honoured before any paid node. No send node anywhere.", [], { color: 5 });

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
});

const spentNode = node({
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {
    name: 'DB - Load Spent',
    position: [320, 400],
    parameters: {
      operation: 'executeQuery',
      query: "SELECT COALESCE(SUM(cost_usd), 0)::float AS spent_usd FROM cost_ledger WHERE run_id = $1",
      options: { queryReplacement: expr('{{ [ $json.run_id || \'\' ] }}') }
    },
    credentials: { postgres: newCredential('Postgres') }
  },
  output: [{ spent_usd: 0 }]
});

const stageNode = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Stage Context',
    parameters: { mode: 'runOnceForAllItems', jsCode: "const t = $('When Executed by Another Workflow').first().json;\nconst spent = Number($input.first().json.spent_usd || 0);\nreturn [{ json: {\n  search_profile_id: t.search_profile_id,\n  profile_version: Number(t.profile_version || 1),\n  run_id: t.run_id || '',\n  contact_min_fit: Number(t.contact_min_fit ?? 30),\n  max_contact_companies: Number(t.max_contact_companies ?? 10),\n  spend_cap_usd: (t.spend_cap_usd === undefined || t.spend_cap_usd === null || t.spend_cap_usd === '') ? null : Number(t.spend_cap_usd),\n  provider_enabled: t.provider_enabled === true,\n  spent_usd: spent\n} }];" },
    position: [600, 400]
  },
  output: [{ run_id: '', spent_usd: 0 }]
});

const pickNode = node({
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {
    name: 'DB - Pick + Claim + Audit',
    position: [880, 400],
    parameters: {
      operation: 'executeQuery',
      query: "WITH cand AS (\n  SELECT c.id, c.name, c.location, c.website, c.phone, s.fit_score,\n         ROW_NUMBER() OVER (ORDER BY s.fit_score DESC, c.id ASC) AS rn\n  FROM companies c\n  JOIN scores s ON s.company_id = c.id\n    AND s.search_profile_id = $1 AND s.profile_version = $2\n  WHERE s.fit_score >= $3\n    AND c.contact_enriched_at IS NULL\n    AND (c.contact_claimed_at IS NULL OR c.contact_claimed_at < now() - interval '1 hour')\n),\naudit AS (\n  INSERT INTO selection_audit (run_id, workflow, company_id, rank, fit_score, cutoff, selection_reason, is_first_skipped)\n  SELECT $5, 'SF6', id::text, rn::int, fit_score, $3,\n         CASE WHEN rn <= $4 THEN 'selected' ELSE 'cap_reached' END,\n         (rn = $4 + 1)\n  FROM cand WHERE rn <= $4 + 1\n  ON CONFLICT DO NOTHING\n  RETURNING 1\n),\nclaim AS (\n  UPDATE companies c\n  SET contact_claimed_at = now(), contact_claim_run_id = $5\n  FROM cand\n  WHERE c.id = cand.id AND cand.rn <= $4\n  RETURNING c.id AS company_id, cand.name, cand.location, cand.website, cand.phone, cand.fit_score AS fit\n)\nSELECT company_id::text AS company_id, name, location, website, phone, fit, false AS empty_run FROM claim\nUNION ALL\nSELECT NULL, NULL, NULL, NULL, NULL, NULL, true AS empty_run\nWHERE NOT EXISTS (SELECT 1 FROM claim)",
      options: { queryReplacement: expr('{{ [ $json.search_profile_id, $json.profile_version, $json.contact_min_fit, $json.max_contact_companies, $json.run_id ] }}') }
    },
    credentials: { postgres: newCredential('Postgres') }
  },
  output: [{ company_id: 'uuid', empty_run: false }]
});

const capGateNode = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Cap Gate',
    parameters: { mode: 'runOnceForAllItems', jsCode: "const ctx = $('Stage Context').first().json;\nconst rows = $input.all().map(i => i.json);\nconst picked = rows.filter(r => !r.empty_run);\nconst EST_PER_COMPANY = ctx.provider_enabled ? 0.026 : 0.016;\nconst cap = ctx.spend_cap_usd;\nconst blocked = cap !== null && picked.length > 0 && (ctx.spent_usd + EST_PER_COMPANY) > cap;\nif (!picked.length) {\n  return [{ json: { has_work: false, empty_run: true, cap_blocked: false, picked: 0, run_id: ctx.run_id } }];\n}\nreturn picked.map(r => ({ json: Object.assign({}, r, {\n  has_work: !blocked, cap_blocked: blocked, empty_run: false,\n  run_id: ctx.run_id, search_profile_id: ctx.search_profile_id,\n  profile_version: ctx.profile_version, provider_enabled: ctx.provider_enabled\n}) }));" },
    position: [1160, 400]
  },
  output: [{ has_work: true, cap_blocked: false }]
});

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
});

const buildNode = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Build Jobs',
    parameters: { mode: 'runOnceForAllItems', jsCode: "function contactUrl(w) {\n  const base = String(w).replace(/\\/+$/, '');\n  return base + '/contact';\n}\nreturn $input.all().map(i => {\n  const j = i.json;\n  const website = j.website || '';\n  const urls = website ? [website, contactUrl(website)] : [];\n  return { json: Object.assign({}, j, {\n    has_website: !!website,\n    mcp_fb: JSON.stringify({ query: '\"' + j.name + '\" ' + (j.location || '') + ' facebook', search_depth: 'basic', max_results: 5 }),\n    mcp_extract: JSON.stringify({ urls: urls, extract_depth: 'basic' })\n  }) };\n});" },
    position: [1720, 320]
  },
  output: [{ company_id: 'uuid', mcp_fb: '{}', mcp_extract: '{}' }]
});

const mcpFb = node({
  type: '@n8n/n8n-nodes-langchain.mcpClient',
  version: 1.1,
  config: {
    name: "Tavily MCP - Search Facebook",
    position: [2000, 320],
    parameters: { serverTransport: "httpStreamable", endpointUrl: "https://mcp.tavily.com/mcp/", authentication: "mcpOAuth2Api", inputMode: "json", options: {"timeout": 120000, "convertToBinary": false}, tool: {"__rl": true, "mode": "list", "value": "tavily_search", "cachedResultName": "tavily_search"}, jsonInput: expr('{{ $json.mcp_fb }}') },
    credentials: { mcpOAuth2Api: newCredential('Tavily MCP (generic)') }
  },
  output: [{}]
});

const reattachANode = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Reattach A',
    parameters: { mode: 'runOnceForAllItems', jsCode: "const jobs = $('Build Jobs').all().map(i => i.json);\nreturn $input.all().map((item, idx) => {\n  const job = jobs[idx] || {};\n  let t = '';\n  try { t = typeof item.json === 'string' ? item.json : JSON.stringify(item.json); } catch (e) { t = String(item.json); }\n  return { json: Object.assign({}, job, { fb_text: t }) };\n});" },
    position: [2280, 320]
  },
  output: [{ company_id: 'uuid', fb_text: '' }]
});

const mcpExtract = node({
  type: '@n8n/n8n-nodes-langchain.mcpClient',
  version: 1.1,
  config: {
    name: "Tavily MCP - Extract Site",
    position: [2560, 320],
    onError: 'continueRegularOutput',
    parameters: { serverTransport: "httpStreamable", endpointUrl: "https://mcp.tavily.com/mcp/", authentication: "mcpOAuth2Api", inputMode: "json", options: {"timeout": 120000, "convertToBinary": false}, tool: {"__rl": true, "mode": "list", "value": "tavily_extract", "cachedResultName": "tavily_extract"}, jsonInput: expr('{{ $json.mcp_extract }}') },
    credentials: { mcpOAuth2Api: newCredential('Tavily MCP (generic)') }
  },
  output: [{}]
});

const reattachBNode = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Reattach B',
    parameters: { mode: 'runOnceForAllItems', jsCode: "const prev = $('Reattach A').all().map(i => i.json);\nreturn $input.all().map((item, idx) => {\n  const p = prev[idx] || {};\n  let t = '';\n  const j = item.json || {};\n  if (!j.error && !j.message) {\n    try { t = typeof j === 'string' ? j : JSON.stringify(j); } catch (e) { t = String(j); }\n  }\n  return { json: Object.assign({}, p, { extract_text: t, extract_attempted: !!p.has_website }) };\n});" },
    position: [2840, 320]
  },
  output: [{ company_id: 'uuid', extract_text: '' }]
});

const parseNode = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Parse Contacts',
    parameters: { mode: 'runOnceForAllItems', jsCode: "const STOPWORDS = new Set(['the','and','co','ltd','company','store','shop','hotel','resort','bangkok','yangon','thailand','myanmar','facebook','page','official']);\nfunction normTokens(s) {\n  return String(s || '').toLowerCase().replace(/[^\\p{L}\\p{N}\\s]/gu, ' ').split(/\\s+/).filter(w => w.length >= 3 && !STOPWORDS.has(w));\n}\nconst GENERIC = new Set(['training','service','services','mobile','phone','computer','electronics','hardware','fashion','trading','enterprise','enterprises','solution','solutions','technology','technologies','digital','media','express','global','international','modern','center','centre','group','beauty','star','king','best','top','world','accessories','garment','textile','food','travel','tour','tours','clinic','school','academy','studio','salon','cafe','restaurant','bakery','pharmacy','mart','market','online']);\nfunction pickFacebook(companyName, results) {\n  const nameToks = new Set(normTokens(companyName));\n  if (!nameToks.size || !Array.isArray(results)) return null;\n  for (const r of results) {\n    const url = String((r && r.url) || '');\n    const m = url.match(/^https?:\\/\\/(?:www\\.)?facebook\\.com\\/([^/?#]+)/i);\n    if (!m) continue;\n    const slug = decodeURIComponent(m[1]);\n    if (['sharer','login','help','groups','watch','marketplace','gaming','profile.php'].includes(slug.toLowerCase())) continue;\n    const candToks = new Set([...normTokens(slug.replace(/[-_.]/g, ' ')), ...normTokens(r.title || '')]);\n    const matched = [];\n    for (const t of nameToks) { if (candToks.has(t)) matched.push(t); }\n    const slugFlat = slug.toLowerCase().replace(/[^a-z0-9]/g, '');\n    for (const t of nameToks) { if (!matched.includes(t) && t.length >= 4 && slugFlat.includes(t)) matched.push(t); }\n    const distinctive = matched.filter(t => !GENERIC.has(t));\n    if (distinctive.length >= 1 || matched.length >= 2) {\n      return { facebook_url: 'https://www.facebook.com/' + slug, matched_token: distinctive[0] || matched[0] };\n    }\n  }\n  return null;\n}\nfunction pickFacebookFromText(companyName, text) {\n  if (!text) return null;\n  const urls = String(text).match(/https?:\\/\\/(?:www\\.)?facebook\\.com\\/[A-Za-z0-9_.\\-%]+/gi) || [];\n  return pickFacebook(companyName, urls.map(u => ({ url: u, title: '' })));\n}\nconst EMAIL_RE = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}/g;\nfunction pickEmail(text) {\n  if (!text) return null;\n  const found = String(text).match(EMAIL_RE) || [];\n  for (const e of found) {\n    if (/^(noreply|no-reply|donotreply|mailer-daemon|postmaster)@/i.test(e)) continue;\n    if (/\\.(png|jpe?g|gif|svg|webp|css|js)$/i.test(e)) continue;\n    if (/example\\.(com|org|net)$/i.test(e)) continue;\n    if (/^(your|user|name|email)@/i.test(e)) continue;\n    return e;\n  }\n  return null;\n}\nfunction pickSize(text) {\n  if (!text) return null;\n  const s = String(text);\n  let m = s.match(/(\\d{1,4})\\s*(?:\\+\\s*)?(employees|staff members|team members)/i);\n  if (m) return m[1] + ' ' + m[2].toLowerCase();\n  m = s.match(/team of\\s*(\\d{1,4})/i);\n  if (m) return m[1] + ' team members';\n  m = s.match(/(\\d{1,4})\\s*(?:\\+\\s*)?(rooms|guest rooms)/i);\n  if (m) return m[1] + ' ' + m[2].toLowerCase();\n  return null;\n}\nfunction searchResults(text) {\n  try {\n    const outer = JSON.parse(text);\n    const inner = typeof outer === 'string' ? JSON.parse(outer) : outer;\n    if (inner && Array.isArray(inner.results)) return inner.results;\n    if (inner && inner.content) {\n      const c = typeof inner.content === 'string' ? JSON.parse(inner.content) : inner.content;\n      if (c && Array.isArray(c.results)) return c.results;\n    }\n  } catch (e) {}\n  return null;\n}\nreturn $input.all().map(i => {\n  const j = i.json;\n  let fb = null;\n  const res = searchResults(j.fb_text || '');\n  if (res) fb = pickFacebook(j.name, res);\n  if (!fb) fb = pickFacebookFromText(j.name, j.fb_text || '');\n  if (!fb) fb = pickFacebookFromText(j.name, j.extract_text || '');\n  const email = pickEmail(j.extract_text || '');\n  const size = pickSize(j.extract_text || '');\n  return { json: {\n    company_id: j.company_id, run_id: j.run_id, name: j.name,\n    facebook_url: fb ? fb.facebook_url : '',\n    email: email || '',\n    company_size: size || '',\n    fb_found: !!fb, email_found: !!email, size_found: !!size,\n    extract_attempted: !!j.extract_attempted,\n    provider_enabled: !!j.provider_enabled\n  } };\n});" },
    position: [3120, 320]
  },
  output: [{ company_id: 'uuid', facebook_url: '', email: '', fb_found: false }]
});

const provJobsNode = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Build Provider Jobs',
    parameters: { mode: 'runOnceForAllItems', jsCode: "function domainOf(w) {\n  let s = String(w || '').trim().toLowerCase();\n  if (!s) return '';\n  s = s.replace(/^https?:\\/\\//, '').replace(/^www\\./, '');\n  s = s.split('/')[0].split('?')[0].split('#')[0].split(':')[0];\n  if (!s || s.includes('facebook.') || s.includes('instagram.') || s.includes('linktr.ee') || s.includes('google.') || s.includes('g.page')) return '';\n  return s;\n}\nconst sites = $('Reattach B').all().map(i => i.json);\nreturn $('Parse Contacts').all().map((i, idx) => {\n  const j = i.json;\n  const website = (sites[idx] && sites[idx].website) || '';\n  const domain = domainOf(website);\n  const need = j.provider_enabled === true && !!domain && (!j.email || !j.company_size);\n  return { json: Object.assign({}, j, {\n    website, domain, apollo_need: need,\n    phone_new: '', provider_used: false,\n    size_source: j.company_size ? 'website' : ''\n  }) };\n});" },
    position: [3260, 320]
  },
  output: [{ company_id: 'uuid', apollo_need: false }]
});

const apolloNode = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {
    name: 'Apollo - Org Enrich',
    onError: 'continueRegularOutput',
    position: [3540, 320],
    parameters: {
      method: 'POST',
      url: 'https://api.apollo.io/api/v1/organizations/enrich',
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendBody: true,
      contentType: 'json',
      specifyBody: 'json',
      jsonBody: expr('{{ JSON.stringify({ domain: $json.domain }) }}'),
      options: { timeout: 30000 }
    },
    credentials: { httpHeaderAuth: newCredential('Apollo') }
  },
  output: [{ organization: { name: 'x' } }]
});

const mergeNode = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Merge Provider (Apollo)',
    parameters: { mode: 'runOnceForAllItems', jsCode: "const jobs = $('Build Provider Jobs').all().map(i => i.json).filter(j => j.apollo_need === true);\nreturn $input.all().map((item, idx) => {\n  const base = Object.assign({}, jobs[idx] || {});\n  const org = (item.json && item.json.organization) || null;\n  if (org) {\n    base.provider_used = true;\n    if (!base.facebook_url && org.facebook_url) base.facebook_url = String(org.facebook_url);\n    if (!base.company_size && org.estimated_num_employees) { base.company_size = String(org.estimated_num_employees); base.size_source = 'apollo'; }\n    if (org.phone) base.phone_new = String(org.phone);\n  }\n  return { json: base };\n});" },
    position: [3680, 320]
  },
  output: [{ company_id: 'uuid', provider_used: false }]
});

const save2Node = node({
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {
    name: 'DB - Save Contacts (No Provider)',
    position: [3540, 560],
    parameters: {
      operation: 'executeQuery',
      query: "WITH u AS (\n  UPDATE companies SET\n    facebook_url = CASE WHEN (facebook_url IS NULL OR facebook_url = '') AND NULLIF($3, '') IS NOT NULL THEN $3 ELSE facebook_url END,\n    email = CASE WHEN (email IS NULL OR email = '') AND NULLIF($4, '') IS NOT NULL THEN $4 ELSE email END,\n    email_source = CASE WHEN (email IS NULL OR email = '') AND NULLIF($4, '') IS NOT NULL THEN 'website' ELSE email_source END,\n    company_size = CASE WHEN (company_size IS NULL OR company_size = '') AND NULLIF($5, '') IS NOT NULL THEN $5 ELSE company_size END,\n    size_source = CASE WHEN (company_size IS NULL OR company_size = '') AND NULLIF($5, '') IS NOT NULL THEN $9 ELSE size_source END,\n    phone = COALESCE(NULLIF(phone, ''), NULLIF($7, '')),\n    contact_enriched_at = now()\n  WHERE id = $1 AND contact_claim_run_id = $2\n  RETURNING id\n),\nl1 AS (\n  INSERT INTO cost_ledger (run_id, workflow, provider, event_type, units, cost_usd, company_id, idempotency_key)\n  VALUES ($2, 'SF6', 'tavily', 'charge', 1, 0.008, $1::text, 'sf6:search:' || $2 || ':' || $1::text)\n  ON CONFLICT (idempotency_key) DO NOTHING\n  RETURNING 1\n),\nl2 AS (\n  INSERT INTO cost_ledger (run_id, workflow, provider, event_type, units, cost_usd, company_id, idempotency_key)\n  SELECT $2, 'SF6', 'tavily', 'charge', 1, 0.008, $1::text, 'sf6:extract:' || $2 || ':' || $1::text\n  WHERE $6 = 1\n  ON CONFLICT (idempotency_key) DO NOTHING\n  RETURNING 1\n),\nl3 AS (\n  INSERT INTO cost_ledger (run_id, workflow, provider, event_type, units, cost_usd, company_id, idempotency_key)\n  SELECT $2, 'SF6', 'people_finder', 'estimate', 1, 0.01, $1::text, 'sf6:apollo:' || $2 || ':' || $1::text\n  WHERE $8 = 1\n  ON CONFLICT (idempotency_key) DO NOTHING\n  RETURNING 1\n)\nSELECT (SELECT count(*) FROM u)::int AS updated",
      options: { queryReplacement: expr('{{ [ $json.company_id, $json.run_id, $json.facebook_url || \'\', $json.email || \'\', $json.company_size || \'\', ($json.extract_attempted === true ? 1 : 0), $json.phone_new || \'\', ($json.provider_used === true ? 1 : 0), $json.size_source || \'website\'] }}') }
    },
    credentials: { postgres: newCredential('Postgres') }
  },
  output: [{ updated: 1 }]
});

const summary2Node = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Return - Summary (No Provider)',
    parameters: { mode: 'runOnceForAllItems', jsCode: "const parsed = $('Parse Contacts').all().map(i => i.json);\nlet provUsed = 0;\ntry { provUsed = $('Merge Provider (Apollo)').all().filter(m => m.json.provider_used).length; } catch (e) {}\nconst pending = parsed.filter(p => p.provider_enabled && !p.email_found).length;\nreturn [{ json: {\n  success: true, stage: 'SF6',\n  picked: parsed.length,\n  fb_found: parsed.filter(p => p.fb_found).length,\n  emails_found: parsed.filter(p => p.email_found).length,\n  size_found: parsed.filter(p => p.size_found).length,\n  provider_used: provUsed,\n  provider_pending: Math.max(0, pending - provUsed),\n  tavily_credits: parsed.length + parsed.filter(p => p.extract_attempted).length\n} }];" },
    position: [3820, 560]
  },
  output: [{ success: true, stage: 'SF6', picked: 0 }]
});

const provGate = ifElse({
  version: 2.2,
  config: {
    name: 'Apollo Needed?',
    position: [3400, 320],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ $json.apollo_need }}'), operator: { type: 'boolean', operation: 'true' } }],
        combinator: 'and'
      }
    }
  }
});


const saveNode = node({
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {
    name: 'DB - Save Contacts',
    position: [3820, 320],
    parameters: {
      operation: 'executeQuery',
      query: "WITH u AS (\n  UPDATE companies SET\n    facebook_url = CASE WHEN (facebook_url IS NULL OR facebook_url = '') AND NULLIF($3, '') IS NOT NULL THEN $3 ELSE facebook_url END,\n    email = CASE WHEN (email IS NULL OR email = '') AND NULLIF($4, '') IS NOT NULL THEN $4 ELSE email END,\n    email_source = CASE WHEN (email IS NULL OR email = '') AND NULLIF($4, '') IS NOT NULL THEN 'website' ELSE email_source END,\n    company_size = CASE WHEN (company_size IS NULL OR company_size = '') AND NULLIF($5, '') IS NOT NULL THEN $5 ELSE company_size END,\n    size_source = CASE WHEN (company_size IS NULL OR company_size = '') AND NULLIF($5, '') IS NOT NULL THEN $9 ELSE size_source END,\n    phone = COALESCE(NULLIF(phone, ''), NULLIF($7, '')),\n    contact_enriched_at = now()\n  WHERE id = $1 AND contact_claim_run_id = $2\n  RETURNING id\n),\nl1 AS (\n  INSERT INTO cost_ledger (run_id, workflow, provider, event_type, units, cost_usd, company_id, idempotency_key)\n  VALUES ($2, 'SF6', 'tavily', 'charge', 1, 0.008, $1::text, 'sf6:search:' || $2 || ':' || $1::text)\n  ON CONFLICT (idempotency_key) DO NOTHING\n  RETURNING 1\n),\nl2 AS (\n  INSERT INTO cost_ledger (run_id, workflow, provider, event_type, units, cost_usd, company_id, idempotency_key)\n  SELECT $2, 'SF6', 'tavily', 'charge', 1, 0.008, $1::text, 'sf6:extract:' || $2 || ':' || $1::text\n  WHERE $6 = 1\n  ON CONFLICT (idempotency_key) DO NOTHING\n  RETURNING 1\n),\nl3 AS (\n  INSERT INTO cost_ledger (run_id, workflow, provider, event_type, units, cost_usd, company_id, idempotency_key)\n  SELECT $2, 'SF6', 'people_finder', 'estimate', 1, 0.01, $1::text, 'sf6:apollo:' || $2 || ':' || $1::text\n  WHERE $8 = 1\n  ON CONFLICT (idempotency_key) DO NOTHING\n  RETURNING 1\n)\nSELECT (SELECT count(*) FROM u)::int AS updated",
      options: { queryReplacement: expr('{{ [ $json.company_id, $json.run_id, $json.facebook_url || \'\', $json.email || \'\', $json.company_size || \'\', ($json.extract_attempted === true ? 1 : 0), $json.phone_new || \'\', ($json.provider_used === true ? 1 : 0), $json.size_source || \'website\'] }}') }
    },
    credentials: { postgres: newCredential('Postgres') }
  },
  output: [{ updated: 1 }]
});

const summaryNode = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Return - Summary',
    parameters: { mode: 'runOnceForAllItems', jsCode: "const parsed = $('Parse Contacts').all().map(i => i.json);\nlet provUsed = 0;\ntry { provUsed = $('Merge Provider (Apollo)').all().filter(m => m.json.provider_used).length; } catch (e) {}\nconst pending = parsed.filter(p => p.provider_enabled && !p.email_found).length;\nreturn [{ json: {\n  success: true, stage: 'SF6',\n  picked: parsed.length,\n  fb_found: parsed.filter(p => p.fb_found).length,\n  emails_found: parsed.filter(p => p.email_found).length,\n  size_found: parsed.filter(p => p.size_found).length,\n  provider_used: provUsed,\n  provider_pending: Math.max(0, pending - provUsed),\n  tavily_credits: parsed.length + parsed.filter(p => p.extract_attempted).length\n} }];" },
    position: [3960, 320]
  },
  output: [{ success: true, stage: 'SF6', picked: 0 }]
});

const capLedgerNode = node({
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {
    name: 'DB - Cap Blocked Ledger',
    position: [1720, 560],
    parameters: {
      operation: 'executeQuery',
      query: "INSERT INTO cost_ledger (run_id, workflow, provider, event_type, units, cost_usd, company_id, idempotency_key)\nVALUES ($1, 'SF6', 'tavily', 'cap_blocked', 1, 0.016, $2, 'sf6:cap:' || $1 || ':' || $2)\nON CONFLICT (idempotency_key) DO NOTHING",
      options: { queryReplacement: expr('{{ [ $json.run_id, $json.company_id || \'\' ] }}') }
    },
    credentials: { postgres: newCredential('Postgres') }
  },
  output: [{}]
});

const blockedSummaryNode = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Return - Blocked/Empty Summary',
    parameters: { mode: 'runOnceForAllItems', jsCode: "const rows = $input.all().map(i => i.json);\nconst first = rows[0] || {};\nreturn [{ json: {\n  success: true, stage: 'SF6',\n  picked: 0, fb_found: 0, emails_found: 0, size_found: 0, provider_pending: 0, tavily_credits: 0,\n  empty_run: !!first.empty_run, cap_blocked: !!first.cap_blocked\n} }];" },
    position: [2000, 560]
  },
  output: [{ success: true, stage: 'SF6', picked: 0, cap_blocked: false }]
});

export default workflow('leadfinder-sf6-vnext5', 'Lead Finder - SF6 Contact Waterfall v-next.5 (fill guards)')
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
      .to(provJobsNode)
      .to(provGate
        .onTrue(apolloNode
          .to(mergeNode)
          .to(saveNode)
          .to(summaryNode))
        .onFalse(save2Node
          .to(summary2Node))))
    .onFalse(capLedgerNode
      .to(blockedSummaryNode)));
