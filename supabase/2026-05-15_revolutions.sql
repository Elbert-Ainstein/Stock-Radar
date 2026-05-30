-- ═══════════════════════════════════════════════════════════════
-- TECH REVOLUTIONS — wave-based supply-chain map of investment themes
-- 2026-05-15  (BUILD_PLAN_v2 Phase 1.1)
--
-- The 科技革命 model: an investment-grade revolution is a multi-year
-- structural buildout where capex is concentrated in identifiable
-- waves with named chokepoints. The system tracks three revolutions
-- as seed data (AI / Space / Digital Finance) and is extensible by
-- user via the [+新科技革命] flow.
--
-- Tables:
--   revolutions       — top-level revolution rows (one per movement)
--   waves             — ordered wave layers within a revolution
--   ticker_revolutions — many-to-many: a stock may appear in
--                       multiple revolutions, each at a different
--                       wave and lifecycle stage
--
-- A stock not in any revolution is still fully analyzable —
-- revolution membership is contextual metadata, not a requirement.
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS revolutions (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name_cn         text NOT NULL UNIQUE,            -- "AI革命"
    name_en         text NOT NULL,                   -- "AI Revolution"
    description     text,                            -- one-paragraph summary
    market_size     text,                            -- "$7,250B+ annual capex"
    timeline        text,                            -- "2024-2035"
    created_at      timestamptz NOT NULL DEFAULT now(),
    created_by      text DEFAULT 'system'            -- 'system' for seeds, 'user' for [+新科技革命]
);

CREATE TABLE IF NOT EXISTS waves (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    revolution_id   bigint NOT NULL REFERENCES revolutions(id) ON DELETE CASCADE,
    wave_number     int NOT NULL,                    -- 0, 1, 2, 3 ...  (junction wave is N/A)
    name_cn         text NOT NULL,                   -- "设备"
    name_en         text,                            -- "Equipment"
    core_need       text,                            -- "advanced packaging metrology"
    chokepoint      text,                            -- "3D microbump white-light measurement"
    lifecycle       text,                            -- 'pre_discovery'|'early'|'early_mid'|'mid'|'peak'
    notes           text,
    is_junction     boolean DEFAULT false,           -- cross-cutting layer (横切层)
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (revolution_id, wave_number, name_cn)     -- allow a junction wave at the same number
);

CREATE TABLE IF NOT EXISTS ticker_revolutions (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ticker          text NOT NULL,                   -- 'CAMT'
    wave_id         bigint NOT NULL REFERENCES waves(id) ON DELETE CASCADE,
    lifecycle       text,                            -- ticker-specific lifecycle within this wave
    notes           text,
    assigned_at     timestamptz NOT NULL DEFAULT now(),
    assigned_by     text DEFAULT 'system',
    UNIQUE (ticker, wave_id)
);

CREATE INDEX IF NOT EXISTS idx_waves_revolution      ON waves (revolution_id);
CREATE INDEX IF NOT EXISTS idx_ticker_rev_ticker     ON ticker_revolutions (ticker);
CREATE INDEX IF NOT EXISTS idx_ticker_rev_wave       ON ticker_revolutions (wave_id);

-- ────────────────────────────────────────────────────────────────
-- View: cross-revolution stocks (appears in 2+ revolutions)
-- ────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW cross_revolution_tickers AS
SELECT
    tr.ticker,
    array_agg(DISTINCT r.name_cn ORDER BY r.name_cn) AS revolutions,
    COUNT(DISTINCT r.id) AS revolution_count
FROM ticker_revolutions tr
JOIN waves w ON w.id = tr.wave_id
JOIN revolutions r ON r.id = w.revolution_id
GROUP BY tr.ticker
HAVING COUNT(DISTINCT r.id) >= 2;

-- ────────────────────────────────────────────────────────────────
-- Seed data — 3 revolutions, 30 waves (BUILD_PLAN_v2 §Seed Data)
-- ────────────────────────────────────────────────────────────────

INSERT INTO revolutions (name_cn, name_en, description, market_size, timeline) VALUES
    ('AI革命',     'AI Revolution',          'AI compute buildout: from semiconductor equipment through inference workloads to native-AI software.',
     '$7,250B+ annual capex', '2024-2035'),
    ('太空经济革命', 'Space Economy Revolution', 'Commercial space buildout: launch, satellite components, manufacturing, ground infrastructure, defense, on-orbit services.',
     'TBD',                  '2023-2040'),
    ('数字金融革命', 'Digital Finance Revolution', 'Blockchain infrastructure: base layer, stablecoins, exchanges, custody, payments, tokenization, on-chain finance.',
     'TBD',                  '2024-2035')
ON CONFLICT (name_cn) DO NOTHING;

