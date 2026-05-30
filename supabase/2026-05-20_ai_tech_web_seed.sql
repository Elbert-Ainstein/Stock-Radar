-- ═══════════════════════════════════════════════════════════════
-- SEED — AI revolution Technology Web (4 levels deep)
-- 2026-05-20  (specs/04_technology_web.md content; BUILD_PLAN addendum §A)
--
-- Populates tech_nodes + node_companies for the AI revolution with the
-- 4-level web traced in specs/04. Surfaces the hidden chokepoints the
-- linear wave map missed: Ajinomoto (98% ABF substrate IP), Disco
-- (precision dicing near-monopoly), TSEM (SiPho foundry), BESI/ASMPT
-- (bonding), SIMO (SSD controllers), AMKR (US OSAT/CoWoS), AAOI, SPXC.
--
-- Run AFTER: 2026-05-20_tech_nodes.sql (creates the tables)
--
-- Methodology note: this is the seed data the lateral-trace methodology
-- would build automatically. Storing it here means the system has the
-- ground-truth web on day one; future discovery_pipeline runs can ADD
-- nodes as they're discovered.
-- ═══════════════════════════════════════════════════════════════

-- ────────────────────────────────────────────────────────────────
-- Helper: get the AI revolution id
-- ────────────────────────────────────────────────────────────────

WITH ai_rev AS (
    SELECT id FROM revolutions WHERE name_cn = 'AI革命' LIMIT 1
)
-- depth 0 root node
INSERT INTO tech_nodes (revolution_id, parent_id, depth, name, name_zh, description, chokepoint_score)
SELECT id, NULL, 0, 'AI Datacenter', 'AI 数据中心', 'Root node — entire AI datacenter buildout', 'oligopoly'
FROM ai_rev
ON CONFLICT DO NOTHING;


-- ────────────────────────────────────────────────────────────────
-- Depth 1 — Six top-level systems
-- ────────────────────────────────────────────────────────────────

WITH root AS (
    SELECT id, revolution_id FROM tech_nodes
    WHERE depth = 0 AND name = 'AI Datacenter'
    LIMIT 1
)
INSERT INTO tech_nodes (revolution_id, parent_id, depth, name, name_zh, description, chokepoint_score)
SELECT r.revolution_id, r.id, 1, n.name, n.name_zh, n.description, n.chokepoint
FROM root r
CROSS JOIN (VALUES
    ('Compute',              '算力',     'GPU + CPU + custom ASICs + foundry + advanced packaging + memory + power ICs', 'oligopoly'),
    ('Networking',           '网络',     'GPU-to-GPU communication: optical transceivers, switches, CPO',                'oligopoly'),
    ('Storage',              '存储',     'Enterprise SSDs, HBM, HDDs',                                                   'competitive'),
    ('Power',                '电力',     'Utility-scale generation, on-site power, distribution',                        'competitive'),
    ('Cooling',              '冷却',     'Liquid cooling CDU, cold plates, heat rejection, immersion',                   'oligopoly'),
    ('Specialty Materials',  '特殊材料', 'Cross-cutting: filtration, fiber, ABF substrate IP, specialty gases',          'oligopoly')
) AS n(name, name_zh, description, chokepoint)
ON CONFLICT DO NOTHING;


-- ────────────────────────────────────────────────────────────────
-- Depth 2 — Subsystems within each system
-- ────────────────────────────────────────────────────────────────

-- Under Compute
INSERT INTO tech_nodes (revolution_id, parent_id, depth, name, name_zh, description, chokepoint_score)
SELECT p.revolution_id, p.id, 2, n.name, n.name_zh, n.description, n.chokepoint
FROM tech_nodes p
CROSS JOIN (VALUES
    ('Chip Design',           '芯片设计',   'GPU/CPU architecture + custom ASIC partners + EDA tools',                 'duopoly'),
    ('Foundry',               '晶圆代工',   'Leading-edge manufacturing (3nm/2nm)',                                    'monopoly'),
    ('Advanced Packaging',    '先进封装',   'CoWoS — the hidden mega-chokepoint',                                       'monopoly'),
    ('Front-end Equipment',   '前道设备',   'Lithography, etch, deposition, photoresist',                              'oligopoly'),
    ('Testing',               '测试',       'System-level ATE',                                                        'duopoly'),
    ('Memory',                '存储',       'HBM + DRAM',                                                              'oligopoly'),
    ('Power Management ICs',  '电源管理',   'NVDA Vera Rubin power, second-source competitors',                        'duopoly')
) AS n(name, name_zh, description, chokepoint)
WHERE p.name = 'Compute' AND p.depth = 1
ON CONFLICT DO NOTHING;

