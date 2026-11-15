// Canonical rubric classifier — IDENTICAL logic in SF7 detScore, SF1 Validate, WF00 v8 gate.
// Returns the deterministic family a criterion belongs to, or 'needs_research'.
function classifyCriterion(crit, locTargets) {
  const name = (crit.name || '').toLowerCase();
  const verify = (crit.how_to_verify || '').toLowerCase();
  const both = name + ' ' + verify;
  if (name.includes('research-only')) return 'needs_research';
  if (/city|location|geograph|footprint|area|region/.test(name)) {
    return (locTargets && locTargets.length) ? 'location' : 'needs_research';
  }
  if (/category|property type|business type|firm type/.test(name)) {
    const m = (crit.how_to_verify || '').match(/matches any of:\s*(.+)/i);
    if (!m) return 'needs_research';
    const terms = m[1].split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
    return terms.length ? 'category' : 'needs_research';
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
module.exports = { classifyCriterion, coverageOf };
