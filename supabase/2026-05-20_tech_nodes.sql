-- ═══════════════════════════════════════════════════════════════
-- PHASE 5.6 — Technology Web (tech_nodes + node_companies)
-- 2026-05-20  (BUILD_PLAN-83703dd5 Session 2 addendum §A; spec at specs/04_technology_web.md)
--
-- The linear wave map misses lateral connections. The Web traces every node
-- 4 levels deep and maps ALL companies at each chokepoint. This is the
-- structure that would have surfaced TSEM automatically (lateral trace:
-- "who ELSE operates at this node?" after finding GFS in silicon photonics).
--
-- Companion methodology change: when a chokepoint niche is identified,
-- discovery_pipeline MUST ask "who ELSE operates here?" — checks patent
-- lawsuits, customer overlap, competitor maps. Documented in BUILD_PLAN
-- addendum §A.
--
-- NOTE on ticker references: node_companies.ticker is a TEXT column rather
-- than an FK to the `tickers` VIEW (Postgres doesn't allow FKs to views).
-- The existing `stocks` table has UNIQUE(ticker), so we could FK there if
-- we want stricter integrity later. For v1 keep flexible — tech web
-- includes private and foreign-listed companies that aren't in `stocks`.
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS tech_nodes (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    revolution_id       bigint NOT NULL REFERENCES revolutions(id) ON DELETE CASCADE,
    parent_id           bigint REFERENCES tech_nodes(id) ON DELETE CASCADE,
    depth               int NOT NULL CHECK (depth IN (0, 1, 2, 3, 4)),
                                                            -- 0=revolution root
                                                            -- 1=system (Compute, Networking, Storage, Power, Cooling, Specialty Materials)
                                                            -- 2=subsystem (e.g. Advanced Packaging within Compute)
                                                            -- 3=component (e.g. ABF Substrates within Advanced Packaging)
                                                            -- 4=optional sub-component (e.g. specific substrate IP)
    name                text NOT NULL,                      -- English name
    name_zh             text,                               -- Chinese name (optional)
    description         text,                               -- 1-2 sentence summary
    supplier_count      int,                                -- count of node_companies at this leaf
    chokepoint_score    text CHECK (chokepoint_score IN ('monopoly','duopoly','oligopoly','competitive','unknown')
                                     OR chokepoint_score IS NULL),
                                                            -- monopoly: 1 supplier, ≥90% share (e.g. Ajinomoto ABF IP)
                                                            -- duopoly: 2 suppliers, structural barrier (e.g. SNPS+CDNS EDA)
                                                            -- oligopoly: 3-5 suppliers (e.g. ABF substrate makers)
                                                            -- competitive: 6+ suppliers, no structural barrier
    notes               text,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tech_nodes_revolution    ON tech_nodes (revolution_id);
CREATE INDEX IF NOT EXISTS idx_tech_nodes_parent        ON tech_nodes (parent_id);
CREATE INDEX IF NOT EXISTS idx_tech_nodes_depth         ON tech_nodes (depth);
CREATE INDEX IF NOT EXISTS idx_tech_nodes_chokepoint    ON tech_nodes (chokepoint_score)
    WHERE chokepoint_score IN ('monopoly','duopoly');


CREATE TABLE IF NOT EXISTS node_companies (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    node_id             bigint NOT NULL REFERENCES tech_nodes(id) ON DELETE CASCADE,
    ticker              text NOT NULL,                      -- 'CAMT', 'LITE', 'Ajinomoto/2802.T', 'TSMC' (text, not FK)
    company_name        text,                               -- 'Camtek Ltd' for display
    role                text CHECK (role IN ('leader','challenger','emerging','private','adjacent')
                                     OR role IS NULL),
                                                            -- leader: dominant supplier at this node
                                                            -- challenger: gaining share (e.g. COHR D-EML for next-gen)
                                                            -- emerging: new entrant, early traction
                                                            -- private: not publicly traded
                                                            -- adjacent: related but not direct chokepoint
    market_share        text,                               -- '70%' or '98% (IP licensing)' — free-text
    market_cap_usd      double precision,                   -- approximate, for sizing the node viz
    notes               text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (node_id, ticker)
);

CREATE INDEX IF NOT EXISTS idx_node_companies_node      ON node_companies (node_id);
CREATE INDEX IF NOT EXISTS idx_node_companies_ticker    ON node_companies (ticker);
CREATE INDEX IF NOT EXISTS idx_node_companies_role      ON node_companies (role);


-- ────────────────────────────────────────────────────────────────
-- Views
-- ────────────────────────────────────────────────────────────────

-- All depth-3+ chokepoint nodes (the leaves where companies actually live)
CREATE OR REPLACE VIEW leaf_tech_nodes AS
SELECT n.*, r.name_cn AS revolution_name_cn, r.name_en AS revolution_name_en,
       p.name AS parent_name
FROM tech_nodes n
JOIN revolutions r ON r.id = n.revolution_id
LEFT JOIN tech_nodes p ON p.id = n.parent_id
WHERE n.depth >= 3;

-- Monopoly + duopoly chokepoints across all revolutions — the "hidden choke" feed
CREATE OR REPLACE VIEW hidden_chokepoints AS
SELECT
    n.id            AS node_id,
    n.name          AS node_name,
    n.name_zh       AS node_name_zh,
    n.chokepoint_score,
    n.description,
    r.name_cn       AS revolution_cn,
    array_agg(DISTINCT nc.ticker ORDER BY nc.ticker) AS tickers,
    array_agg(DISTINCT nc.role)                       AS roles,
    COUNT(nc.id)    AS supplier_count
FROM tech_nodes n
JOIN revolutions r ON r.id = n.revolution_id
LEFT JOIN node_companies nc ON nc.node_id = n.id
WHERE n.chokepoint_score IN ('monopoly','duopoly')
GROUP BY n.id, n.name, n.name_zh, n.chokepoint_score, n.description, r.name_cn
ORDER BY n.chokepoint_score, supplier_count;

-- All nodes a ticker appears at — useful for cross-cutting names like MPWR
CREATE OR REPLACE VIEW ticker_node_membership AS
SELECT
    nc.ticker,
    nc.company_name,
    array_agg(DISTINCT n.name ORDER BY n.name) AS nodes,
    array_agg(DISTINCT r.name_cn ORDER BY r.name_cn) AS revolutions,
    COUNT(DISTINCT n.id) AS node_count
FROM node_companies nc
JOIN tech_nodes n ON n.id = nc.node_id
JOIN revolutions r ON r.id = n.revolution_id
GROUP BY nc.ticker, nc.company_name
ORDER BY node_count DESC, nc.ticker;