-- Under Networking
INSERT INTO tech_nodes (revolution_id, parent_id, depth, name, name_zh, description, chokepoint_score)
SELECT p.revolution_id, p.id, 2, n.name, n.name_zh, n.description, n.chokepoint
FROM tech_nodes p
CROSS JOIN (VALUES
    ('Optical Transceivers',  '光收发器',   '800G / 1.6T / 3.2T modules; EML lasers + SiPho PICs + DSPs + modules',    'oligopoly'),
    ('Network Switches',      '网络交换机', 'Switch ASICs + PCIe retimers + CXL controllers',                          'oligopoly'),
    ('Co-Packaged Optics',    'CPO',        'Next-gen — first revenue 2027+',                                          'oligopoly'),
    ('High-Speed Connectors', '高速连接器', 'Data center MPO fiber + copper connectors',                               'oligopoly'),
    ('Optical Fiber & Cable', '光纤光缆',   'Physical data transmission backbone',                                     'oligopoly')
) AS n(name, name_zh, description, chokepoint)
WHERE p.name = 'Networking' AND p.depth = 1
ON CONFLICT DO NOTHING;

-- Under Storage
INSERT INTO tech_nodes (revolution_id, parent_id, depth, name, name_zh, description, chokepoint_score)
SELECT p.revolution_id, p.id, 2, n.name, n.name_zh, n.description, n.chokepoint
FROM tech_nodes p
CROSS JOIN (VALUES
    ('Enterprise SSDs',      '企业SSD',  'NAND flash + SSD controllers',                  'oligopoly'),
    ('SSD Controllers',      'SSD控制器', 'Independent controllers for AI server SSDs',    'duopoly'),
    ('HDDs',                 '机械硬盘', 'Bulk/cold storage',                             'duopoly')
) AS n(name, name_zh, description, chokepoint)
WHERE p.name = 'Storage' AND p.depth = 1
ON CONFLICT DO NOTHING;

-- Under Power
INSERT INTO tech_nodes (revolution_id, parent_id, depth, name, name_zh, description, chokepoint_score)
SELECT p.revolution_id, p.id, 2, n.name, n.name_zh, n.description, n.chokepoint
FROM tech_nodes p
CROSS JOIN (VALUES
    ('Utility Generation',   '公用事业发电', 'Nuclear, natural gas, grid transformers',           'oligopoly'),
    ('On-site Power',        '现场电力',     'Fuel cells, gas turbines, battery backup',          'competitive'),
    ('Power Distribution',   '电力分配',     'UPS, switchgear, busbar, high-voltage DC',          'oligopoly')
) AS n(name, name_zh, description, chokepoint)
WHERE p.name = 'Power' AND p.depth = 1
ON CONFLICT DO NOTHING;

-- Under Cooling
INSERT INTO tech_nodes (revolution_id, parent_id, depth, name, name_zh, description, chokepoint_score)
SELECT p.revolution_id, p.id, 2, n.name, n.name_zh, n.description, n.chokepoint
FROM tech_nodes p
CROSS JOIN (VALUES
    ('Liquid Cooling CDU',   '液冷分配单元', 'Coolant distribution units',                        'oligopoly'),
    ('Cold Plates',          '冷板',         'Direct chip cooling',                               'oligopoly'),
    ('Heat Rejection',       '散热',         'Building-level heat exchange',                      'competitive'),
    ('Immersion Cooling',    '浸没冷却',     'Two-phase + single-phase immersion',                'competitive'),
    ('Refrigerants',         '冷媒',         'Next-gen low-GWP coolants',                         'duopoly')
) AS n(name, name_zh, description, chokepoint)
WHERE p.name = 'Cooling' AND p.depth = 1
ON CONFLICT DO NOTHING;

