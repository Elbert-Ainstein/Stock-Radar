-- ═══════════════════════════════════════════════════════════════
-- SEED — 量子计算革命 (4th revolution) + 8 waves
-- 2026-05-20  (BUILD_PLAN-83703dd5 Session 2 addendum §E)
--
-- Quantum is the 4th revolution we're tracking. ALL waves are pre-commercial
-- (远见期 / Moonshot). Only public chokepoint identified: Oxford Instruments
-- (~$2B, dilution refrigerators). 10-15 years behind AI. Position size guidance
-- per Hume: tiny positions (1-3%) only.
--
-- Idempotent — ON CONFLICT skips if revolution already exists.
-- ═══════════════════════════════════════════════════════════════

INSERT INTO revolutions (name_cn, name_en, description, market_size, timeline, timing_category, created_by) VALUES
    ('量子计算革命', 'Quantum Computing Revolution',
     'Quantum computing buildout: critical materials → qubit hardware → control electronics → software stack → networking. All waves pre-commercial; 10-15 years behind AI. Only public chokepoint is Oxford Instruments (dilution refrigerators). Moonshot allocation only.',
     'TBD (pre-commercial)', '2026-2040+', '远见期', 'system')
ON CONFLICT (name_cn) DO UPDATE SET timing_category = EXCLUDED.timing_category;


-- 8 quantum waves, all 远见期
INSERT INTO waves (revolution_id, wave_number, name_cn, name_en, core_need, chokepoint, lifecycle, is_junction, timing_category, notes)
SELECT r.id, w.wn, w.cn, w.en, w.core, w.choke, w.lc, w.is_j, '远见期', w.notes
FROM revolutions r
CROSS JOIN (VALUES
    (0, '关键材料',       'Critical Materials',
     'isotopically pure silicon, rare cryogenic materials, helium-3',
     'isotope enrichment + helium-3 supply (mostly state-controlled)',
     'pre_discovery', false,
     'Helium-3 is the bottleneck. US strategic reserves limited. Russian/Chinese supplies geopolitically constrained.'),

    (1, '量子比特硬件',   'Qubit Hardware',
     'superconducting, trapped ion, photonic, neutral atom qubit fabrication',
     'fabrication processes for specific qubit modalities',
     'pre_discovery', false,
     'IBM (superconducting), IonQ (trapped ion, public ★), Quantinuum (Honeywell, private), Atom Computing (neutral atom). RGTI public, struggling.'),

    (2, '低温与控制',     'Cryogenics & Control Electronics',
     'dilution refrigerators reaching <20mK; RF control electronics',
     'dilution refrigerators (Oxford Instruments near-monopoly)',
     'pre_discovery', false,
     '★ Oxford Instruments (OXIG.L, ~$2B) is the only public chokepoint identified. Bluefors private. Zurich Instruments private. Control electronics fragmented.'),

    (3, '量子纠错',       'Quantum Error Correction',
     'logical-qubit overhead reduction; surface codes; LDPC codes',
     'algorithm + hardware co-design',
     'pre_discovery', false,
     'Mostly research labs. IBM/Google in-house. No public chokepoint identified.'),

    (4, '量子算法',       'Quantum Algorithms',
     'Shor, Grover, VQE, QAOA, quantum simulation',
     'specific use-case algorithms with commercial proof',
     'pre_discovery', false,
     'Pre-NISQ-utility. Most "quantum advantage" claims are narrow. Open question: which problems break first.'),

    (5, '量子软件栈',     'Quantum Software Stack',
     'Qiskit, Cirq, OpenQASM, transpilers, error mitigation',
     'middleware between hardware and algorithms',
     'pre_discovery', false,
     'IBM Qiskit (open source), Google Cirq, Quantinuum software. No standalone public play.'),

    (6, '量子网络',       'Quantum Networking',
     'quantum repeaters, entanglement distribution, QKD',
     'quantum repeaters that maintain entanglement >1km',
     'pre_discovery', false,
     'Toshiba (QKD), ID Quantique (private). Repeaters still research-stage. China leads in QKD deployment.'),

    (7, '量子云与商业化', 'Quantum Cloud & Commercialization',
     'cloud-accessible quantum compute; first commercial proofs',
     'demonstrated commercial use case beating classical',
     'pre_discovery', false,
     'IBM Quantum Network, Amazon Braket, Azure Quantum. Revenue is consulting + cloud credits, not problem-solving.')
) AS w(wn, cn, en, core, choke, lc, is_j, notes)
WHERE r.name_cn = '量子计算革命'
ON CONFLICT (revolution_id, wave_number, name_cn) DO NOTHING;


-- Seed Oxford Instruments at Wave 2 (Cryogenics) as the only public chokepoint
-- NOTE: Oxford Instruments isn't in stocks table (LSE-listed). ticker_revolutions
-- accepts arbitrary text tickers. Adding for completeness of the wave map.
INSERT INTO ticker_revolutions (ticker, wave_id, lifecycle, notes, timing_category, assigned_by)
SELECT 'OXIG.L', w.id, 'pre_discovery',
       'Only public chokepoint in quantum revolution. Dilution refrigerators reach <20mK required for superconducting qubits. ~$2B market cap. Moonshot allocation only (1-3% per user_position_sizing_discipline).',
       '远见期', 'system'
FROM waves w
JOIN revolutions r ON r.id = w.revolution_id
WHERE r.name_cn = '量子计算革命' AND w.wave_number = 2
ON CONFLICT (ticker, wave_id) DO NOTHING;

-- IonQ and RGTI at Wave 1 (Qubit Hardware) — public but high-risk
INSERT INTO ticker_revolutions (ticker, wave_id, lifecycle, notes, timing_category, assigned_by)
SELECT t.ticker, w.id, 'pre_discovery', t.note, '远见期', 'system'
FROM waves w
JOIN revolutions r ON r.id = w.revolution_id
CROSS JOIN (VALUES
    ('IONQ', 'Trapped-ion qubits. Public but unprofitable; valuation reflects optionality, not revenue. Moonshot.'),
    ('RGTI', 'Superconducting qubits. Struggling commercially; near-zero revenue. Highest-risk moonshot.')
) AS t(ticker, note)
WHERE r.name_cn = '量子计算革命' AND w.wave_number = 1
ON CONFLICT (ticker, wave_id) DO NOTHING;
