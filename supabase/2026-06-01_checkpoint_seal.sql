-- ═══════════════════════════════════════════════════════════════
-- CHECKPOINT SEAL — rescoped Async Checkpoint Feedback (P0 + P1)
-- 2026-06-01
--
-- Per CHECKPOINT_FEEDBACK_ASSESSMENT + RESCOPE_RESOLUTIONS:
-- we EXTEND the existing prediction_log / prediction_outcomes stack
-- rather than build a parallel thesis_predictions / thesis_outcomes
-- (the latter NAME-COLLIDES with the existing theses-linked table).
--
-- This migration is NOT auto-applied. Apply via the Supabase SQL editor.
-- ═══════════════════════════════════════════════════════════════

-- ── 1. New sealed-record fields on prediction_log ──────────────
-- All nullable so the existing engine write-path is unaffected
-- (rows it writes simply leave these NULL).

ALTER TABLE prediction_log ADD COLUMN IF NOT EXISTS system_version        text;     -- git short hash that produced the call
ALTER TABLE prediction_log ADD COLUMN IF NOT EXISTS reasoning_fingerprint jsonb DEFAULT '{}'::jsonb;  -- {dissenting_model, unresolved_questions, model_confidences, conviction, conviction_source}
ALTER TABLE prediction_log ADD COLUMN IF NOT EXISTS cohort_key            text;     -- derived: judgment prompt_versions + judgment-file hash
ALTER TABLE prediction_log ADD COLUMN IF NOT EXISTS version_cohort_break  boolean;  -- true if cohort_key changed vs the ticker's previous seal
-- FK-type fix (P0): socratic_analyses.id is BIGINT, not UUID. Link by bigint.
ALTER TABLE prediction_log ADD COLUMN IF NOT EXISTS socratic_analysis_id  bigint;   -- -> socratic_analyses(id), soft link (no hard FK to avoid migration coupling)

CREATE INDEX IF NOT EXISTS idx_prediction_log_cohort      ON prediction_log (cohort_key);
CREATE INDEX IF NOT EXISTS idx_prediction_log_socratic_id ON prediction_log (socratic_analysis_id);

-- ── 2. Date-pinning on prediction_outcomes (P0) ────────────────
-- The grader must record WHICH calendar date the close came from,
-- so an immutable grade can never silently use the wrong day.
ALTER TABLE prediction_outcomes ADD COLUMN IF NOT EXISTS actual_date_used date;

-- ── 3. Append-only guard on prediction_log (P1, Option A) ───────
-- Replace the permissive ALL policy with INSERT + SELECT only.
-- Effect: the anon key the app uses can append and read, but cannot
-- UPDATE or DELETE a sealed row. The logger's upsert(on_conflict=
-- ticker,run_id) keeps working because run_id is unique per run, so
-- it only ever INSERTs (no conflict -> no UPDATE attempted).
--
-- ESCAPE HATCH (deliberate, logged): a genuine correction — e.g. an
-- early extractor bug that sealed a malformed reasoning_fingerprint —
-- is made by a DATED service-role migration in this folder, never from
-- the app. Prefer appending a corrected row with a `supersedes` note in
-- reasoning_fingerprint over an in-place edit, so the original is kept
-- as evidence. The service_role key bypasses RLS for that rare path.
DROP POLICY IF EXISTS prediction_log_all ON prediction_log;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='prediction_log' AND policyname='prediction_log_insert') THEN
        CREATE POLICY prediction_log_insert ON prediction_log FOR INSERT WITH CHECK (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='prediction_log' AND policyname='prediction_log_select') THEN
        CREATE POLICY prediction_log_select ON prediction_log FOR SELECT USING (true);
    END IF;
    -- Intentionally NO update/delete policy => those operations are denied for non-service roles.
END $$;