-- Under Specialty Materials
INSERT INTO tech_nodes (revolution_id, parent_id, depth, name, name_zh, description, chokepoint_score)
SELECT p.revolution_id, p.id, 2, n.name, n.name_zh, n.description, n.chokepoint
FROM tech_nodes p
CROSS JOIN (VALUES
    ('Filtration & Chemicals', '过滤与化学品',   'Process chemicals + filtration for fab',           'oligopoly'),
    ('ABF Substrate IP',       'ABF基板IP',      '98% controlled by Ajinomoto — single point of US supply failure', 'monopoly'),
    ('Specialty Gases',        '特种气体',       'Air Products, Linde, Air Liquide',                 'oligopoly'),
    ('Fiber & Glass',          '光纤与玻璃',     'Corning + Japanese cable',                         'oligopoly')
) AS n(name, name_zh, description, chokepoint)
WHERE p.name = 'Specialty Materials' AND p.depth = 1
ON CONFLICT DO NOTHING;


-- ────────────────────────────────────────────────────────────────
-- Depth 3 — Component-level chokepoints (the leaves where companies live)
-- ────────────────────────────────────────────────────────────────

-- Under Advanced Packaging (the mega-chokepoint)
INSERT INTO tech_nodes (revolution_id, parent_id, depth, name, name_zh, description, chokepoint_score, notes)
SELECT p.revolution_id, p.id, 3, n.name, n.name_zh, n.description, n.chokepoint, n.notes
FROM tech_nodes p
CROSS JOIN (VALUES
    ('Packaging Execution (CoWoS)', 'CoWoS封装', 'TSMC dominant; AMKR + ASE secondary',
     'monopoly', 'TSMC CoWoS 60% booked by NVDA alone'),
    ('ABF Substrates Manufacturing', 'ABF基板制造', 'Top-3: Ibiden, Shinko, Unimicron; all Japanese/Taiwanese',
     'oligopoly', 'Only 3-5 companies globally. Lead times 30+ weeks during pandemic.'),
    ('Inspection (Advanced Packaging)', '封装检测', 'CAMT 3D microbump metrology; KLA front-end; ONTO optical',
     'oligopoly', 'CAMT chokepoint: KLA admits cannot match 3D metrology accuracy'),
    ('Bonding Equipment', '键合设备', 'TCB bonding required for every CoWoS package',
     'oligopoly', 'KLIC + BESI + ASMPT. We analyzed KLIC, missed BESI and ASMPT.'),
    ('Precision Dicing/Grinding', '精密切割', 'Disco near-monopoly — every chip must be diced',
     'monopoly', 'Disco 70% share in niches, 35-40% operating margins, $33B. "Without Disco, AI chips cannot be finalized."')
) AS n(name, name_zh, description, chokepoint, notes)
WHERE p.name = 'Advanced Packaging' AND p.depth = 2
ON CONFLICT DO NOTHING;

-- Under Optical Transceivers
INSERT INTO tech_nodes (revolution_id, parent_id, depth, name, name_zh, description, chokepoint_score, notes)
SELECT p.revolution_id, p.id, 3, n.name, n.name_zh, n.description, n.chokepoint, n.notes
FROM tech_nodes p
CROSS JOIN (VALUES
    ('EML Lasers', 'EML激光器',
     'Light source for 200G/400G/3.2T transceivers',
     'duopoly',
     'LITE owns current-gen 200G EML for 1.6T (sole source). COHR positioning 400G D-EML for next-gen 3.2T. Generational competition, not direct — outcome depends on customer transition timing.'),
    ('Silicon Photonics PICs', '硅光PIC',
     'Photonic integrated circuits for current and next-gen optical',
     'oligopoly',
     'TSEM current-gen pluggable SiPho leader ($1.3B contracted 2027). GFS SCALE platform for next-gen CPO. TSMC entering.'),
    ('Optical DSPs', '光学DSP',
     'Digital signal processors for coherent + PAM4',
     'oligopoly',
     'MRVL Coherent DSP family. AVGO PAM4. ALAB retimers + fabric switches.'),
    ('Transceiver Module Assembly', '收发模块组装',
     'Vertically integrated module makers',
     'competitive',
     'COHR vertically integrated. AAOI smaller, 441% YTD. CSCO Acacia. Intel SiPho.')
) AS n(name, name_zh, description, chokepoint, notes)
WHERE p.name = 'Optical Transceivers' AND p.depth = 2
ON CONFLICT DO NOTHING;

