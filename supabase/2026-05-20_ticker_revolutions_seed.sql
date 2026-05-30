-- ═══════════════════════════════════════════════════════════════
-- SEED — ticker_revolutions for the AI / Space / Digital Finance tickers
-- 2026-05-20  (deferred from Phase 1 2026-05-15_revolutions.sql per
--              its closing NOTE; now needed so wave_context fetch resolves)
--
-- Links the analyzed tickers from socratic_results_summary to their
-- primary wave. is_primary_wave=true picks the canonical wave for the
-- harness lookup rule (Must-fix #3). Stocks appearing in multiple waves
-- (e.g. AMD in compute + inference, MPWR in cross-cutting + power IC)
-- get exactly ONE primary tag.
--
-- Idempotent — ON CONFLICT (ticker, wave_id) skips if already assigned.
--
-- Run AFTER: 2026-05-15_revolutions.sql, 2026-05-20_phase5_5_macro_wave.sql
--            (the latter adds is_primary_wave column)
-- ═══════════════════════════════════════════════════════════════

-- Helper template: insert into ticker_revolutions using wave lookup.
-- We use a parameterized INSERT pattern keyed on (revolution.name_cn, wave.name_cn).

-- ────────────────────────────────────────────────────────────────
-- AI Revolution assignments
-- ────────────────────────────────────────────────────────────────

INSERT INTO ticker_revolutions (ticker, wave_id, lifecycle, is_primary_wave, timing_category, notes, assigned_by)
SELECT t.ticker, w.id, t.lifecycle, t.is_primary, t.timing, t.notes, 'system'
FROM revolutions r
JOIN waves w ON w.revolution_id = r.id
CROSS JOIN (VALUES
    -- Wave 0: Equipment (设备)
    ('设备', 'ASML', 'mid',         true,  '半步领先', 'EUV monopoly, consensus but structurally irreplaceable'),
    ('设备', 'CAMT', 'early_mid',   true,  '半步领先', '3D microbump moat KLA cannot match, 70% AI exposure, 17% pullback opportunity'),
    ('设备', 'KLA',  'mid',         false, '收获期',   'Front-end inspection consensus, $194B, 20 analysts Buy — peak consensus'),
    ('设备', 'KLIC', 'early_mid',   false, '半步领先', 'TCB bonding for CoWoS, exposure to hyperscaler capex cycle'),

    -- Wave 1: Compute (算力)
    ('算力', 'NVDA', 'peak',        true,  '收获期',   'GPU monopoly past peak consensus'),

    -- Wave 2: Optical (光互联)
    ('光互联', 'LITE', 'peak',      true,  '收获期',   'Current-gen 200G EML monopoly. Extreme momentum (+943% 12mo). Macro pass at $970.'),
    ('光互联', 'COHR', 'mid',       false, '收获期',   'Next-gen 400G D-EML positioning. NVDA $2B partnership. WATCH not BREAK for LITE.'),
    ('光互联', 'AAOI', 'peak',      false, '收获期',   '441% YTD, no moat, unprofitable on $600M rev. Pass.'),

    -- Wave 3: Storage (存储)
    ('存储',  'MU',   'mid',        true,  '半步领先', 'HBM #3 + US-based scarcity. Data still contaminated per project_mu_data_bug.'),
    ('存储',  'SNDK', 'mid',        false, '半步领先', '$42B contracted backlog at 78% gross margins.'),

    -- Wave 4: Power (电力)
    ('电力',  'CEG',  'early_mid',  true,  '一步领先', 'Largest US nuclear fleet. Wait lockup Jun 30 / DOJ Sept 4.'),
    ('电力',  'GEV',  'early_mid',  false, '半步领先', 'Natural gas turbines, transformer backlog'),
    ('电力',  'BE',   'early',      false, '一步领先', 'Fuel cells for datacenter, smaller player'),

    -- Wave 5: Cooling (冷却)
    ('冷却',  'VRT',  'early_mid',  true,  '半步领先', '$15B backlog, 2.9x book-to-bill, integrated chip-to-building chain. 3 acquisitions consolidating.'),
    ('冷却',  'MOD',  'early_mid',  false, '半步领先', 'Thermal management specialist, smaller and less integrated than VRT'),
    ('冷却',  'ETN',  'mid',        false, '半步领先', 'Boyd acquisition gives cold plate exposure, diversified industrials'),

    -- Wave 6: Inference (推理)
    ('推理',  'AMD',  'peak',       true,  '收获期',   '$762B, 41/41 Buy, ATH. Peak consensus.'),
    ('推理',  'MRVL', 'mid',        false, '一步领先', 'Custom silicon platform, #2 to AVGO'),
    ('推理',  'ALAB', 'peak',       false, '收获期',   '93% YoY but 70% NVDA single-customer, $211M insider selling'),

    -- Wave 7: AI-Native Applications (AI原生应用)
    ('AI原生应用', 'APP',  'mid',   true,  '一步领先', 'AXON AI engine. 65% net margin, 85% EBITDA. SEC investigation risk.'),
    ('AI原生应用', 'PLTR', 'mid',   false, '一步领先', 'Government + commercial expansion'),

    -- Wave 8: AI Foundational Software (AI基础软件)
    ('AI基础软件', 'DDOG', 'early_mid', true,  '半步领先', 'Growth accelerating 32% at scale. OpenAI largest customer. Wait pullback $160.'),
    ('AI基础软件', 'SNOW', 'mid',       false, '一步领先', 'Data platform, slower AI integration'),
    ('AI基础软件', 'MDB',  'mid',       false, '一步领先', 'Document database, AI use cases emerging'),

    -- Wave 9: AI-Augmented SaaS (AI增强SaaS)
    ('AI增强SaaS', 'NOW',  'early', false, '一步领先', 'Workflow + AI features'),
    ('AI增强SaaS', 'CRWD', 'mid',   false, '一步领先', '134x forward P/E, AI security thesis real but revenue not materialized'),
    ('AI增强SaaS', 'CRM',  'mid',   false, '一步领先', 'Einstein AI features in CRM stack'),

    -- Wave 10: AI-Disrupted SaaS (AI颠覆SaaS) — short candidates
    ('AI颠覆SaaS', 'ZI',   'peak',  false, '收获期',   'Disrupted by AI sales tools — short candidate'),

    -- Junction layer (横切层 / wave_number=99) — cross-cutting tickers
    ('横切层', 'MPWR',     'mid',   true,  '半步领先', '70% NVDA Vera Rubin power, strongest chokepoint. Wait pullback $1,300.'),
    ('横切层', 'ENTG',     'mid',   true,  '一步领先', 'Filtration + chemicals oligopolist. Not sole-source. Pass per socratic.'),
    ('横切层', 'GFS',      'early_mid', true,  '半步领先', 'SCALE silicon photonics. NVDA/AMD/MSFT backing. 19x P/E — cheapest AI semi.'),
    ('横切层', '6857.T',   'mid',   true,  '一步领先', 'Advantest. #1 ATE, 58% share, 65% GM. Quality duopoly.'),
    ('横切层', 'GLW',      'mid',   false, '一步领先', 'Western fiber leader')
) AS t(wave_name, ticker, lifecycle, is_primary, timing, notes)
WHERE r.name_cn = 'AI革命' AND w.name_cn = t.wave_name
ON CONFLICT (ticker, wave_id) DO NOTHING;


-- ────────────────────────────────────────────────────────────────
-- Space Economy Revolution
-- ────────────────────────────────────────────────────────────────

INSERT INTO ticker_revolutions (ticker, wave_id, lifecycle, is_primary_wave, timing_category, notes, assigned_by)
SELECT t.ticker, w.id, t.lifecycle, t.is_primary, t.timing, t.notes, 'system'
FROM revolutions r
JOIN waves w ON w.revolution_id = r.id
CROSS JOIN (VALUES
    ('发射',    'RKLB', 'early_mid', true,  '半步领先', '"TSMC of space" vertical integration W0+W2+W6. $2.2B backlog, $200M Q1 +63.5%. Binary Neutron risk.'),
    ('地球观测', 'PL',   'early',   true,  '一步领先', 'Earth observation, smaller play'),
    ('地球观测', 'BKSY', 'early',   false, '一步领先', 'Radar imagery'),
    ('连接',    'ASTS', 'pre_discovery', true, '一步领先', 'Direct-to-cell satellite licensing, frontier'),
    ('太空制造', 'LUNR', 'pre_discovery', true, '远见期', 'Space manufacturing, very early')
) AS t(wave_name, ticker, lifecycle, is_primary, timing, notes)
WHERE r.name_cn = '太空经济革命' AND w.name_cn = t.wave_name
ON CONFLICT (ticker, wave_id) DO NOTHING;


-- ────────────────────────────────────────────────────────────────
-- Digital Finance Revolution
-- ────────────────────────────────────────────────────────────────

INSERT INTO ticker_revolutions (ticker, wave_id, lifecycle, is_primary_wave, timing_category, notes, assigned_by)
SELECT t.ticker, w.id, t.lifecycle, t.is_primary, t.timing, t.notes, 'system'
FROM revolutions r
JOIN waves w ON w.revolution_id = r.id
CROSS JOIN (VALUES
    ('稳定币',  'CRCL', 'early_mid', true,  '一步领先', 'USDC $78B (+72% YoY). 95% interest income. Macro helps near-term; cuts compress revenue.'),
    ('交易所',  'COIN', 'mid',       true,  '一步领先', 'Multi-layer regulated venue + listings'),
    ('交易所',  'HOOD', 'early_mid', false, '一步领先', 'Retail-focused exchange'),
    ('托管',    'BTGO', 'early',     true,  '一步领先', 'Institutional custody specialist'),
    ('支付',    'V',    'mid',       false, '收获期',   'Visa — stablecoin rails exposure but legacy network is core'),
    ('支付',    'MA',   'mid',       false, '收获期',   'Mastercard — same shape as V')
) AS t(wave_name, ticker, lifecycle, is_primary, timing, notes)
WHERE r.name_cn = '数字金融革命' AND w.name_cn = t.wave_name
ON CONFLICT (ticker, wave_id) DO NOTHING;


-- ────────────────────────────────────────────────────────────────
-- Verification block
-- ────────────────────────────────────────────────────────────────

DO $$
DECLARE
    n_ai_primary int;
    n_total int;
BEGIN
    SELECT COUNT(*) INTO n_ai_primary
    FROM ticker_revolutions tr
    JOIN waves w ON w.id = tr.wave_id
    JOIN revolutions r ON r.id = w.revolution_id
    WHERE r.name_cn = 'AI革命' AND tr.is_primary_wave = true;

    SELECT COUNT(*) INTO n_total FROM ticker_revolutions;

    RAISE NOTICE 'ticker_revolutions seed complete: % AI tickers with is_primary_wave=true; % total assignments',
                 n_ai_primary, n_total;
END $$;
