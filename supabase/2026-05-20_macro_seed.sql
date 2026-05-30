-- ═══════════════════════════════════════════════════════════════
-- SEED — macro_environment.id=1 from Hume's 2026-05-17 analysis
-- 2026-05-20  (BUILD_PLAN_v2 Phase 5.5 — seed first manual row)
--
-- Inserts the current regime as a structured row so the system has a
-- ground-truth macro context for all subsequent Socratic runs. Source
-- is the chat message from 2026-05-17 plus its Section A-H structured
-- form. After this seed, the existing LITE pass (bets.id=1) is backfilled
-- to link to this macro context for proper settlement at T+90 (2026-08-16).
--
-- Run AFTER: 2026-05-20_phase5_5_macro_wave.sql (creates the table)
-- ═══════════════════════════════════════════════════════════════

INSERT INTO macro_environment (
    source,
    state_summary,
    regime_classification,
    bear_case,
    bull_case,
    state_change_triggers,
    watch_dates,
    this_week_watch,
    falsification,
    notes
) VALUES (
    'manual_hume',

    -- State summary
    'Collision regime: inflation re-accelerating (CPI 3.8% YoY April 2026, energy +17.9% YoY from Iran/Hormuz disruption), new Fed chair Warsh confirmed 2026-05-13 trapped between his stated dovish preferences and data that forbids cuts. Powell remains on board as a governing vote, watching Warsh. Three regional Fed presidents pushed at April meeting to signal next move could be HIKE; four dissents total (most since 1992). Market pricing zero cuts through end of 2027, 37% probability of HIKE by year-end. Paradoxically, the economy is resilient: GDP tracking +3.7% Q2, corporate profits robust, hiring strong. The Fed has no urgency to cut because the economy does not need rescue, but consumers are getting squeezed (real wages -0.5% one month, consumer sentiment all-time lows).',

    'stagflation_risk',

    -- Bear case
    jsonb_build_object(
        'probability', 'moderate-high',
        'drivers', jsonb_build_array(
            'CPI at 3.8% YoY and accelerating — going wrong direction, not stuck above target',
            'Iran/Hormuz keeping oil above $100/barrel; gasoline $4.50 nationally; structural energy inflation',
            'Warsh wants to cut but data forbids it — Day-1 he walks in with 37% hike probability priced',
            'Powell + three regional hawks can outvote Warsh on any dovish move',
            'Real wages -0.5% one month; consumer sentiment all-time low; spending eventually slows',
            'Markets hate a Fed that''s internally divided and directionally unclear'
        ),
        'implication', 'SPX correction 10-15% over 1-3 months as the "Warsh will cut" narrative dies. AI infrastructure stocks at 2-2.5x SPX beta drop 25-40% (CAMT $170→$100-130, GFS $70→$36-50, VRT $340→$235-250, SIMO $260→$130-150). These are the entry prices the portfolio should target.'
    ),

    -- Bull case
    jsonb_build_object(
        'probability', 'moderate',
        'drivers', jsonb_build_array(
            'GDP tracking +3.7% Q2 — economy is structurally strong, doesn''t need rescue',
            'Corporate profits robust; Q1 earnings beating consensus broadly',
            'AI capex cycle is structural — $7,250B committed 2024-2035, contractual not discretionary',
            'Iran situation could de-escalate → oil drops to $70 → CPI falls → rate cuts back on table',
            'Warsh could surprise with creative policy (end QT while holding rates)',
            'Tax refunds + hiring momentum buffer consumer spending near-term'
        ),
        'implication', 'Market holds or grinds higher on earnings strength despite macro noise. AI infrastructure stocks consolidate but don''t correct hard. Entry timing window may not materialize.'
    ),

    -- State change triggers (each becomes a Phase 6 notification rule)
    jsonb_build_array(
        jsonb_build_object(
            'event', 'iran_ceasefire',
            'direction', 'BULLISH',
            'watch_for', 'Iran ceasefire announcement → oil drops to $70 → next CPI prints below 3.5% → rate cuts back on table'
        ),
        jsonb_build_object(
            'event', 'may_cpi_above_4',
            'direction', 'BEARISH',
            'watch_for', 'May CPI prints above 4% → rate HIKE becomes consensus; SPX correction confirmed'
        ),
        jsonb_build_object(
            'event', 'warsh_first_speech',
            'direction', 'CLARITY',
            'watch_for', 'Warsh''s first public remarks as chair → tone reveals actual policy direction'
        ),
        jsonb_build_object(
            'event', 'q2_gdp_slowdown',
            'direction', 'MIXED',
            'watch_for', 'Q2 GDP slows materially → recession fears → Fed forced to cut regardless of inflation (bullish for risk assets short-term, bearish for cyclicals)'
        ),
        jsonb_build_object(
            'event', 'june_fomc_dissent_pattern',
            'direction', 'CLARITY',
            'watch_for', 'June FOMC vote pattern — Warsh''s first as chair. Does he get rolled by hawks? Does Powell vote against him? Public dissents reveal coalition.'
        )
    ),

    -- Watch dates
    jsonb_build_array(
        jsonb_build_object('date', '2026-06-12', 'event', 'May CPI release', 'importance', 'critical — bear-case trigger if >4%'),
        jsonb_build_object('date', '2026-06-17', 'event', 'June FOMC meeting (Warsh''s first as chair)', 'importance', 'critical'),
        jsonb_build_object('date', '2026-07-25', 'event', 'Q2 GDP advance estimate', 'importance', 'high — tests "economy resilient" claim'),
        jsonb_build_object('date', '2026-07-15', 'event', 'June CPI release', 'importance', 'high'),
        jsonb_build_object('date', '2026-07-18', 'event', 'Q2 earnings season starts (JPM/Wells leadoff)', 'importance', 'medium — corporate profit resilience test')
    ),

    -- This week watch (granular, weekly cadence)
    jsonb_build_array(
        jsonb_build_object('item', 'Warsh''s first public remarks as chair', 'note', 'Any speech, congressional testimony, or background briefing reveals actual policy direction'),
        jsonb_build_object('item', 'Oil price daily close vs $100', 'note', 'Still above? Iran situation evolving?'),
        jsonb_build_object('item', 'Market reaction to the regime change', 'note', 'Institutional repositioning visible in VIX term structure, sector rotation, financial-sector relative performance')
    ),

    -- Falsification: what would prove this regime call wrong
    'If by 2026-08-15 ALL of: (1) S&P 500 has not had a >5% drawdown from 2026-05-17 levels, (2) CPI has not printed above 3.5% in any month, (3) Warsh has publicly signaled a clear path to cuts that markets have priced — then the bear case has failed. Single conditions in isolation are not sufficient; the regime needs at least one to manifest within 90 days.',

    -- Notes
    'Seeded manually by Hume 2026-05-17 (chat) and 2026-05-19/2026-05-20 design refinement. First macro_environment row in the system. bets.id=1 (LITE pass at $970) is being backfilled to link to this row via the subsequent UPDATE.'
);


-- ────────────────────────────────────────────────────────────────
-- Backfill bets.id=1 (LITE pass) to link to macro_environment.id=1
-- Per Must-fix #4: also update status to 'passed' (was 'active'; 0% position).
-- ────────────────────────────────────────────────────────────────

UPDATE bets
SET macro_environment_id = (
        SELECT id FROM macro_environment ORDER BY id DESC LIMIT 1   -- the row we just inserted
    ),
    status = 'passed'
WHERE id = 1
  AND ticker = 'LITE'
  AND position_pct = 0;

-- Verification: confirm the backfill succeeded
DO $$
DECLARE
    backfilled_count int;
BEGIN
    SELECT COUNT(*) INTO backfilled_count
    FROM bets
    WHERE id = 1 AND macro_environment_id IS NOT NULL AND status = 'passed';

    IF backfilled_count = 1 THEN
        RAISE NOTICE 'bets.id=1 successfully linked to macro_environment and marked passed';
    ELSE
        RAISE NOTICE 'bets.id=1 backfill skipped or already done (count=%)', backfilled_count;
    END IF;
END $$;
