-- ═══════════════════════════════════════════════════════════════
-- SEED — wave_health for AI Waves 0/2/3/5
-- 2026-05-20  (Phase 5.5 — wave health populated with watch_signals
--              per feedback_watch_vs_break)
--
-- Seeds the most active AI revolution waves with structured health data
-- that the Socratic engine will inject as [WAVE_CONTEXT]. Each row links
-- to macro_environment.id=1 (the current stagflation_risk regime), so the
-- macro_translation and regime_playbook reflect today's regime.
--
-- The watch_signals jsonb is the key pattern from feedback_watch_vs_break:
-- observable cycle-shift metrics, NOT binary fire/no-fire triggers. For
-- generational competition (LITE 200G vs COHR 400G EML) and cycle-turn
-- detection (storage inventory + lead times), the system needs leading
-- indicators tracked numerically over time, not single-trigger alerts.
--
-- Run AFTER: 2026-05-20_phase5_5_macro_wave.sql, 2026-05-20_macro_seed.sql
-- ═══════════════════════════════════════════════════════════════

-- ────────────────────────────────────────────────────────────────
-- Wave 0 — Equipment (CAMT, KLA, KLIC dynamics)
-- ────────────────────────────────────────────────────────────────

INSERT INTO wave_health (
    wave_id, macro_env_id,
    momentum_score, momentum_label, crowding_score, avg_forward_pe, pe_vs_5yr_mean,
    macro_beta, beta_methodology, macro_translation, why_drivers, regime_playbook,
    differentiation, watch_signals
)
SELECT
    w.id, (SELECT id FROM current_macro_environment),
    1.45, 'elevated', 'medium', 36.0, '~40% above',
    1.8,
    'LLM analogy from 2022 semiconductor correction (SOX -34% peak-to-trough); equipment names typically 1.5-2.0x SOX beta',
    'In current stagflation_risk regime, SPX -10-15% → Wave 0 -18 to -27% with CAMT and KLIC potentially -25 to -35% due to higher momentum',
    'Equipment names ran with AI capex narrative. Multiple compression on rate-hike-fear is the main downside vector. CAMT has structural 3D microbump moat KLA admits cannot match — buffers against multiple compression but not against capex digestion if hyperscalers blink.',
    'In stagflation regime, equipment names with named-customer locked-in orders outperform horizontal exposure plays. CAMT/KLIC with HBM pipeline visibility (CAMT $260M HBM locked) are more resilient than KLA at peak consensus.',
    '[
        {"ticker": "CAMT",  "resilience": "high",       "reason": "3D microbump moat + $260M HBM pipeline locked + H2 acceleration",
         "trailing_12mo_return": 0.42, "trailing_18mo_return": 0.78},
        {"ticker": "KLA",   "resilience": "medium-high", "reason": "peak consensus ($194B, 20 analysts Buy), strong franchise but priced",
         "trailing_12mo_return": 0.18, "trailing_18mo_return": 0.55},
        {"ticker": "KLIC",  "resilience": "medium",     "reason": "TCB bonding for CoWoS, exposure to hyperscaler capex cycle",
         "trailing_12mo_return": 0.55, "trailing_18mo_return": 1.20},
        {"ticker": "ASML",  "resilience": "high",       "reason": "EUV monopoly, consensus but structurally irreplaceable",
         "trailing_12mo_return": 0.25, "trailing_18mo_return": 0.60}
    ]'::jsonb,
    '{
        "hbm_qualification_wins": {"metric": "named hyperscaler HBM design wins per quarter", "current": "ramp accelerating", "threshold_bullish": "≥2 new wins/quarter", "threshold_bearish": "0 wins for 2 consecutive quarters"},
        "cowos_capacity_booked": {"metric": "TSMC CoWoS capacity booking ratio", "current": "60% booked by NVDA alone", "watch": "any unbooking >5%"},
        "kla_3d_metrology_announce": {"metric": "KLA product announcement matching CAMT 3D microbump accuracy", "current": "no public announce", "if_fires": "CAMT moat erosion confirmed"},
        "equipment_lead_times": {"metric": "ASML/AMAT/LRCX lead times in earnings calls", "current": "tight 30+ weeks", "threshold_bearish": "softening to <20 weeks"}
    }'::jsonb
