import json

BUILD_JS = r"""const trig = $('When Executed by Another Workflow').item.json || {};
const profile = ($input.item.json.profile) || {};
const pairs = [];
for (const s of (profile.sources || [])) {
  if (s.source !== 'apify_maps') continue;
  const locs = (s.locations && s.locations.length) ? s.locations : [null];
  for (const q of (s.queries || [])) for (const loc of locs) pairs.push({ search: q, location: loc });
}
const maxPer = trig.max_per_query || 20;
return pairs.map(p => ({ json: {
  search_profile_id: trig.search_profile_id || null,
  profile_version: trig.profile_version || 1,
  run_id: trig.run_id || null,
  search: p.search,
  location: p.location,
  max_per_query: maxPer,
  apify_input: {
    searchStringsArray: [p.search],
    locationQuery: p.location || '',
    maxCrawledPlacesPerSearch: maxPer,
    language: 'en',
    skipClosedPlaces: false,
    scrapePlaceDetailPage: false
  }
} }));"""

MAP_JS = r"""const p = $input.item.json || {};
return { json: {
  source: 'apify_maps',
  source_id: p.placeId || null,
  name: p.title || '',
  place_id: p.placeId || null,
  category: p.categoryName || null,
  location: p.city || p.address || null,
  website: p.website || null,
  phone: p.phone || null,
  rating: (p.totalScore === undefined ? null : p.totalScore),
  review_count: (p.reviewsCount === undefined ? null : p.reviewsCount),
  raw: p
} };"""

COLLECT_JS = r"""const cands = $input.all().map(i => i.json);
return { json: { success: true, count: cands.length, candidates: cands } };"""

IMPORT_JS = r"""const REQUIRED = ['company_name', 'domain', 'location', 'source_url'];
const rows = $input.all().map(i => i.json);
if (!rows.length) {
  return [{ json: { import_error: 'missing_header:company_name', missing_header: 'company_name', detail: 'import sheet returned no rows (headers not readable)' } }];
}
const keys = Object.keys(rows[0]);
const missing = REQUIRED.filter(h => !keys.includes(h));
if (missing.length) {
  return [{ json: { import_error: 'missing_header:' + missing[0], missing_header: missing[0] } }];
}
return rows.filter(r => String(r.company_name || '').trim()).map(r => {
  let d = String(r.domain || '').trim().toLowerCase().replace(/^https?:\/\//, '').replace(/^www\./, '');
  d = d.split('/')[0];
  return { json: {
    source: 'manual_import',
    source_id: null,
    name: String(r.company_name).trim(),
    place_id: null,
    category: null,
    location: String(r.location || '').trim(),
    website: d ? 'https://' + d : null,
    domain: d || null,
    phone: null,
    rating: null,
    review_count: null,
    source_url: String(r.source_url || '').trim(),
    raw: r
  } };
});"""

HALT_RETURN_JS = r"""const err = ($('Validate + Normalise Import').first().json || {}).import_error || 'unknown';
return [{ json: { success: false, count: 0, candidates: [], import_error: err } }];"""

CACHE_KEY_JS = r"""const trig = $('When Executed by Another Workflow').item.json || {};
const pairs = $input.all().map(i => i.json);
const pairKey = pairs.map(x => String(x.search || '').toLowerCase().trim() + '|' + String(x.location || '').toLowerCase().trim()).join(';');
const material = (trig.search_profile_id || '') + '@' + (trig.profile_version || 1) + '|' + pairKey + '|' + (trig.max_per_query || 20);
return [{ json: {
  cache_key_material: material,
  profile_material: (trig.search_profile_id || '') + '@' + (trig.profile_version || 1),
  query_norm: pairs.map(x => String(x.search || '').toLowerCase().trim()).join(';'),
  location_norm: pairs.map(x => String(x.location || '').toLowerCase().trim()).join(';'),
  pairs,
  search_profile_id: trig.search_profile_id || null,
  profile_version: trig.profile_version || 1,
  run_id: trig.run_id || null,
  max_per_query: trig.max_per_query || 20,
  ttl_hours: (trig.discovery_cache_ttl_hours === undefined || trig.discovery_cache_ttl_hours === null || trig.discovery_cache_ttl_hours === '' ? 24 : Number(trig.discovery_cache_ttl_hours))
} }];"""

LOOKUP_SQL = """
SELECT c.result_company_ids AS candidates, c.discovered_count AS count, true AS hit
FROM discovery_cache c
WHERE c.cache_key = encode(sha256($1::bytea), 'hex') AND c.expires_at > now()
UNION ALL
SELECT NULL, NULL, false
WHERE NOT EXISTS (SELECT 1 FROM discovery_cache c WHERE c.cache_key = encode(sha256($1::bytea), 'hex') AND c.expires_at > now())
""".strip()

