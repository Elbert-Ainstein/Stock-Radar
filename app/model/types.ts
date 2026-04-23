// ─── Target engine payload (subset of what /api/model/[ticker] returns) ───
// The brief view uses this as its source of truth for financial numbers, so
// missing-pipeline tickers (like TER before the pipeline runs) still render
// real targets instead of $1B / 20x placeholder garbage.
export interface EngineForecastYear {
  period: string;
  revenue: number;
  operating_income: number;
  net_income: number;
  ebitda: number;
}
export interface EngineScenario {
  price: number;
  terminal_revenue: number;
  terminal_ebitda: number;
  ev_ebitda_multiple: number;
}
export interface ArchetypeInfo {
  primary: "garp" | "cyclical" | "transformational" | "compounder" | "special_situation";
  secondary?: string | null;
  justification?: string;
}

export interface EnginePayload {
  ticker: string;
  archetype?: ArchetypeInfo | null;
  target: {
    current_price: number;
    base: number;
    low: number;
    high: number;
    ttm_revenue: number;
    ttm_ebitda: number;
    shares_diluted: number;
    forecast_annual: EngineForecastYear[];
    scenarios: Record<string, EngineScenario>;
    drivers: Record<string, number>;
    terminal_year: string;
    valuation_method?: string;
    price_horizon_months?: number;
    price_target_date?: string;
    exit_fiscal_year?: string;
    net_debt?: number;
    upside_base_pct?: number;
  };
  capitalization?: {
    price: number;
    market_cap: number;
    shares_diluted: number;
    net_debt: number;
  };
  historicals: { ttm: { revenue: number | null; operating_income: number | null; ebitda?: number | null } };
  warnings?: string[];
  error?: string;
}

// ─── Types ───
export interface StockTarget {
  price: number;
  timeline_years: number;
  valuation_method: string;
  target_multiple: number;
  notes?: string;
  model_defaults?: {
    revenue_b?: number;
    op_margin?: number;
    tax_rate?: number;
    shares_m?: number;
    pe_multiple?: number;
    ps_multiple?: number;
    valuation_method?: "pe" | "ps"; // override auto-detection if set
  };
  scenarios?: Record<string, { probability: number; price: number; trigger: string }>;
}

export interface CriterionNews {
  title: string;
  url: string;
  source: string;
  date: string;
  relevance: number;
}

export interface Criterion {
  id: string;
  label: string;
  detail: string;
  variable: string;
  weight: "critical" | "important" | "monitoring";
  status: "met" | "not_yet" | "failed";
  price_impact_pct?: number;
  price_impact_direction?: "up" | "down_if_failed";
  eval_hint?: string;
  // Auto-evaluation fields (from analyst)
  evaluation_note?: string;
  progress_pct?: number | null;
  current_value?: number | null;
  target_value?: number | null;
  current_label?: string;
  target_label?: string;
  relevant_news?: CriterionNews[];
}

// ─── Event impact types (Phase 1: audit-only, side-by-side with criteria) ───
export interface EventChainLink {
  level: number;
  claim: string;
  confidence: number;
  reasoning: string;
}

export interface EventEvidence {
  date?: string | null;
  source?: string | null;
  url?: string | null;
  headline?: string;
}

export interface ReasonedEvent {
  event_id: string;
  type: string;
  type_display: string;
  summary: string;
  rationale: string;
  direction: "up" | "down";
  magnitude_pct: number;
  probability: number;
  compounded_confidence: number;
  recency_weight: number;
  expected_contribution_pct: number;
  time_horizon_months: number;
  chain: EventChainLink[];
  reasoner: string;
  evidence: EventEvidence[];
  detected_by: string;
  first_seen?: string;
  status: string;
}

export interface ProjectionScorePayload {
  score: number;
  baseline: number;
  contributors: { label: string; delta: number; source: string }[];
  raw_score: number;
  final_explanation: string;
}

export interface BlendPayload {
  base_target: number;
  criteria_pct: number;
  event_pct_raw: number;
  event_weight: number;
  event_pct_weighted: number;
  total_adjustment_pct: number;
  final_target: number;
  formula: string;
}

export interface EventImpactsPayload {
  events: ReasonedEvent[];
  summary: {
    event_adjustment_pct: number;
    raw_sum_pct: number;
    capped: boolean;
    event_count: number;
    up_count: number;
    down_count: number;
  };
  merge_enabled: boolean;
  proposed_target_with_events: number;
  reasoner_available: boolean;
  blend_available?: boolean;
  projection_score?: ProjectionScorePayload;
  blend?: BlendPayload;
  final_target?: number;
}

export interface StockData {
  ticker: string;
  name: string;
  sector: string;
  thesis: string;
  killCondition: string;
  archetype?: ArchetypeInfo | null;
  target: StockTarget;
  criteria: Criterion[];
  currentPrice: number;
  marketCapB: number;
  psRatio: number;
  peRatio: number;
  forwardPe: number;
  revenueGrowthPct: number;
  earningsGrowthPct: number;
  operatingMarginPct: number;
  grossMarginPct: number;
  compositeScore: number;
  valuation: any;
  autoTiers: any[];
  eventImpacts?: EventImpactsPayload;
  killConditionEval?: {
    status: "safe" | "warning" | "triggered";
    confidence: number;
    reasoning: string;
    evidence: string[];
    checked_at: string;
  } | null;
  researchCache?: {
    generated_at?: string;
    sources?: string[];
    quant_snapshot?: Record<string, any>;
  } | null;
}

export interface Props {
  stocks: StockData[];
  meta: { generatedAt: string; scoutsActive: string[]; scoutDetails: any[] };
  initialTicker?: string;
}

// ─── Valuation Methods ───
export type ValuationMethod = "pe" | "ps" | "cyclical";

export interface ValuationMethodInfo {
  method: ValuationMethod;
  label: string;
  multipleLabel: string;
  justification: string;
  reasons: string[];
}
