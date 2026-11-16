// SF6 deterministic parsers — shared by the local harness and the SF6 Code nodes.
// No LLM. Verbatim-evidence only: an email is stored only if it appears in the
// fetched page text; a Facebook page is stored only if its name/slug shares a
// significant token with the company name.

function normTokens(s) {
  return String(s || '')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .split(/\s+/)
    .filter(w => w.length >= 3 && !STOPWORDS.has(w));
}
const STOPWORDS = new Set(['the', 'and', 'co', 'ltd', 'company', 'store', 'shop', 'hotel', 'resort', 'bangkok', 'yangon', 'thailand', 'myanmar', 'facebook', 'page', 'official']);
// Generic descriptor words: a match on ONE of these alone is not evidence the
// page belongs to the company (learned 2026-11-16: a mobile-training shop was
// matched to an unrelated hardware-training page on the word "training").
const GENERIC = new Set(['training', 'service', 'services', 'mobile', 'phone', 'computer', 'electronics', 'hardware', 'fashion', 'trading', 'enterprise', 'enterprises', 'solution', 'solutions', 'technology', 'technologies', 'digital', 'media', 'express', 'global', 'international', 'modern', 'center', 'centre', 'group', 'beauty', 'star', 'king', 'best', 'top', 'world', 'accessories', 'garment', 'textile', 'food', 'travel', 'tour', 'tours', 'clinic', 'school', 'academy', 'studio', 'salon', 'cafe', 'restaurant', 'bakery', 'pharmacy', 'mart', 'market', 'online']);

// results: Tavily search results [{title, url}] for query '"<name>" <location> facebook'
// Returns {facebook_url, matched_token} or null.
function pickFacebook(companyName, results) {
  const nameToks = new Set(normTokens(companyName));
  if (!nameToks.size || !Array.isArray(results)) return null;
  for (const r of results) {
    const url = String((r && r.url) || '');
    const m = url.match(/^https?:\/\/(?:www\.)?facebook\.com\/([^/?#]+)/i);
    if (!m) continue;
    const slug = decodeURIComponent(m[1]);
    if (['sharer', 'login', 'help', 'groups', 'watch', 'marketplace', 'gaming', 'profile.php'].includes(slug.toLowerCase())) continue;
    const candToks = new Set([...normTokens(slug.replace(/[-_.]/g, ' ')), ...normTokens(r.title || '')]);
    const matched = [];
    for (const t of nameToks) {
      if (candToks.has(t)) matched.push(t);
    }
    // Concatenated slugs (facebook.com/leobeautystudio): a name token of
    // length >= 4 appearing inside the slug counts as a match.
    const slugFlat = slug.toLowerCase().replace(/[^a-z0-9]/g, '');
    for (const t of nameToks) {
      if (!matched.includes(t) && t.length >= 4 && slugFlat.includes(t)) matched.push(t);
    }
    // Accept: any matched token is distinctive (not generic), OR >= 2 matched.
    const distinctive = matched.filter(t => !GENERIC.has(t));
    if (distinctive.length >= 1 || matched.length >= 2) {
      return { facebook_url: 'https://www.facebook.com/' + slug, matched_token: distinctive[0] || matched[0] };
    }
  }
  return null;
}

const EMAIL_RE = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const BAD_EMAIL = /^(noreply|no-reply|donotreply|mailer-daemon|postmaster)@/i;
const BAD_TLD_FILE = /\.(png|jpe?g|gif|svg|webp|css|js)$/i;
// text: extracted page text. Returns the first plausible business email or null.
function pickEmail(text) {
  if (!text) return null;
  const found = String(text).match(EMAIL_RE) || [];
  for (const e of found) {
    if (BAD_EMAIL.test(e) || BAD_TLD_FILE.test(e)) continue;
    if (/example\.(com|org|net)$/i.test(e)) continue;
    if (/^(your|user|name|email)@/i.test(e)) continue;
    return e;
  }
  return null;
}

// FB links inside extracted page text. Returns {facebook_url, matched_token} or null.
function pickFacebookFromText(companyName, text) {
  if (!text) return null;
  const urls = String(text).match(/https?:\/\/(?:www\.)?facebook\.com\/[A-Za-z0-9_.\-%]+/gi) || [];
  const results = urls.map(u => ({ url: u, title: '' }));
  return pickFacebook(companyName, results);
}

// Explicit size statements only: "25 employees", "team of 40", "120 rooms".
// Returns e.g. "25 employees" / "120 rooms" or null.
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

module.exports = { pickFacebook, pickEmail, pickFacebookFromText, pickSize, normTokens };