-- Under Chip Design
INSERT INTO tech_nodes (revolution_id, parent_id, depth, name, name_zh, description, chokepoint_score, notes)
SELECT p.revolution_id, p.id, 3, n.name, n.name_zh, n.description, n.chokepoint, n.notes
FROM tech_nodes p
CROSS JOIN (VALUES
    ('GPU Architecture', 'GPU架构', 'CUDA ecosystem + competing architectures', 'duopoly', 'NVDA + AMD'),
    ('Custom ASIC Design', '定制ASIC设计', 'Hyperscaler custom silicon partners', 'oligopoly', 'MRVL + AVGO design partners; Google TPU, Amazon Trainium, Meta MTIA in-house'),
    ('EDA Tools', 'EDA工具', 'Chip design starts here — duopoly', 'duopoly', 'SNPS + CDNS, $80B+ each. Consensus but structurally irreplaceable.')
) AS n(name, name_zh, description, chokepoint, notes)
WHERE p.name = 'Chip Design' AND p.depth = 2
ON CONFLICT DO NOTHING;

-- Under Front-end Equipment
INSERT INTO tech_nodes (revolution_id, parent_id, depth, name, name_zh, description, chokepoint_score, notes)
SELECT p.revolution_id, p.id, 3, n.name, n.name_zh, n.description, n.chokepoint, n.notes
FROM tech_nodes p
CROSS JOIN (VALUES
    ('EUV Lithography', 'EUV光刻', 'Only ASML', 'monopoly', NULL),
    ('Etch & Deposition', '刻蚀与沉积', 'AMAT + LRCX duopoly with TEL secondary', 'oligopoly', NULL),
    ('Photoresist', '光刻胶', 'EUV resist is near-monopoly material', 'oligopoly', 'JSR went private 2024. TOK + Shin-Etsu remaining public.')
) AS n(name, name_zh, description, chokepoint, notes)
WHERE p.name = 'Front-end Equipment' AND p.depth = 2
ON CONFLICT DO NOTHING;

-- Under Testing
INSERT INTO tech_nodes (revolution_id, parent_id, depth, name, name_zh, description, chokepoint_score, notes)
SELECT p.revolution_id, p.id, 3, 'System-Level ATE', '系统级ATE', 'Advantest #1 (58% share); Teradyne #2 qualifying on NVDA', 'duopoly', NULL
FROM tech_nodes p
WHERE p.name = 'Testing' AND p.depth = 2
ON CONFLICT DO NOTHING;

-- Under Memory
INSERT INTO tech_nodes (revolution_id, parent_id, depth, name, name_zh, description, chokepoint_score, notes)
SELECT p.revolution_id, p.id, 3, n.name, n.name_zh, n.description, n.chokepoint, n.notes
FROM tech_nodes p
CROSS JOIN (VALUES
    ('HBM (High Bandwidth Memory)', 'HBM', 'AI training/inference memory', 'oligopoly', 'SK Hynix #1, Samsung #2, Micron #3. Uses same CoWoS/bonding supply chain.'),
    ('DRAM',                         'DRAM', 'Standard memory',                     'oligopoly', NULL)
) AS n(name, name_zh, description, chokepoint, notes)
WHERE p.name = 'Memory' AND p.depth = 2
ON CONFLICT DO NOTHING;


