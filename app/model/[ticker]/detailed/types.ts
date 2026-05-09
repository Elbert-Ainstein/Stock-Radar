export type ForecastPeriod = {
  period: string;
  revenue: number;
  operating_income: number;
  ebitda: number;
  ebitda_margin: number;
  fcf_sbc: number;
  fcf_sbc_margin: number;
  net_income: number;
  fcf: number;
  op_margin: number;
  rev_growth: number;
  is_actual?: boolean;
};

export type HistPeriod = {
  period: string;
  date: string;
  revenue: number | null;
  operating_income: number | null;
  net_income: number | null;
};

export type DeductionStep = {
  label: string;
  formula: string;
  value: number;
  unit: string;
};

export type ScenarioResult = {
  scenario: string;
  price: number;
  discount_rate: number;
  rev_growth_y1: number;
  rev_growth_terminal: number;
  ebitda_margin_target: number;
  fcf_sbc_margin_target: number;
  ev_ebitda_multiple: number;
  ev_fcf_sbc_multiple: number;
  terminal_revenue: number;
  terminal_ebitda: number;
  terminal_fcf_sbc: number;
  ev_from_ebitda: number;
  ev_from_fcf_sbc: number;
  terminal_ev_blended: number;
  pv_ev_blended: number;
  pv_ev_from_ebitda: number;
  pv_ev_from_fcf_sbc: number;
  equity_value: number;
  price_from_ebitda: number;
  price_from_fcf_sbc: number;
  forecast_annual: ForecastPeriod[];
};

export type Payload = {
  ticker: string;
  name: string;
  sector: string;
  target: {
    current_price: number;
    low: number;
    base: number;
    high: number;
    upside_base_pct: number;
    upside_low_pct: number;
    upside_high_pct: number;
    steps: DeductionStep[];
    forecast_quarterly: ForecastPeriod[];
    forecast_annual: ForecastPeriod[];
    scenarios: Record<string, ScenarioResult>;
    drivers: Record<string, number>;
    terminal_year: string;
    ttm_revenue: number;
    ttm_ebitda: number;
    ttm_fcf_sbc: number;
    net_debt: number;
    shares_diluted: number;
    warnings?: string[];
    price_horizon_months?: number;
    price_target_date?: string;
    exit_fiscal_year?: string;
    valuation_method?: string;
  };
  historicals: {
    quarterly: HistPeriod[];
    annual: HistPeriod[];
    ttm: {
      revenue: number | null;
      operating_income: number | null;
      ebitda: number | null;
      fcf: number | null;
    };
  };
  capitalization: {
    price: number;
    market_cap: number;
    shares_diluted: number;
    net_debt: number;
  };
  warnings?: string[];
  error?: string;
};

export type ThesisFilter = { pass: boolean; evidence: string };
export type ThesisItem = {
  name: string;
  probability: number;
  price_impact: number;
  early_signal?: string;
  confirming_signal?: string;
};
export type ThesisData = {
  exists?: boolean;
  thesis_target?: number | null;
  breakout_price?: number | null;
  risk_adj_target?: number | null;
  conviction?: string | null;
  position_size_pct?: number | null;
  buy_below?: number | null;
  trim_above?: number | null;
  prompt_version?: string;
  run_at?: string;
  markdown_path?: string | null;
  spot_at_run?: number | null;
  trigger_reason?: string | null;
  coverage_quality?: string | null;
  cited_domains?: string[];
  filters?: Record<string, ThesisFilter>;
  top_risks?: ThesisItem[];
  top_catalysts?: ThesisItem[];
  kill_triggers?: string[];
};

export type Tab = "thesis" | "setup" | "risks" | "floor" | "income" | "cashflow" | "formulas" | "whatif";

export type HorizonMonths = 12 | 24 | 36;
