-- ════════════════════════════════════════════════════════════════════
-- 2026-04-20 — Event-impacts column + AMD watchlist backfill
-- Apply via Supabase SQL Editor (Dashboard → SQL Editor → New query → Run)
-- Safe to re-run; both blocks are idempotent.
-- ════════════════════════════════════════════════════════════════════

-- 1) Add event_impacts column to analysis (resilient-save was stripping it)
ALTER TABLE analysis
  ADD COLUMN IF NOT EXISTS event_impacts JSONB DEFAULT '{}'::JSONB;


-- 2) Backfill AMD watchlist config (target + criteria) so event_impacts has
--    something to scale against. Anchored on $278 price, $34.6B FY25 revenue,
--    34% growth, fwd PE 25.4. 3-year base case = $500 (PE path).
UPDATE stocks
SET
  thesis = 'AMD is structurally taking server CPU share from Intel (41.3% in Q3 2025) while Instinct GPU establishes credible #2 AI accelerator position. Meta $60B 5-year agreement + 160M-share warrant validates revenue durability. Revolutionary thesis: AMD becomes the AI-infra share-taker that compounds at 30%+ for 3+ years.',
  kill_condition = 'Instinct GPU revenue stalls below $10B annual run rate by end of FY2026, AND server CPU share gains plateau or reverse for two consecutive quarters.',
  tags = '["ai_infrastructure","semiconductors","share_taker","revolutionary"]'::JSONB,

  target_price = 500,
  timeline_years = 3,
  valuation_method = 'pe',
  target_multiple = 32,
  target_notes = 'Target $500 by FY2028 derives from: revenue $34.6B → $85B (AI Instinct ramp + EPYC share gains), op margin 23% → 32% (data-center mix), 13% tax, 1620M shares, 32x PE = $14.7 EPS × 32 = $470 + small buffer. Required conditions: Instinct annual revenue exits FY2026 above $15B, server CPU share crosses 45% by FY2027, no major EUV/foundry disruption.',

  model_defaults = '{
    "shares_m": 1620,
    "tax_rate": 0.13,
    "op_margin": 0.32,
    "revenue_b": 85,
    "pe_multiple": 32,
    "ps_multiple": null,
    "valuation_method": "pe"
  }'::JSONB,

  scenarios = '{
    "base": {
      "price": 500,
      "trigger": "Instinct revenue ramps to $20B annual run rate by end of FY2027, server CPU share reaches 45%, op margin expands to 32%. AI infra capex stays elevated through 2028.",
      "probability": 0.50
    },
    "bull": {
      "price": 720,
      "trigger": "Meta $60B contract pulls forward, Instinct hits $30B run rate by FY2027, AMD captures meaningful inference share, op margin expands to 35%, multiple re-rates to 38x on durable share-take story.",
      "probability": 0.25
    },
    "bear": {
      "price": 230,
      "trigger": "AI capex cycle peaks mid-2026, Instinct revenue stalls below $12B due to NVIDIA Blackwell/Rubin lock-in, EPYC share gains plateau at 42%, op margin compresses to 25%.",
      "probability": 0.25
    }
  }'::JSONB,

  criteria = '[
    {
      "id": "instinct_revenue_ramp",
      "label": "Instinct GPU annual revenue exits FY2026 above $15B",
      "detail": "Instinct (MI300X / MI350 / MI400) is the revolutionary lever. $15B+ exit run-rate confirms AMD is the credible #2 AI accelerator. Below this, the AI thesis collapses to a server-CPU-only story.",
      "status": "not_yet",
      "weight": "critical",
      "variable": "R",
      "eval_hint": "AMD discloses Instinct/data-center GPU annual revenue >= $15B by Q4 FY2026 earnings.",
      "price_impact_pct": 30,
      "price_impact_direction": "down_if_failed"
    },
    {
      "id": "server_cpu_share_gain",
      "label": "Server CPU revenue share reaches 45% by Q2 FY2027",
      "detail": "EPYC share-take from Intel is the durable secondary engine. 41.3% in Q3 2025 → 45% trajectory adds ~$8B incremental data-center revenue.",
      "status": "not_yet",
      "weight": "critical",
      "variable": "R",
      "eval_hint": "Mercury Research / Counterpoint reports server CPU revenue share >= 45% by Q2 FY2027.",
      "price_impact_pct": 20,
      "price_impact_direction": "down_if_failed"
    },
    {
      "id": "op_margin_expansion",
      "label": "Operating margin expands to 30%+ by FY2027",
      "detail": "Data-center revenue mix shift drives op-margin from 23% to 30%+. Critical for the EPS/PE math: every 1% margin = ~$0.85B additional operating income.",
      "status": "not_yet",
      "weight": "critical",
      "variable": "M",
      "eval_hint": "Quarterly non-GAAP op margin >= 30% in any quarter of FY2027.",
      "price_impact_pct": 25,
      "price_impact_direction": "down_if_failed"
    },
    {
      "id": "meta_contract_execution",
      "label": "Meta $60B agreement executes on schedule (6 GW deployed by FY2030)",
      "detail": "Meta deal validates AMD as a hyperscaler-grade AI infra supplier. On-schedule deployment unlocks similar deals with other hyperscalers.",
      "status": "not_yet",
      "weight": "important",
      "variable": "R",
      "eval_hint": "Meta confirms first 1 GW of Instinct GPUs deployed by Q4 FY2026 in their capex disclosures.",
      "price_impact_pct": 18,
      "price_impact_direction": "down_if_failed"
    },
    {
      "id": "rocm_software_maturity",
      "label": "ROCm closes the CUDA gap on inference workloads",
      "detail": "Software moat is the bear case. If ROCm reaches CUDA parity on inference (where AMD has best chance), it removes the structural lock-in advantage NVIDIA holds.",
      "status": "not_yet",
      "weight": "important",
      "variable": "R",
      "eval_hint": "Independent benchmarks show ROCm achieves >=90% of CUDA throughput on PyTorch inference for major LLMs by FY2027.",
      "price_impact_pct": 15,
      "price_impact_direction": "down_if_failed"
    },
    {
      "id": "tsmc_capacity_secured",
      "label": "TSMC N3/N2 capacity allocation secured for FY2027 ramp",
      "detail": "Supply constraints could cap upside even if demand is there. AMD must secure leading-edge capacity at TSMC against NVIDIA / Apple competition.",
      "status": "not_yet",
      "weight": "important",
      "variable": "R",
      "eval_hint": "Management discloses N2 / N3 wafer allocation visibility for full FY2027.",
      "price_impact_pct": 12,
      "price_impact_direction": "down_if_failed"
    },
    {
      "id": "fcf_generation",
      "label": "Free cash flow exceeds $12B by FY2027",
      "detail": "FCF supports buybacks and de-risks the multiple. $12B FCF on $80B+ revenue = 15% FCF margin, peer-leading.",
      "status": "not_yet",
      "weight": "important",
      "variable": "F",
      "eval_hint": "TTM FCF >= $12B by Q4 FY2027 reporting.",
      "price_impact_pct": 10,
      "price_impact_direction": "down_if_failed"
    },
    {
      "id": "client_pc_share_durability",
      "label": "Desktop x86 unit share sustains above 35% through FY2027",
      "detail": "Client PC business funds the AI bets. Must hold ground against Intel Lunar Lake / Panther Lake refresh cycle.",
      "status": "not_yet",
      "weight": "important",
      "variable": "R",
      "eval_hint": "Mercury Research desktop x86 unit share >= 35% in any quarter of FY2027.",
      "price_impact_pct": 8,
      "price_impact_direction": "down_if_failed"
    },
    {
      "id": "embedded_segment_recovery",
      "label": "Embedded (Xilinx) segment returns to growth by FY2026",
      "detail": "Xilinx acquisition has been a drag. Recovery signals demand normalization in industrial/comms end-markets.",
      "status": "not_yet",
      "weight": "monitoring",
      "variable": "R",
      "eval_hint": "Embedded segment revenue grows YoY for 2 consecutive quarters in FY2026.",
      "price_impact_pct": 5,
      "price_impact_direction": "down_if_failed"
    },
    {
      "id": "gaming_segment_stability",
      "label": "Gaming segment stabilizes above $1B/quarter",
      "detail": "Console cycle headwind. Stabilization removes a recurring negative variance line.",
      "status": "not_yet",
      "weight": "monitoring",
      "variable": "R",
      "eval_hint": "Gaming segment revenue >= $1B in any quarter of FY2026.",
      "price_impact_pct": 5,
      "price_impact_direction": "down_if_failed"
    },
    {
      "id": "insider_alignment",
      "label": "No material insider selling above grant-vesting routine",
      "detail": "Lisa Su + leadership team conviction. Above-routine selling would signal internal concern about thesis durability.",
      "status": "not_yet",
      "weight": "monitoring",
      "variable": "S",
      "eval_hint": "Net insider selling outside routine 10b5-1 plans stays below $50M per quarter.",
      "price_impact_pct": 6,
      "price_impact_direction": "down_if_failed"
    },
    {
      "id": "competitive_moat_widening",
      "label": "ROCm / ZenDNN ecosystem grows to >=500 enterprise deployments",
      "detail": "Customer count is the leading indicator of ecosystem moat. Without ecosystem breadth, share gains revert.",
      "status": "not_yet",
      "weight": "monitoring",
      "variable": "M",
      "eval_hint": "AMD discloses >=500 production ROCm deployments at any FY2027 investor event.",
      "price_impact_pct": 7,
      "price_impact_direction": "down_if_failed"
    }
  ]'::JSONB,

  active = TRUE,
  updated_at = NOW()
WHERE ticker = 'AMD';


-- 3) Verification queries — run these after the UPDATE to confirm
-- SELECT ticker, target_price, timeline_years, jsonb_array_length(criteria) AS criteria_count FROM stocks WHERE ticker IN ('AMD','LITE','TER');
-- SELECT column_name FROM information_schema.columns WHERE table_name='analysis' AND column_name='event_impacts';