FROM waves w
JOIN revolutions r ON r.id = w.revolution_id
WHERE r.name_cn = 'AI革命' AND w.name_cn = '设备'
ON CONFLICT DO NOTHING;


-- ────────────────────────────────────────────────────────────────
-- Wave 2 — Optical (LITE/COHR — the generational watch case)
-- ────────────────────────────────────────────────────────────────

INSERT INTO wave_health (
    wave_id, macro_env_id,
    momentum_score, momentum_label, crowding_score, avg_forward_pe, pe_vs_5yr_mean,
    macro_beta, beta_methodology, macro_translation, why_drivers, regime_playbook,
    differentiation, watch_signals
)
SELECT
    w.id, (SELECT id FROM current_macro_environment),
    3.50, 'extreme', 'high', 65.0, '~150% above',
    2.3,
    'LLM analogy from 2022 semiconductor correction adjusted for momentum overshoot. LITE at +900% in 18 months → individual beta likely 2.8-3.2x SPX in real correction',
    'In current stagflation_risk regime, SPX -10-15% → Wave 2 -23 to -35% on average; LITE specifically -30 to -45% due to extreme momentum unwinding',
    'Momentum unwind primary driver (LITE/COHR ran 5-20x). Profit-taking on 20x runs by long-term holders. Multiple compression from 60x+ forward P/E. Crowded institutional positioning — most-owned AI hardware trade. Contracted backlog (LITE $42B) protects revenue but not stock price in unwind.',
    'Generational competition is a WATCH, not a BREAK. LITE owns current-gen 200G EML for 1.6T (revenue today); COHR positioning 400G D-EML for next-gen 3.2T (revenue 2027+). Customer transition timing determines outcome, not technology existence. In stagflation regime, contracted-backlog names (LITE) outperform uncontracted names (smaller transceiver makers like AAOI) within the same wave.',
    '[
        {"ticker": "LITE", "resilience": "high",   "reason": "$42B contracted backlog protects revenue; vertical InP integration; current-gen 200G EML monopoly",
         "trailing_12mo_return": 9.43, "trailing_18mo_return": 12.50},
        {"ticker": "COHR", "resilience": "medium", "reason": "own 400G D-EML for next-gen; vertically integrated; NVDA $2B partnership; less contracted than LITE",
         "trailing_12mo_return": 1.45, "trailing_18mo_return": 2.10},
        {"ticker": "AAOI", "resilience": "low",    "reason": "no contracted backlog; 441% YTD on competitive position vs LITE/COHR; unprofitable on $600M revenue",
         "trailing_12mo_return": 4.41, "trailing_18mo_return": 4.80}
    ]'::jsonb,
    '{
        "gen_mix_order_flow": {
            "metric": "1.6T vs 3.2T order mix at hyperscaler design wins (per earnings call commentary)",
            "current": "1.6T dominant, 3.2T pre-revenue",
            "watch_for_break": "3.2T design wins announced at tier-1 hyperscaler AND 1.6T order flow decelerates >15% QoQ — coincident, not either-alone"
        },
        "eml_inventory_at_module_assemblers": {
            "metric": "EML laser inventory at module makers (LITE 10-Q + industry channel checks)",
            "current": "tight",
            "threshold_bearish": "inventory builds >2 quarters consecutive — signals demand digestion ahead"
        },
        "cohr_400g_qualification": {
            "metric": "COHR 400G D-EML qualification wins at tier-1 hyperscalers (Microsoft, Google, Meta, Amazon)",
            "current": "no public qualifications yet",
            "if_fires": "watch for coincident LITE 1.6T order deceleration"
        },
        "hyperscaler_dual_sourcing_language": {
            "metric": "explicit dual-sourcing mentions in hyperscaler capex calls",
            "current": "ambiguous",
            "threshold_bearish": "explicit dual-source commitment from any tier-1 = single-source moat erosion"
        },
        "lite_lead_times": {
            "metric": "LITE quoted lead times in 10-Q",
            "current": "long",
            "threshold_bearish": "shortening lead times signals demand softening"
        }
    }'::jsonb
