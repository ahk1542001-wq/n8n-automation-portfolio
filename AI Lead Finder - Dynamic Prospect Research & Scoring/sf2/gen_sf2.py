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

ts = """import { workflow, node, trigger, sticky, newCredential, expr } from '@n8n/workflow-sdk';

const aboutNote = sticky("SF2 - Discovery, Google Maps via Apify. Input: { search_profile_id, profile_version, run_id, max_per_query }. Loads the approved search profile from Postgres, runs every apify_maps query x location from the profile through the Apify Google Places scraper (sync), and maps results into the common raw-lead candidate contract. Returns { success, count, candidates[] }. NO dedupe here - SF4 runs next, before any paid enrichment.", [], { color: 5 });

const subTrigger = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger',
  version: 1.1,
  config: {
    name: 'When Executed by Another Workflow',
    parameters: {
      workflowInputs: { values: [ { name: 'search_profile_id', type: 'string' }, { name: 'profile_version', type: 'number' }, { name: 'run_id', type: 'string' }, { name: 'max_per_query', type: 'number' } ] }
    },
    position: [40, 400]
  },
  output: [{ search_profile_id: 'uuid', profile_version: 1, run_id: '', max_per_query: 20 }]
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
    position: [320, 400]
  },
  output: [{ profile: { sources: [] } }]
});

const buildQueries = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Build Query List',
    parameters: { mode: 'runOnceForAllItems', jsCode: BUILDJS },
    position: [600, 400]
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
    position: [880, 400]
  },
  output: [{ title: 'Example Place', placeId: 'ChIJ...', categoryName: 'Cafe', city: 'Yangon', website: 'https://example.com', phone: '09...', totalScore: 4.5, reviewsCount: 120 }]
});

const mapCandidates = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Map to Candidates',
    parameters: { mode: 'runOnceForEachItem', jsCode: MAPJS },
    position: [1160, 400]
  },
  output: [{ source: 'apify_maps', name: 'Example Place', place_id: 'ChIJ...' }]
});

const collect = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Collect + Return',
    parameters: { mode: 'runOnceForAllItems', jsCode: COLLECTJS },
    position: [1440, 400]
  },
  output: [{ success: true, count: 0, candidates: [] }]
});

export default workflow('sf2-discovery-maps', 'SF2 - Discovery Maps (Apify)')
  .add(aboutNote)
  .add(subTrigger)
  .to(loadProfile)
  .to(buildQueries)
  .to(apifySearch)
  .to(mapCandidates)
  .to(collect);
"""
ts = ts.replace('BUILDJS', json.dumps(BUILD_JS)).replace('MAPJS', json.dumps(MAP_JS)).replace('COLLECTJS', json.dumps(COLLECT_JS))
open('sf2.ts', 'w').write(ts)
json.dump({"code": ts}, open('create-sf2.json', 'w'))
json.dump({"code": ts}, open('validate-sf2.json', 'w'))
print('generated', len(ts))
