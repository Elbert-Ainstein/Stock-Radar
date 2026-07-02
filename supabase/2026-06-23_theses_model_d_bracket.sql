-- Model D integration (2026-06-23): store the optionality/vision bracket on each
-- thesis for transformational names — the vision CEILING alongside the engine FLOOR.
-- Additive and non-authoritative: it never overrides conviction/target.
--
-- Shape: {engine_floor, vision_ceiling, vision_over_floor_x}
--
-- Not auto-applied. Until applied, run_thesis schema-drift-strips the column
-- (the insert loop strips up to 5 unknown columns, so this + kill_gate_override
-- can both be missing without error).

ALTER TABLE theses ADD COLUMN IF NOT EXISTS model_d_bracket jsonb;