-- ────────────────────────────────────────────────────────────────
-- node_companies — link tickers to leaf chokepoint nodes
-- ────────────────────────────────────────────────────────────────

-- Helper: lookup node by name and insert ticker mapping
-- Pattern: SELECT n.id FROM tech_nodes n WHERE n.name = '<node>' AND n.depth = <d>

-- Advanced Packaging chokepoints
INSERT INTO node_companies (node_id, ticker, company_name, role, market_share, market_cap_usd, notes)
SELECT n.id, t.ticker, t.company_name, t.role, t.market_share, t.market_cap_usd, t.notes
FROM tech_nodes n
CROSS JOIN (VALUES
    ('Packaging Execution (CoWoS)',     'TSMC',  'Taiwan Semiconductor', 'leader',     '~80% CoWoS', 800e9, 'CoWoS 60% booked by NVDA alone'),
    ('Packaging Execution (CoWoS)',     'AMKR',  'Amkor Technology',     'challenger', 'small share',   7e9, 'US-based, TSMC-licensed CoWoS, Arizona facility, Apple anchor'),
    ('Packaging Execution (CoWoS)',     '3711.TW','ASE Technology',      'challenger', 'OSAT leader',  20e9, 'World''s largest OSAT, $1B advanced packaging'),

    ('ABF Substrates Manufacturing',    '4062.T',  'Ibiden',            'leader', 'top-3', 8e9,  'Up 881% in 12mo; thesis correct, price wrong at $29B on flat $2.5B rev'),
    ('ABF Substrates Manufacturing',    '6967.T',  'Shinko Electric',   'leader', 'top-3', NULL::double precision, 'Fujitsu subsidiary'),
    ('ABF Substrates Manufacturing',    '3037.TW', 'Unimicron',         'leader', 'top-3', NULL::double precision, NULL),

    ('Inspection (Advanced Packaging)', 'CAMT',  'Camtek',              'leader',     '3D metrology', 7e9, 'KLA admits cannot match 3D microbump algorithm. 17% pullback. 70% AI exposure.'),
    ('Inspection (Advanced Packaging)', 'KLA',   'KLA Corporation',     'adjacent',   'front-end',  194e9, 'Front-end inspection consensus. Different node from CAMT.'),
    ('Inspection (Advanced Packaging)', 'ONTO',  'Onto Innovation',     'adjacent',   'optical inspection', NULL::double precision, NULL),

    ('Bonding Equipment',               'KLIC',     'Kulicke & Soffa', 'leader',     'TCB',  NULL::double precision, 'TCB bonding for CoWoS'),
    ('Bonding Equipment',               'BESI.AS',  'BE Semiconductor', 'leader',     'hybrid bonding', 15e9, 'Dutch. AMAT bought 9% stake for hybrid bonding co-development. Overlooked.'),
    ('Bonding Equipment',               '522.HK',   'ASM Pacific Technology', 'leader', 'die attach + TCB', NULL::double precision, 'HK-listed. Overlooked.'),

    ('Precision Dicing/Grinding',       '6146.T', 'Disco Corporation', 'leader', '70% niche share, near-monopoly', 33e9,
     'Near-monopoly. 35-40% operating margins. 69.5% GM. "Without Disco, AI chips cannot be finalized or packaged." 11% growth fairly valued at $33B; wait cyclical pullback.')
) AS t(node_name, ticker, company_name, role, market_share, market_cap_usd, notes)
WHERE n.name = t.node_name AND n.depth = 3
ON CONFLICT (node_id, ticker) DO NOTHING;

-- ABF Substrate IP (depth-2 monopoly node — Ajinomoto is the IP, not a manufacturer)
INSERT INTO node_companies (node_id, ticker, company_name, role, market_share, market_cap_usd, notes)
SELECT n.id, '2802.T', 'Ajinomoto', 'leader', '98% IP licensing', 15e9,
       'Controls 98% of ABF (Ajinomoto Build-up Film) IP. Every CoWoS package = Ajinomoto ABF inside. US has zero independent ABF substrate source — single point of failure for US semiconductor supply chain. Food company — semi investors don''t look here.'
