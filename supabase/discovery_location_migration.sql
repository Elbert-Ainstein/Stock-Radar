-- Add HQ location columns to discovery_candidates for globe visualization
ALTER TABLE discovery_candidates ADD COLUMN IF NOT EXISTS hq_city TEXT DEFAULT '';
ALTER TABLE discovery_candidates ADD COLUMN IF NOT EXISTS hq_state TEXT DEFAULT '';
ALTER TABLE discovery_candidates ADD COLUMN IF NOT EXISTS hq_country TEXT DEFAULT '';
