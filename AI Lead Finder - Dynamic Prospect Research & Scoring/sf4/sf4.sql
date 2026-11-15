-- SF4 Dedupe + Exclusion — single deterministic statement.
-- Franchise rule (Wonder review fix, 2026-11-15): a shared domain alone NEVER makes a
-- duplicate — domain matches require the same location too, so distinct chain branches
-- (same domain, different city) are separate companies. Pairs with the
-- companies_domain_loc_uq index on (lower(domain), location).
-- $1 = JSON payload: {search_profile_id, profile_version, run_id, candidates:[...]}
-- Candidates arrive PRE-NORMALISED (normalised_name, domain lowercased/host-extracted).
WITH p AS (SELECT $1::jsonb AS j),
cand AS (
  SELECT t.idx,
         t.elem->>'source' AS source,
         t.elem->>'source_id' AS source_id,
         t.elem->>'name' AS name,
         t.elem->>'normalised_name' AS normalised_name,
         t.elem->>'domain' AS domain,
         t.elem->>'place_id' AS place_id,
         t.elem->>'registration_no' AS registration_no,
         t.elem->>'category' AS category,
         t.elem->>'location' AS location,
         t.elem->>'website' AS website,
         t.elem->>'phone' AS phone,
         (t.elem->>'rating')::numeric AS rating,
         (t.elem->>'review_count')::int AS review_count,
         t.elem->'raw' AS raw,
         (p.j->>'search_profile_id')::uuid AS spid,
         (p.j->>'profile_version')::int AS ver,
         (p.j->>'run_id')::uuid AS runid,
         coalesce(t.elem->>'place_id',
                  lower(t.elem->>'domain') || '|' || coalesce(t.elem->>'location',''),
                  (t.elem->>'normalised_name') || '|' || coalesce(t.elem->>'location','')) AS dkey
  FROM p, jsonb_array_elements(p.j->'candidates') WITH ORDINALITY AS t(elem, idx)
),
supp AS (
  SELECT c.idx FROM cand c
  WHERE EXISTS (SELECT 1 FROM suppressions s WHERE
    (s.match_type = 'place_id' AND c.place_id IS NOT NULL AND s.match_value = c.place_id)
    OR (s.match_type = 'domain' AND c.domain IS NOT NULL AND s.match_value = lower(c.domain))
    OR (s.match_type = 'name_location' AND s.match_value = c.normalised_name || '|' || coalesce(c.location,'')))
),
exist AS (
  SELECT c.idx,
         (SELECT co.id FROM companies co
          WHERE (c.place_id IS NOT NULL AND co.place_id = c.place_id)
             OR (c.domain IS NOT NULL AND lower(co.domain) = lower(c.domain)
                 AND coalesce(co.location,'') = coalesce(c.location,''))
             OR (co.normalised_name = c.normalised_name AND coalesce(co.location,'') = coalesce(c.location,''))
          ORDER BY co.created_at LIMIT 1) AS company_id
  FROM cand c WHERE c.idx NOT IN (SELECT idx FROM supp)
),
ins AS (
  INSERT INTO companies (search_profile_id, profile_version, run_id, name, normalised_name,
                         domain, place_id, registration_no, category, location, website,
                         phone, rating, review_count, source, source_ids, raw_payload, status)
  SELECT spid, ver, runid, name, normalised_name, domain, place_id, registration_no, category,
         location, website, phone, rating, review_count, source,
         jsonb_build_object(source, source_id), raw, 'new'
  FROM (SELECT DISTINCT ON (dkey) * FROM cand
        WHERE idx NOT IN (SELECT idx FROM supp)
          AND idx NOT IN (SELECT idx FROM exist WHERE company_id IS NOT NULL)
        ORDER BY dkey, idx) firsts
  ON CONFLICT DO NOTHING
  RETURNING id, name, place_id, domain, normalised_name, location
),
ins_d AS (
  SELECT id, coalesce(place_id, lower(domain) || '|' || coalesce(location,''), normalised_name || '|' || coalesce(location,'')) AS dkey
  FROM ins
),
firsts AS (
  SELECT dkey, min(idx) AS idx FROM cand
  WHERE idx NOT IN (SELECT idx FROM supp)
    AND idx NOT IN (SELECT idx FROM exist WHERE company_id IS NOT NULL)
  GROUP BY dkey
)
SELECT c.name,
       CASE WHEN c.idx IN (SELECT idx FROM supp) THEN 'suppressed'
            WHEN c.idx IN (SELECT idx FROM exist WHERE company_id IS NOT NULL) THEN 'duplicate'
            WHEN c.idx IN (SELECT idx FROM firsts) AND c.dkey IN (SELECT dkey FROM ins_d) THEN 'inserted'
            ELSE 'duplicate' END AS outcome,
       CASE WHEN c.idx IN (SELECT idx FROM exist WHERE company_id IS NOT NULL)
              THEN (SELECT company_id FROM exist WHERE idx = c.idx)
            WHEN c.dkey IN (SELECT dkey FROM ins_d)
              THEN (SELECT id FROM ins_d WHERE dkey = c.dkey)
            ELSE NULL END AS company_id
FROM cand c
ORDER BY c.idx;