HIT_LEDGER_SQL = """
INSERT INTO cost_ledger (run_id, workflow, provider, event_type, units, cost_usd, company_id, idempotency_key)
VALUES ($1, 'SF2 v-next.1', 'apify', 'cache_hit_zero', 0, 0, NULL, 'sf2:cachehit:' || $1 || ':' || $2)
ON CONFLICT (idempotency_key) DO NOTHING
""".strip()

EMIT_CACHED_JS = r"""const row = ($('DB - Cache Lookup (F29)').first().json) || {};
const key = ($('Cache Key (F29)').first().json) || {};
const cands = row.candidates || [];
return [{ json: { success: true, count: cands.length, candidates: cands, cache_hit: true, run_id: key.run_id || null } }];"""

EXPAND_JS = r"""const key = ($('Cache Key (F29)').first().json) || {};
return (key.pairs || []).map(x => ({ json: x }));"""

PREP_STORE_JS = r"""const key = ($('Cache Key (F29)').first().json) || {};
const coll = $input.first().json || {};
return [{ json: {
  cache_key_material: key.cache_key_material, profile_material: key.profile_material,
  query_norm: key.query_norm, location_norm: key.location_norm, max_per_query: key.max_per_query,
  ttl_hours: key.ttl_hours, candidates: coll.candidates || [], count: coll.count || 0,
  candidates_json: JSON.stringify(coll.candidates || [])
} }];"""

STORE_SQL = """
INSERT INTO discovery_cache (cache_key, query_norm, location_norm, radius_m, profile_hash, result_company_ids, discovered_count, expires_at)
VALUES (encode(sha256($1::bytea), 'hex'), $2, $3, $4, encode(sha256($5::bytea), 'hex'), $6::jsonb, $7, now() + ($8::text || ' hours')::interval)
ON CONFLICT (cache_key) DO UPDATE SET result_company_ids = EXCLUDED.result_company_ids, discovered_count = EXCLUDED.discovered_count, created_at = now(), expires_at = EXCLUDED.expires_at
""".strip()

RETURN_STORE_JS = r"""const prep = ($('Prep Cache Store (F29)').first().json) || {};
return [{ json: { success: true, count: prep.count || 0, candidates: prep.candidates || [], cache_hit: false } }];"""