FROM tech_nodes n
WHERE n.name = 'ABF Substrate IP' AND n.depth = 2
ON CONFLICT (node_id, ticker) DO NOTHING;

-- Optical Transceivers chokepoints
INSERT INTO node_companies (node_id, ticker, company_name, role, market_share, market_cap_usd, notes)
SELECT n.id, t.ticker, t.company_name, t.role, t.market_share, t.market_cap_usd, t.notes
FROM tech_nodes n
CROSS JOIN (VALUES
    ('EML Lasers', 'LITE',  'Lumentum Holdings', 'leader',     '200G EML sole source for current-gen 1.6T', 75e9,
     'Current-gen 200G EML monopoly for 1.6T transceivers. Generational competition with COHR (next-gen 3.2T) — not direct today. Watch via order flow + EML inventory at module assemblers.'),
    ('EML Lasers', 'COHR',  'Coherent Corp.',    'challenger', 'own 400G D-EML for next-gen 3.2T',           NULL::double precision,
     'Has own 400G Differential-EML for 3.2T. NVDA $2B investment. Vertically integrated module maker. Watch: 3.2T hyperscaler design wins.'),

    ('Silicon Photonics PICs', 'TSEM', 'Tower Semiconductor', 'leader',     'current-gen pluggable SiPho',     30e9,
     'SiPho revenue tripled. $1.3B contracted 2027. Only 4-9 analysts. GFS sued them (competitive validation). User found before system did.'),
    ('Silicon Photonics PICs', 'GFS',  'GlobalFoundries',     'challenger', 'next-gen CPO via SCALE platform', NULL::double precision,
     'NVDA/AMD/AVGO/META/MSFT/OpenAI backing. SCALE platform. 19x P/E — cheapest AI semi.'),

    ('Optical DSPs', 'MRVL', 'Marvell Technology', 'leader',     'Coherent DSP family',   NULL::double precision, NULL),
    ('Optical DSPs', 'AVGO', 'Broadcom',           'leader',     'PAM4 DSP',              NULL::double precision, NULL),
    ('Optical DSPs', 'ALAB', 'Astera Labs',        'adjacent',   'retimers + fabric switches', NULL::double precision, '93% YoY, 76% GM, but 70% single-customer (NVDA), $211M insider selling. Dangerous price.'),

    ('Transceiver Module Assembly', 'COHR', 'Coherent Corp.', 'leader',     'vertically integrated', NULL::double precision, NULL),
    ('Transceiver Module Assembly', 'AAOI', 'Applied Optoelectronics', 'emerging', 'aggressive growth', 5e9,
     '441% YTD. $18B unprofitable on $600M revenue. No moat vs LITE/COHR. Pass — no moat.')
) AS t(node_name, ticker, company_name, role, market_share, market_cap_usd, notes)
WHERE n.name = t.node_name AND n.depth = 3
ON CONFLICT (node_id, ticker) DO NOTHING;

