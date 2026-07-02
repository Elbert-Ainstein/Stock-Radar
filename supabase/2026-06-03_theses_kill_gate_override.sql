-- D1 (2026-06-03): structured record of an archetype-routed kill-gate override.
-- When the post-processor relaxes a ratio-driven BROKEN for a regime-shift /
-- pre-revenue name, the override is stored as MACHINE-READABLE jsonb (not only a
-- prose note in kill_triggers) so the checkpoint grader reads the routed verdict,
-- not the raw "BROKEN", when it grades the thesis later.
--
-- Shape: {raw_verdict, routed_verdict, raw_position_pct, routed_position_pct,
--         risk_adj_ev_ratio, archetype, archetype_floor, uniform_threshold, reason}
--
-- Not auto-applied. Apply via the Supabase SQL editor. Until then run_thesis
-- schema-drift-strips the column (no error; the prose note in kill_triggers still
-- lands, and conviction/position already carry the routed values).

ALTER TABLE theses ADD COLUMN IF NOT EXISTS kill_gate_override jsonb;
