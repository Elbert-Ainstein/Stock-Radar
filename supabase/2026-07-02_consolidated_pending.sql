-- ═══════════════════════════════════════════════════════════════════════════
-- CONSOLIDATED PENDING MIGRATIONS — 2026-07-02 (consolidation sprint, Phase 1.4)
--
-- Combines the four migrations that were written between 2026-06-01 and
-- 2026-06-27 but never applied to the live DB (audit 2026-07-02 §4.3/§4.7),
-- plus the new quarantine flag for poisoned legacy prediction rows (1.5).
--
-- Idempotent (ADD COLUMN IF NOT EXISTS / guarded policies) — safe to re-run.
-- NOT auto-applied. Run in the Supabase SQL editor (postgres role, bypasses RLS).
--
-- Order matters only for section 4 (the quarantine UPDATE must precede the
-- append-only policy swap in section 5 conceptually; as postgres it works
-- either way, but keep the order for auditability).
-- ═══════════════════════════════════════════════════════════════════════════


-- ── 1. checkpoint_seal (2026-06-01) — seal fields on prediction_log ─────────
-- While these were missing, prediction_logger's old fixed 5-attempt strip
-- budget was exactly exhausted by these 5 columns, losing ENTIRE rows.

ALTER TABLE prediction_log ADD COLUMN IF NOT EXISTS system_version        text;
ALTER TABLE prediction_log ADD COLUMN IF NOT EXISTS reasoning_fingerprint jsonb DEFAULT '{}'::jsonb;
ALTER TABLE prediction_log ADD COLUMN IF NOT EXISTS cohort_key            text;
ALTER TABLE prediction_log ADD COLUMN IF NOT EXISTS version_cohort_break  boolean;
ALTER TABLE prediction_log ADD COLUMN IF NOT EXISTS socratic_analysis_id  bigint;

CREATE INDEX IF NOT EXISTS idx_prediction_log_cohort      ON prediction_log (cohort_key);
CREATE INDEX IF NOT EXISTS idx_prediction_log_socratic_id ON prediction_log (socratic_analysis_id);

-- Date-pinning on prediction_outcomes: record WHICH calendar date the close
-- came from, so an immutable grade can never silently use the wrong day.
ALTER TABLE prediction_outcomes ADD COLUMN IF NOT EXISTS actual_date_used date;


-- ── 2. theses columns (2026-06-03 / 2026-06-23 / 2026-06-27) ────────────────
-- Until these exist, run_thesis strip-and-retry drops all four on every write
-- (loud stderr warning, but the data is lost for that row).

-- D1: machine-readable archetype-routed kill-gate override
ALTER TABLE theses ADD COLUMN IF NOT EXISTS kill_gate_override jsonb;

-- Model D: vision bracket {engine_floor, vision_ceiling, vision_over_floor_x}
ALTER TABLE theses ADD COLUMN IF NOT EXISTS model_d_bracket jsonb;

-- Dual-system Step 1: the structural (Type A) axis
ALTER TABLE theses ADD COLUMN IF NOT EXISTS strategic_conviction text;
ALTER TABLE theses ADD COLUMN IF NOT EXISTS risk_adj_ev_ratio numeric;


-- ── 3. Quarantine flag (2026-07-02, sprint 1.5) ─────────────────────────────
-- The legacy engine pipeline wrote snapshot rows with all-zero targets and
-- ref prices (it read keys analyst.py never emits) plus fabricated ±30%
-- bands. Never delete (append-only evidence) — mark, so the grader skips.

ALTER TABLE prediction_log ADD COLUMN IF NOT EXISTS quarantined boolean NOT NULL DEFAULT false;
COMMENT ON COLUMN prediction_log.quarantined IS
  '2026-07-02: poisoned legacy engine-path snapshot (zero targets/ref price from a key mismatch in run_pipeline). Grader skips; kept as evidence, never deleted.';


-- ── 4. Mark existing junk rows ──────────────────────────────────────────────
-- Conservative WHERE: only rows that are provably ungradeable junk —
-- non-Socratic source (no soc- run prefix) AND a zero/null ref price or base
-- target. The grader additionally source-filters at read time, so anything
-- this UPDATE misses is still excluded from grading.

UPDATE prediction_log
SET quarantined = true
WHERE quarantined = false
  AND (run_id IS NULL OR run_id NOT LIKE 'soc-%')
  AND (COALESCE(current_price, 0) = 0 OR COALESCE(target_base, 0) = 0);


-- ── 5. Append-only guard on prediction_log (from 2026-06-01, Option A) ──────
-- Replace the permissive ALL policy with INSERT + SELECT only: the anon key
-- can append and read but cannot UPDATE or DELETE a sealed row. Corrections
-- happen only via dated service-role migrations in this folder.

DROP POLICY IF EXISTS prediction_log_all ON prediction_log;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='prediction_log' AND policyname='prediction_log_insert') THEN
        CREATE POLICY prediction_log_insert ON prediction_log FOR INSERT WITH CHECK (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='prediction_log' AND policyname='prediction_log_select') THEN
        CREATE POLICY prediction_log_select ON prediction_log FOR SELECT USING (true);
    END IF;
    -- Intentionally NO update/delete policy => denied for non-service roles.
END $$;


-- ── 6. VERIFICATION (run these; paste the output back) ──────────────────────
-- 6a. All new columns present? Expect 6 prediction_log + 4 theses rows.
SELECT table_name, column_name
FROM information_schema.columns
WHERE (table_name = 'prediction_log' AND column_name IN
        ('system_version','reasoning_fingerprint','cohort_key',
         'version_cohort_break','socratic_analysis_id','quarantined'))
   OR (table_name = 'theses' AND column_name IN
        ('kill_gate_override','model_d_bracket','strategic_conviction','risk_adj_ev_ratio'))
ORDER BY table_name, column_name;

-- 6b. prediction_outcomes date pin present? Expect 1 row.
SELECT column_name FROM information_schema.columns
WHERE table_name = 'prediction_outcomes' AND column_name = 'actual_date_used';

-- 6c. Quarantine census: how many rows were marked, and does the ripening
--     cohort (created <= now() - 30d) contain any UNquarantined non-Socratic rows?
--     Expect the last count to be 0.
SELECT
  COUNT(*) FILTER (WHERE quarantined)                                   AS quarantined_total,
  COUNT(*) FILTER (WHERE NOT quarantined AND run_id LIKE 'soc-%')       AS live_socratic_seals,
  COUNT(*) FILTER (WHERE NOT quarantined
                   AND (run_id IS NULL OR run_id NOT LIKE 'soc-%')
                   AND created_at <= now() - interval '30 days')        AS ripening_legacy_unquarantined
FROM prediction_log;

-- 6d. Append-only enforced? Expect exactly insert+select policies, no ALL.
SELECT policyname, cmd FROM pg_policies WHERE tablename = 'prediction_log' ORDER BY policyname;
