// Canonical rubric classifier — IDENTICAL logic in SF7 detScore, SF1 Validate, WF00 gate.
// Returns the deterministic family a criterion belongs to, or 'needs_research'.
// v3 (F26, 2026-11-16): MATCHER_SYNONYMS_V1 — versioned normalised-phrase -> family map
// consulted before the regex families; location synonyms keep the locTargets guard.
// v2 (F25, 2026-11-16): category verify-text parsing handles negation — a category term
// preceded by a negation inside its clause is EXCLUDED and cannot trigger the category
// family; positive mentions in other clauses still count. Baseline v1 sha256:
// 027a61fb498af38d5e92d0af3dc2de27b114b351232a40dc226772804a8c718f
function categoryTerms(howToVerify) {
  const m = (howToVerify || '').match(/matches any of:\s*(.+)/i);
  if (!m) return null;
  const text = m[1].toLowerCase();
  const clauses = text
    .split(/\s+but\s+|\s+however\s+/)
    .flatMap(part => part.split(/[,;]/))
    .map(s => s.trim())
    .filter(Boolean);
  const include = [], exclude = [];
  for (const clause of clauses) {
    const neg = clause.match(/\b(not|no|never|without|isn't|isnt)\b/);
    if (neg) {
      const after = clause.slice(neg.index + neg[0].length).slice(0, 40).trim().replace(/^(a|an|the)\s+/, '').trim();
      if (after) exclude.push(after);
    } else {
      include.push(clause);
    }
  }
  return { include, exclude };
}
const MATCHER_VERSION = 'synonyms_v1';
const MATCHER_SYNONYMS_V1 = {
  'operates in target cities': 'location',
  'local presence in target markets': 'location',
  'target markets': 'location',
  'operates in target markets': 'location'
};
const KNOWN_FAMILIES = ['location', 'category', 'facebook', 'rating', 'review_volume', 'website', 'phone_contact'];
function normPhrase(s) {
  return String(s || '').toLowerCase().replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
}
function synonymFamily(rawName) {
  const v = MATCHER_SYNONYMS_V1[normPhrase(rawName)];
  if (v === undefined) return null;
  return KNOWN_FAMILIES.includes(v) ? v : 'unknown';
}
function classifyCriterion(crit, locTargets) {
  const name = (crit.name || '').toLowerCase();
  const verify = (crit.how_to_verify || '').toLowerCase();
  const both = name + ' ' + verify;
  if (name.includes('research-only')) return 'needs_research';
  const syn = synonymFamily(crit.name);
  if (syn === 'location') {
    return (locTargets && locTargets.length) ? 'location' : 'needs_research';
  }
  if (syn && syn !== 'unknown') return syn;
  if (/city|location|geograph|footprint|area|region/.test(name)) {
    return (locTargets && locTargets.length) ? 'location' : 'needs_research';
  }
  if (/category|property type|business type|firm type/.test(name)) {
    const parsed = categoryTerms(crit.how_to_verify);
    if (!parsed) return 'needs_research';
    return parsed.include.length ? 'category' : 'needs_research';
  }
  if (/facebook/.test(name)) return 'facebook';
  if (/rating/.test(name)) return 'rating';
  if (/review/.test(name) && /count|volume|number/.test(both)) return 'review_volume';
  if (/website/.test(name)) return 'website';
  if (/phone|contact/.test(name)) return 'phone_contact';
  return 'needs_research';
}
function coverageOf(fitCriteria, locTargets) {
  let det = 0, res = 0, contact = 0; const families = {};
  for (const c of (fitCriteria || [])) {
    const f = classifyCriterion(c, locTargets || []);
    families[c.name] = f;
    const pts = Number(c.max_points) || 0;
    if (f === 'needs_research') res += pts; else det += pts;
    if (f === 'website' || f === 'phone_contact') contact += pts;
  }
  return { deterministic_points: det, research_points: res, contact_points: contact, families };
}
module.exports = { classifyCriterion, coverageOf, categoryTerms };