FROM waves w
JOIN revolutions r ON r.id = w.revolution_id
WHERE r.name_cn = 'AI革命' AND w.name_cn = '光互联'
ON CONFLICT DO NOTHING;


-- ────────────────────────────────────────────────────────────────
-- Wave 3 — Storage (SNDK/MU + cycle indicators per BUILD_PLAN §F)
-- ────────────────────────────────────────────────────────────────

INSERT INTO wave_health (
    wave_id, macro_env_id,
    momentum_score, momentum_label, crowding_score, avg_forward_pe, pe_vs_5yr_mean,
    macro_beta, beta_methodology, macro_translation, why_drivers, regime_playbook,
    differentiation, watch_signals
)
SELECT
    w.id, (SELECT id FROM current_macro_environment),
    1.85, 'elevated', 'medium', 14.5, '~25% above',
    1.6,
    'Memory historically 1.4-1.8x SOX beta in corrections; classic cyclical with multi-quarter draw-down patterns',
    'In current stagflation_risk regime, SPX -10-15% → Wave 3 -16 to -24% on average; mid-cycle position means moderate but not extreme beta',
    'Memory is cyclical, not secular. SNDK/MU contracted backlog and HBM pricing are mid-cycle. Six classic turn-signals (below) are the leading indicators of when this wave shifts from harvest to decline. None firing as of May 2026; estimated peak H2 2026 to H1 2027.',
    'In stagflation regime, memory names with HBM exposure (MU) outperform pure-NAND names (SNDK partial) because HBM is supply-constrained and AI-tethered while consumer NAND faces consumer-spending headwinds. Watch the turn signals — when 3+ fire, exit before consensus.',
    '[
        {"ticker": "SNDK", "resilience": "medium", "reason": "$42B contracted backlog at 78% gross margins (datacenter SSD post-spinoff economics underpricing); cyclical exposure",
         "trailing_12mo_return": 1.85, "trailing_18mo_return": 2.40},
        {"ticker": "MU",   "resilience": "medium", "reason": "HBM #3 with US-based scarcity premium; data still contaminated per project_mu_data_bug",
         "trailing_12mo_return": 1.20, "trailing_18mo_return": 1.85}
    ]'::jsonb,
    '{
        "_methodology": "The six turn-signals from BUILD_PLAN-83703dd5 addendum §F. NONE firing as of 2026-05-20. When 3+ fire, the cycle is turning; exit positions before this is consensus. Track these monthly.",
        "dram_inventory_weeks": {"metric": "DRAM inventory weeks at major customers", "current": "tight 6-8 weeks", "threshold_bearish": ">12 weeks for 2+ months"},
        "nand_inventory_weeks": {"metric": "NAND inventory weeks at major customers", "current": "tight 8-10 weeks", "threshold_bearish": ">14 weeks for 2+ months"},
        "lead_times": {"metric": "memory lead times in earnings calls", "current": "extended", "threshold_bearish": "shortening to historical mean"},
        "price_qoq": {"metric": "DRAM and NAND spot+contract price QoQ", "current": "rising", "threshold_bearish": "first QoQ decline after consecutive rises"},
        "cancel_to_book": {"metric": "cancel-to-book ratio at memory suppliers", "current": "low", "threshold_bearish": "rising above 0.10"},
        "distributor_stock": {"metric": "channel/distributor stock levels", "current": "tight", "threshold_bearish": "building above historical norm"}
    }'::jsonb