ts = """import { workflow, node, trigger, sticky, ifElse, newCredential, expr } from '@n8n/workflow-sdk';

const aboutNote = sticky("SF2 v-next - Discovery with two sources (F27). Places path = the original SF2 (profile-driven Apify Google Places). Manual-import path: reads an import Sheet with exact headers company_name, domain, location, source_url; a missing header halts the branch with a Gmail draft naming the header; rows are normalised (domain lowercased, www./scheme stripped, location trimmed) and emitted in the SAME candidate contract with source='manual_import' + source_url, merging into the same Collect return so SF4 dedupe handles both paths identically. Input adds discovery_source ('places' default | 'manual_import'), import_sheet_id, import_tab.", [], { color: 5 });

const subTrigger = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger',
  version: 1.1,
  config: {
    name: 'When Executed by Another Workflow',
    parameters: {
      workflowInputs: { values: [ { name: 'search_profile_id', type: 'string' }, { name: 'profile_version', type: 'number' }, { name: 'run_id', type: 'string' }, { name: 'max_per_query', type: 'number' }, { name: 'discovery_source', type: 'string' }, { name: 'import_sheet_id', type: 'string' }, { name: 'import_tab', type: 'string' }, { name: 'discovery_cache_ttl_hours', type: 'number' } ] }
    },
    position: [40, 400]
  },
  output: [{ search_profile_id: 'uuid', profile_version: 1, run_id: '', max_per_query: 20, discovery_source: 'places', import_sheet_id: '', import_tab: 'Import', discovery_cache_ttl_hours: 24 }]
});

const routeSource = ifElse({
  version: 2.2,
  config: {
    name: 'Import Source?',
    position: [320, 400],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ $json.discovery_source === "manual_import" }}'), operator: { type: 'boolean', operation: 'true' } }],
        combinator: 'and'
      }
    }
  }
});

const loadProfile = node({
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {
    name: 'DB - Load Search Profile',
    parameters: {
      operation: 'executeQuery',
      query: "SELECT profile FROM search_profiles WHERE id = $1::uuid",
      options: { queryReplacement: expr('{{ [ $json.search_profile_id ] }}') }
    },
    credentials: { postgres: newCredential('Supabase Postgres') },
    position: [600, 560]
  },
  output: [{ profile: { sources: [] } }]
});

const buildQueries = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Build Query List',
    parameters: { mode: 'runOnceForAllItems', jsCode: BUILDJS },
    position: [880, 560]
  },
  output: [{ search: 'cafe', location: 'Yangon', apify_input: {} }]
});

const apifySearch = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {
    name: 'Apify - Maps Search',
    parameters: {
      method: 'POST',
      url: 'https://api.apify.com/v2/acts/compass~crawler-google-places/run-sync-get-dataset-items',
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendBody: true,
      contentType: 'json',
      specifyBody: 'json',
      jsonBody: expr('{{ $json.apify_input }}'),
      options: { timeout: 300000, batching: { batch: { batchSize: 1, batchInterval: 5000 } } }
    },
    credentials: { httpHeaderAuth: newCredential('Apify') },
    position: [1160, 560]
  },
  output: [{ title: 'Example Place', placeId: 'ChIJ...', categoryName: 'Cafe', city: 'Yangon', website: 'https://example.com', phone: '09...', totalScore: 4.5, reviewsCount: 120 }]
});

const mapCandidates = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Map to Candidates',
    parameters: { mode: 'runOnceForEachItem', jsCode: MAPJS },
    position: [1440, 560]
  },
  output: [{ source: 'apify_maps', name: 'Example Place', place_id: 'ChIJ...' }]
});

const collect = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Collect + Return',
    parameters: { mode: 'runOnceForAllItems', jsCode: COLLECTJS },
    position: [1720, 560]
  },
  output: [{ success: true, count: 0, candidates: [] }]
});


const cacheKeyNode = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Cache Key (F29)',
    parameters: { mode: 'runOnceForAllItems', jsCode: CACHEKEYJS },
    position: [1160, 560]
  },
  output: [{ cache_key_material: 'x', pairs: [] }]
});

const cacheLookup = node({
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {
    name: 'DB - Cache Lookup (F29)',
    parameters: {
      operation: 'executeQuery',
      query: LOOKUPSQL,
      options: { queryReplacement: expr('{{ [ $json.cache_key_material ] }}') }
    },
    credentials: { postgres: newCredential('Supabase Postgres') },
    position: [1440, 560],
    executeOnce: true
  },
  output: [{ hit: false }]
});

const cacheHitIf = ifElse({
  version: 2.2,
  config: {
    name: 'Cache Hit?',
    position: [1720, 560],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ $json.hit }}'), operator: { type: 'boolean', operation: 'true' } }],
        combinator: 'and'
      }
    }
  }
});

const hitLedger = node({
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {
    name: 'DB - Cache Hit Ledger (F29)',
    parameters: {
      operation: 'executeQuery',
      query: HITLEDSQL,
      options: { queryReplacement: expr("{{ [ $('Cache Key (F29)').first().json.run_id, $('Cache Key (F29)').first().json.cache_key_material ] }}") }
    },
    credentials: { postgres: newCredential('Supabase Postgres') },
    position: [2000, 440]
  },
  output: [{ id: 1 }]
});

const emitCached = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Emit Cached (F29)',
    parameters: { mode: 'runOnceForAllItems', jsCode: EMITCACHEDJS },
    position: [2280, 440]
  },
  output: [{ success: true, count: 0, candidates: [], cache_hit: true }]
});

const expandPairs = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Expand Pairs (F29)',
    parameters: { mode: 'runOnceForAllItems', jsCode: EXPANDJS },
    position: [2000, 680]
  },
  output: [{ search: 'cafe', apify_input: {} }]
});

const prepStore = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Prep Cache Store (F29)',
    parameters: { mode: 'runOnceForAllItems', jsCode: PREPSTOREJS },
    position: [2280, 680]
  },
  output: [{ cache_key_material: 'x', candidates_json: '[]', count: 0 }]
});

const cacheStore = node({
  type: 'n8n-nodes-base.postgres',
  version: 2.6,
  config: {
    name: 'DB - Cache Store (F29)',
    parameters: {
      operation: 'executeQuery',
      query: STORESQL,
      options: { queryReplacement: expr('{{ [ $json.cache_key_material, $json.query_norm, $json.location_norm, $json.max_per_query, $json.profile_material, $json.candidates_json, $json.count, $json.ttl_hours ] }}') }
    },
    credentials: { postgres: newCredential('Supabase Postgres') },
    position: [2560, 680]
  },
  output: [{ cache_key: 'x' }]
});

const returnStore = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Return - After Cache Store (F29)',
    parameters: { mode: 'runOnceForAllItems', jsCode: RETURNSTOREJS },
    position: [2840, 680]
  },
  output: [{ success: true, count: 0, candidates: [], cache_hit: false }]
});

const sheetsRead = node({
  type: 'n8n-nodes-base.googleSheets',
  version: 4.2,
  config: {
    name: 'Sheet - Read Import Tab',
    position: [600, 240],
    parameters: {
      resource: 'sheet',
      operation: 'read',
      documentId: { __rl: true, mode: 'id', value: expr('{{ $json.import_sheet_id }}') },
      sheetName: { __rl: true, mode: 'name', value: expr('{{ $json.import_tab }}') },
      options: {}
    },
    credentials: { googleSheetsOAuth2: newCredential('Google Sheets') }
  },
  output: [{ company_name: 'Example Co', domain: 'example.com', location: 'Yangon', source_url: 'https://example.com' }]
});

const normaliseImport = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Validate + Normalise Import',
    parameters: { mode: 'runOnceForAllItems', jsCode: IMPORTJS },
    position: [880, 240]
  },
  output: [{ source: 'manual_import', name: 'Example Co' }]
});

const importOk = ifElse({
  version: 2.2,
  config: {
    name: 'Import OK?',
    position: [1160, 240],
    parameters: {
      conditions: {
        options: { caseSensitive: true, typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ !!$json.import_error }}'), operator: { type: 'boolean', operation: 'true' } }],
        combinator: 'and'
      }
    }
  }
});

const gmailHalt = node({
  type: 'n8n-nodes-base.gmail',
  version: 2.1,
  config: {
    name: 'Gmail - Import Halt Draft (NEVER SENDS)',
    position: [1440, 120],
    parameters: {
      resource: 'draft',
      operation: 'create',
      sendTo: 'owner@example.com',
      subject: 'SF2 import halted - missing header',
      emailType: 'text',
      message: expr('{{ "The manual-import branch halted before reading any company rows. Missing required header: " + $json.missing_header + ". Required headers (exact): company_name, domain, location, source_url. No discovery ran and nothing was spent." }}'),
      options: {}
    },
    credentials: { gmailOAuth2: newCredential('Gmail') }
  },
  output: [{ id: 'draft-id' }]
});

const haltReturn = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Return - Import Halted',
    parameters: { mode: 'runOnceForAllItems', jsCode: HALTJS },
    position: [1720, 120]
  },
  output: [{ success: false, count: 0, candidates: [] }]
});

const collectImport = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Collect Import + Return',
    parameters: { mode: 'runOnceForAllItems', jsCode: COLLECTJS },
    position: [1440, 320]
  },
  output: [{ success: true, count: 0, candidates: [] }]
});

export default workflow('leadfinder-sf2-vnext1', 'SF2 v-next.1 - Discovery Maps + Manual Import + Cache (F27+F29)')
  .add(aboutNote)
  .add(subTrigger)
  .to(routeSource
    .onTrue(sheetsRead.to(normaliseImport).to(importOk
      .onTrue(gmailHalt.to(haltReturn))
      .onFalse(collectImport)))
    .onFalse(loadProfile.to(buildQueries).to(cacheKeyNode).to(cacheLookup).to(cacheHitIf
      .onTrue(hitLedger.to(emitCached))
      .onFalse(expandPairs.to(apifySearch).to(mapCandidates).to(collect).to(prepStore).to(cacheStore).to(returnStore)))));
"""
ts = ts.replace('CACHEKEYJS', json.dumps(CACHE_KEY_JS)).replace('LOOKUPSQL', json.dumps(LOOKUP_SQL)).replace('HITLEDSQL', json.dumps(HIT_LEDGER_SQL)).replace('EMITCACHEDJS', json.dumps(EMIT_CACHED_JS)).replace('EXPANDJS', json.dumps(EXPAND_JS)).replace('PREPSTOREJS', json.dumps(PREP_STORE_JS)).replace('STORESQL', json.dumps(STORE_SQL)).replace('RETURNSTOREJS', json.dumps(RETURN_STORE_JS))
ts = ts.replace('BUILDJS', json.dumps(BUILD_JS)).replace('MAPJS', json.dumps(MAP_JS)).replace('COLLECTJS', json.dumps(COLLECT_JS)).replace('IMPORTJS', json.dumps(IMPORT_JS)).replace('HALTJS', json.dumps(HALT_RETURN_JS))
open('sf2-vnext1.ts', 'w').write(ts)
json.dump({"code": ts, "name": "SF2 v-next.1 - Discovery Maps + Manual Import + Cache (F27+F29)"}, open('create-sf2-vnext1.json', 'w'))
print('generated', len(ts))
