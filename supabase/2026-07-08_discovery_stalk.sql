-- 2026-07-08 — Lesson L2 first slice: STALK stance + trigger price.
-- Discovery mode's output is a stance with a stored trigger, NEVER a sized
-- position and NEVER a value of `conviction` (kill gate / UI pills / outcomes
-- seeding pattern-match on conviction — design constraint, L2).
-- Written by scripts/discovery_screens.py; trigger breaches surfaced by
-- scripts/refresh_prices.py (L5: alerts — pending orders, not sentiment).
--
-- Apply manually in the Supabase SQL editor (postgres role), then run the
-- verification query and paste the output back.

ALTER TABLE discovery_universe
  ADD COLUMN IF NOT EXISTS stance TEXT DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS trigger_price NUMERIC DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS stalk_evidence JSONB DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS stalk_updated_at TIMESTAMPTZ DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS trigger_breached_at TIMESTAMPTZ DEFAULT NULL;

COMMENT ON COLUMN discovery_universe.stance IS
  'L2 discovery stance (e.g. STALK). Deliberately separate from any conviction field.';
COMMENT ON COLUMN discovery_universe.trigger_price IS
  'Price at which a STALK becomes actionable; refresh_prices surfaces breaches.';

-- Verification (expect 5 rows):
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'discovery_universe'
  AND column_name IN ('stance','trigger_price','stalk_evidence',
                      'stalk_updated_at','trigger_breached_at');
