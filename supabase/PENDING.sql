-- ═══════════════════════════════════════════════════════════════════════════
-- ROLLING PENDING MIGRATIONS — the ONE file that is ever unapplied.
--
-- Pattern (2026-07-02, replaces per-change "run this in the SQL editor"):
--   * Every new migration is appended HERE (idempotent: IF NOT EXISTS only)
--     and also archived as its own dated file for history.
--   * Applied AUTOMATICALLY on merge to main by
--     .github/workflows/apply-migrations.yml — once the SUPABASE_DB_URL
--     secret exists. Until then, this file is the single thing to paste into
--     the SQL editor, whenever convenient (writers strip missing columns
--     loudly; nothing breaks in between).
--   * The whole file is always safe to re-run.
-- ═══════════════════════════════════════════════════════════════════════════

-- L4 (2026-07-02): parameter block each thesis verdict ran under.
ALTER TABLE theses ADD COLUMN IF NOT EXISTS run_parameters jsonb;

-- ── Verification (safe to run any time) ─────────────────────────────────────
SELECT column_name FROM information_schema.columns
WHERE table_name = 'theses'
  AND column_name IN ('run_parameters')
ORDER BY column_name;