-- Chip Design + Front-end + Testing + Memory
INSERT INTO node_companies (node_id, ticker, company_name, role, market_share, market_cap_usd, notes)
SELECT n.id, t.ticker, t.company_name, t.role, t.market_share, t.market_cap_usd, t.notes
FROM tech_nodes n
CROSS JOIN (VALUES
    ('GPU Architecture',     'NVDA', 'NVIDIA',                   'leader',     'CUDA ecosystem', NULL::double precision, 'Past peak consensus — 收获期'),
    ('GPU Architecture',     'AMD',  'AMD',                      'challenger', 'EPYC + Instinct', 762e9, '$762B, 41/41 Buy, ATH — peak consensus 收获期'),

    ('Custom ASIC Design',   'MRVL', 'Marvell Technology',       'leader',     'design partner',   NULL::double precision, '#2 to Broadcom. Custom silicon platform.'),
    ('Custom ASIC Design',   'AVGO', 'Broadcom',                 'leader',     'design partner',   NULL::double precision, NULL),

    ('EDA Tools',            'SNPS', 'Synopsys',                 'leader',     'EDA duopoly', NULL::double precision, 'Consensus but structurally irreplaceable'),
    ('EDA Tools',            'CDNS', 'Cadence',                  'leader',     'EDA duopoly', NULL::double precision, 'Consensus but structurally irreplaceable'),

    ('EUV Lithography',      'ASML', 'ASML',                     'leader',     'EUV monopoly', NULL::double precision, NULL),
    ('Etch & Deposition',    'AMAT', 'Applied Materials',        'leader',     'deposition + etch', NULL::double precision, NULL),
    ('Etch & Deposition',    'LRCX', 'Lam Research',             'leader',     'etch leader', NULL::double precision, NULL),
    ('Etch & Deposition',    '8035.T','Tokyo Electron',          'challenger', 'coater/developer', NULL::double precision, NULL),

    ('Photoresist',          '4185.T', 'Tokyo Ohka Kogyo',       'leader',     'EUV resist', NULL::double precision, NULL),
    ('Photoresist',          '4063.T', 'Shin-Etsu Chemical',     'leader',     'resist + wafers', NULL::double precision, NULL),

    ('System-Level ATE',     '6857.T','Advantest',               'leader',     '58% share, 65% GM, 47% OM', NULL::double precision, 'Quality duopoly, Japan discount'),
    ('System-Level ATE',     'TER',   'Teradyne',                'challenger', 'qualifying on NVDA', NULL::double precision, NULL),

    ('HBM (High Bandwidth Memory)', 'MU', 'Micron Technology',   'challenger', 'US HBM #3', NULL::double precision, 'Data still contaminated per project_mu_data_bug — verify before relying on financials')
) AS t(node_name, ticker, company_name, role, market_share, market_cap_usd, notes)
WHERE n.name = t.node_name AND n.depth = 3
ON CONFLICT (node_id, ticker) DO NOTHING;


-- ────────────────────────────────────────────────────────────────
-- SSD Controllers (Storage depth-2 → depth-3 via subnodes)
-- ────────────────────────────────────────────────────────────────

INSERT INTO node_companies (node_id, ticker, company_name, role, market_share, market_cap_usd, notes)
SELECT n.id, t.ticker, t.company_name, t.role, t.market_share, t.market_cap_usd, t.notes
FROM tech_nodes n
CROSS JOIN (VALUES
    ('SSD Controllers', 'SIMO',    'Silicon Motion',  'leader',     'independent controller', 4e9,
     'Best web-trace find. 105% YoY, 6x P/S. MonTitan enterprise ramp. Wait $180-200 pullback.'),
    ('SSD Controllers', '8299.TW', 'Phison',          'leader',     'dominant independent', NULL::double precision, NULL),
    ('SSD Controllers', 'SNDK',    'SanDisk',         'adjacent',   'NAND + contracted backlog', NULL::double precision, '$42B contracted backlog')
) AS t(node_name, ticker, company_name, role, market_share, market_cap_usd, notes)
WHERE n.name = t.node_name AND n.depth = 2
ON CONFLICT (node_id, ticker) DO NOTHING;


-- ────────────────────────────────────────────────────────────────
-- Power Management ICs (Compute depth-2)
-- ────────────────────────────────────────────────────────────────

INSERT INTO node_companies (node_id, ticker, company_name, role, market_share, market_cap_usd, notes)
SELECT n.id, t.ticker, t.company_name, t.role, t.market_share, t.market_cap_usd, t.notes
FROM tech_nodes n
CROSS JOIN (VALUES
    ('Power Management ICs', 'MPWR',  'Monolithic Power Systems', 'leader',     '70% NVDA Vera Rubin', 78e9, 'Strongest chokepoint, priced. Wait pullback $1,300.'),
    ('Power Management ICs', '6723.T','Renesas Electronics',      'challenger', 'second source',       NULL::double precision, NULL),
    ('Power Management ICs', 'IFX.DE','Infineon Technologies',    'challenger', 'competing',           NULL::double precision, NULL)
) AS t(node_name, ticker, company_name, role, market_share, market_cap_usd, notes)
WHERE n.name = t.node_name AND n.depth = 2
ON CONFLICT (node_id, ticker) DO NOTHING;