-- AI revolution waves
INSERT INTO waves (revolution_id, wave_number, name_cn, name_en, core_need, chokepoint, lifecycle, is_junction)
SELECT r.id, w.wn, w.cn, w.en, w.core, w.choke, w.lc, w.is_j
FROM revolutions r
CROSS JOIN (VALUES
    (0,  '设备',          'Equipment',                'advanced packaging metrology',     '3D microbump white-light measurement',         'early',         false),
    (1,  '算力',          'Compute',                  'GPU compute density',              'leading-edge GPU/foundry',                     'peak',          false),
    (2,  '光互联',        'Optical Interconnect',     'rack-to-rack & rack-internal bandwidth', '200G/lane EML lasers',                  'mid',           false),
    (3,  '存储',          'Storage',                  'AI training dataset memory',       'HBM + datacenter SSD',                         'mid',           false),
    (4,  '电力',          'Power',                    'datacenter electricity baseload',  'nuclear PPAs + grid components',               'early_mid',     false),
    (5,  '冷却',          'Cooling',                  'thermal density management',       'liquid-cooling integration',                   'early',         false),
    (6,  '推理',          'Inference',                'inference acceleration economics', 'inference-optimized silicon',                  'early',         false),
    (7,  'AI原生应用',    'AI-Native Applications',   'AI-first consumer/enterprise apps','proprietary first-party data + ML ops',         'mid',           false),
    (8,  'AI基础软件',    'AI Foundational Software', 'data + observability platforms',   'platform breadth & switching costs',            'early_mid',     false),
    (9,  'AI增强SaaS',    'AI-Augmented SaaS',        'AI features in existing SaaS',     'embedding without margin compression',          'early',         false),
    (10, 'AI颠覆SaaS',    'AI-Disrupted SaaS',        'short / pair-trade candidates',    'identifying the displaced incumbents',          'peak',          false),
    (99, '横切层',        'Junction Layer',           'cross-wave suppliers',             'cross-cutting chokepoint exposure',             'early_mid',     true)
) AS w(wn, cn, en, core, choke, lc, is_j)
WHERE r.name_cn = 'AI革命'
ON CONFLICT (revolution_id, wave_number, name_cn) DO NOTHING;

-- Space revolution waves
INSERT INTO waves (revolution_id, wave_number, name_cn, name_en, core_need, chokepoint, lifecycle, is_junction)
SELECT r.id, w.wn, w.cn, w.en, w.core, w.choke, w.lc, w.is_j
FROM revolutions r
CROSS JOIN (VALUES
    (0,  '发射',          'Launch',                   'orbital launch capacity',          'reusable medium-lift cadence',                'early_mid',     false),
    (1,  '卫星组件',      'Satellite Components',     'radiation-hardened parts',         'rad-hard chips, SADAs, carbon fiber',          'early',         false),
    (2,  '卫星制造',      'Satellite Manufacturing',  'vertical integration',             'in-house bus + payload',                       'early_mid',     false),
    (3,  '地面基础设施',  'Ground Infrastructure',    'data downlink + cloud bridge',     'ground-station-as-a-service',                  'early',         false),
    (4,  '连接',          'Connectivity',             'direct-to-device space comms',     'direct-to-cell satellite licensing',           'pre_discovery', false),
    (5,  '地球观测',      'Earth Observation',        'persistent imagery & data',        'constellation refresh rate',                   'early',         false),
    (6,  '国防',          'Defense',                  'gov/military demand',              'SDA contracts + integration',                   'early_mid',     false),
    (7,  '在轨服务',      'On-Orbit Services',        'refueling + repair',               'docking + propellant delivery',                 'pre_discovery', false),
    (8,  '太空制造',      'Space Manufacturing',      'microgravity production',          'commercial returns from orbit',                 'pre_discovery', false),
    (99, '横切层',        'Junction Layer',           'cross-wave suppliers',             'rad-hard chips, carbon fiber, test',           'early',         true)
) AS w(wn, cn, en, core, choke, lc, is_j)
WHERE r.name_cn = '太空经济革命'
ON CONFLICT (revolution_id, wave_number, name_cn) DO NOTHING;

-- Digital finance revolution waves
INSERT INTO waves (revolution_id, wave_number, name_cn, name_en, core_need, chokepoint, lifecycle, is_junction)
SELECT r.id, w.wn, w.cn, w.en, w.core, w.choke, w.lc, w.is_j
FROM revolutions r
CROSS JOIN (VALUES
    (0,  '基础层',        'Base Layer',               'settlement infrastructure',        'L1 throughput + decentralization',             'mid',           false),
    (1,  '稳定币',        'Stablecoin',               'regulated dollar-on-chain',        'issuance + reserves trust',                    'early_mid',     false),
    (2,  '交易所',        'Exchange',                 'on/off-ramp',                      'regulated venue + listings',                   'mid',           false),
    (3,  '托管',          'Custody',                  'institutional storage',            'qualified custody + regulatory licenses',      'early',         false),
    (4,  '支付',          'Payments',                 'stablecoin payment rails',         'merchant adoption + settlement',               'early',         false),
    (5,  '代币化',        'Tokenization',             'real-world assets on-chain',       'institutional issuance frameworks',            'pre_discovery', false),
    (6,  '链上金融',      'On-Chain Finance',         'DeFi for institutions',            'compliance + liquidity',                       'early',         false),
    (7,  'AI+Crypto',     'AI + Crypto',              'agent-driven on-chain economics',  'unclear',                                       'pre_discovery', false),
    (99, '横切层',        'Junction Layer',           'multi-wave operators',             'COIN/CRCL/BTGO touch multiple waves',          'early_mid',     true)
) AS w(wn, cn, en, core, choke, lc, is_j)
WHERE r.name_cn = '数字金融革命'
ON CONFLICT (revolution_id, wave_number, name_cn) DO NOTHING;

-- NOTE: Initial ticker → wave assignments from socratic_results_summary.md
-- are deliberately NOT inserted here. They'll be done via a separate
-- one-shot script after the schema is applied, so we can review them
-- before they hit the live DB. See scripts/seed_ticker_revolutions.py
-- (to be written in Phase 7).