FROM waves w
JOIN revolutions r ON r.id = w.revolution_id
WHERE r.name_cn = 'AI革命' AND w.name_cn = '存储'
ON CONFLICT DO NOTHING;


-- ────────────────────────────────────────────────────────────────
-- Wave 5 — Cooling (VRT integrated chain)
-- ────────────────────────────────────────────────────────────────

INSERT INTO wave_health (
    wave_id, macro_env_id,
    momentum_score, momentum_label, crowding_score, avg_forward_pe, pe_vs_5yr_mean,
    macro_beta, beta_methodology, macro_translation, why_drivers, regime_playbook,
    differentiation, watch_signals
)
SELECT
    w.id, (SELECT id FROM current_macro_environment),
    1.05, 'elevated', 'medium', 28.0, '~50% above',
    1.7,
    'New emerging chokepoint; analog: 2022 datacenter spend correction was ~25% deeper than SPX for capex-exposed names; VRT integrated chain has $15B backlog providing partial buffer',
    'In current stagflation_risk regime, SPX -10-15% → Wave 5 -17 to -25%; VRT specifically with $15B backlog has revenue floor but stock price tracks the wave',
    'Cooling is early-mid cycle — heat density at GPU is the structural driver, not yet at peak consensus. VRT consolidated 3 acquisitions in 2 months building integrated chip-to-building thermal chain. Multiple expansion from 22x → 28x reflects recognition; further expansion requires liquid-cooling penetration acceleration.',
    'In stagflation regime, integrated solutions (VRT) command pricing power vs component plays (MOD individual products). Watch the 2.9x book-to-bill — that''s the structural confidence indicator. If it drops below 2.0x, the multi-year backlog confidence is eroding.',
    '[
        {"ticker": "VRT", "resilience": "high",   "reason": "$15B backlog, 2.9x book-to-bill, integrated chip-to-building thermal chain via 3 recent acquisitions",
         "trailing_12mo_return": 1.42, "trailing_18mo_return": 2.10},
        {"ticker": "MOD", "resilience": "medium", "reason": "thermal management specialist; smaller and less integrated than VRT",
         "trailing_12mo_return": 0.62, "trailing_18mo_return": 1.05},
        {"ticker": "ETN", "resilience": "medium-high", "reason": "Boyd acquisition gives cold plate exposure; large diversified industrials",
         "trailing_12mo_return": 0.28, "trailing_18mo_return": 0.55}
    ]'::jsonb,
    '{
        "vrt_book_to_bill": {"metric": "VRT quarterly book-to-bill", "current": "2.9x", "threshold_bearish": "<2.0x = backlog confidence eroding"},
        "liquid_cooling_penetration": {"metric": "% of new datacenter builds specifying liquid cooling vs air", "current": "rising", "threshold_bullish": ">50% in any quarter"},
        "vrt_backlog_dollar_value": {"metric": "VRT contracted backlog $ value QoQ", "current": "$15B", "threshold_bearish": "QoQ decline >$1B"},
        "competitor_acquisitions": {"metric": "competitor M&A activity in cooling", "current": "VRT-led consolidation", "watch": "any hyperscaler vertical integration into cooling"}
    }'::jsonb
FROM waves w
JOIN revolutions r ON r.id = w.revolution_id
WHERE r.name_cn = 'AI革命' AND w.name_cn = '冷却'
ON CONFLICT DO NOTHING;


-- ────────────────────────────────────────────────────────────────
-- Verification block
-- ────────────────────────────────────────────────────────────────

DO $$
DECLARE
    n_rows int;
BEGIN
    SELECT COUNT(*) INTO n_rows FROM current_wave_health;
    IF n_rows >= 4 THEN
        RAISE NOTICE 'wave_health seed succeeded: % rows in current_wave_health', n_rows;
    ELSE
        RAISE NOTICE 'wave_health seed unexpected count: % rows (expected ≥4)', n_rows;
    END IF;
END $$;