-- ────────────────────────────────────────────────────────────────
-- Power + Cooling (depth-2 nodes, populated with companies directly)
-- ────────────────────────────────────────────────────────────────

INSERT INTO node_companies (node_id, ticker, company_name, role, market_share, market_cap_usd, notes)
SELECT n.id, t.ticker, t.company_name, t.role, t.market_share, t.market_cap_usd, t.notes
FROM tech_nodes n
CROSS JOIN (VALUES
    ('Utility Generation', 'CEG',   'Constellation Energy',     'leader',     'largest US nuclear', NULL::double precision, 'Nuclear scarcity. Wait lockup June 30 / DOJ Sept 4.'),
    ('Utility Generation', 'GEV',   'GE Vernova',               'leader',     'natural gas turbines', NULL::double precision, NULL),
    ('Utility Generation', 'SPXC',  'SPX Technologies',         'emerging',   'US transformer maker', NULL::double precision, '5-year industry backlog. Research if datacenter exposure.'),

    ('On-site Power',      'BE',    'Bloom Energy',             'emerging',   'fuel cells for DC', NULL::double precision, NULL),

    ('Power Distribution', 'VRT',   'Vertiv',                   'leader',     'integrated thermal + power', 30e9, '$15B backlog, 2.9x book-to-bill, chip-to-building thermal chain'),
    ('Power Distribution', 'ETN',   'Eaton',                    'leader',     'switchgear + UPS', NULL::double precision, NULL),

    ('Liquid Cooling CDU', 'VRT',   'Vertiv',                   'leader',     'integrated chain', NULL::double precision, '3 acquisitions in 2 months consolidating'),
    ('Liquid Cooling CDU', 'MOD',   'Modine Manufacturing',     'challenger', 'cooling specialist', NULL::double precision, NULL),

    ('Refrigerants',       'CC',    'Chemours',                 'emerging',   'next-gen low-GWP', NULL::double precision, 'Speculative datacenter connection — research needed')
) AS t(node_name, ticker, company_name, role, market_share, market_cap_usd, notes)
WHERE n.name = t.node_name AND n.depth = 2
ON CONFLICT (node_id, ticker) DO NOTHING;


-- ────────────────────────────────────────────────────────────────
-- Specialty Materials direct
-- ────────────────────────────────────────────────────────────────

INSERT INTO node_companies (node_id, ticker, company_name, role, market_share, market_cap_usd, notes)
SELECT n.id, t.ticker, t.company_name, t.role, t.market_share, t.market_cap_usd, t.notes
FROM tech_nodes n
CROSS JOIN (VALUES
    ('Filtration & Chemicals', 'ENTG', 'Entegris',           'leader',     'filtration + chemicals', NULL::double precision, 'Strong oligopolist but not sole-source. 5% growth at 48x. Pass.'),
    ('Fiber & Glass',          'GLW',  'Corning',            'leader',     'Western fiber leader', NULL::double precision, NULL),
    ('Fiber & Glass',          '5801.T','Furukawa Electric', 'challenger', 'Japanese fiber',       NULL::double precision, NULL),
    ('Fiber & Glass',          '5802.T','Sumitomo Electric', 'challenger', 'Japanese fiber',       NULL::double precision, NULL),
    ('Specialty Gases',        'APD',  'Air Products',       'leader',     'specialty gases',      NULL::double precision, NULL),
    ('Specialty Gases',        'LIN',  'Linde',              'leader',     'specialty gases',      NULL::double precision, NULL)
) AS t(node_name, ticker, company_name, role, market_share, market_cap_usd, notes)
WHERE n.name = t.node_name AND n.depth = 2
ON CONFLICT (node_id, ticker) DO NOTHING;


-- ────────────────────────────────────────────────────────────────
-- Refresh supplier_count on tech_nodes for the seeded data
-- ────────────────────────────────────────────────────────────────

UPDATE tech_nodes n
SET supplier_count = (SELECT COUNT(*) FROM node_companies nc WHERE nc.node_id = n.id);
