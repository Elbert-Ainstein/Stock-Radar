/**
 * Single-source-of-truth registries for the Stock Radar frontend.
 *
 * ALL scout names, valuation methods, archetypes, and lifecycle stages are
 * defined here.  Every TypeScript module that needs these constants MUST
 * import from this file — never re-define the lists locally.
 *
 * Python mirror: scripts/registries.py
 */

// ─── SCOUTS ──────────────────────────────────────────────────────────────────

export interface ScoutRegistryEntry {
  label: string;
  requiresKey: boolean;
  keyName?: string;
}

/** Canonical registry of all scouts with metadata. */
export const SCOUT_REGISTRY: Record<string, ScoutRegistryEntry> = {
  quant:        { label: "Quant Screener",        requiresKey: false },
  insider:      { label: "Insider Tracker",       requiresKey: false },
  social:       { label: "Social Sentiment",      requiresKey: false },
  news:         { label: "News Scanner",          requiresKey: true, keyName: "PERPLEXITY_API_KEY" },
  catalyst:     { label: "Catalyst Tracker",      requiresKey: true, keyName: "PERPLEXITY_API_KEY" },
  moat:         { label: "Moat Analyzer",         requiresKey: true, keyName: "PERPLEXITY_API_KEY" },
  fundamentals: { label: "Business Fundamentals", requiresKey: true, keyName: "ANTHROPIC_API_KEY" },
  filings:      { label: "SEC Filings",           requiresKey: false },
  youtube:      { label: "YouTube Intel",         requiresKey: true, keyName: "GEMINI_API_KEY" },
} as const;

/** All scout names as an ordered list. */
export const ALL_SCOUTS = Object.keys(SCOUT_REGISTRY);

/** Scouts that run without any paid API key. */
export const FREE_SCOUTS = ALL_SCOUTS.filter(s => !SCOUT_REGISTRY[s].requiresKey);

// ─── ARCHETYPES ──────────────────────────────────────────────────────────────

export const ALL_ARCHETYPES = [
  "garp",
  "cyclical",
  "transformational",
  "compounder",
  "special_situation",
] as const;

export type Archetype = (typeof ALL_ARCHETYPES)[number];

// ─── VALUATION METHODS ───────────────────────────────────────────────────────

/** Methods the LLM can select (pipeline input). */
export const LLM_VALUATION_METHODS = ["pe", "ps"] as const;

/** All methods including engine-derived ones (cyclical inferred from archetype). */
export const ALL_VALUATION_METHODS = ["pe", "ps", "cyclical"] as const;

export type ValuationMethod = (typeof ALL_VALUATION_METHODS)[number];

// ─── LIFECYCLE ───────────────────────────────────────────────────────────────

export const ALL_LIFECYCLE_STAGES = [
  "startup",
  "high_growth",
  "mature_growth",
  "mature_stable",
  "decline",
] as const;

export type LifecycleStage = (typeof ALL_LIFECYCLE_STAGES)[number];

export const ALL_MOAT_WIDTHS = ["none", "narrow", "wide"] as const;
export type MoatWidth = (typeof ALL_MOAT_WIDTHS)[number];

// ─── CIRCUIT BREAKER THRESHOLDS ──────────────────────────────────────────────
// Rigid container — values may evolve but the checks always exist.

/** Maximum target-to-price ratio before extreme prediction warning. */
export const MAX_TARGET_PRICE_RATIO = 3.0;

/** Maximum target change (fraction) between runs before flagging. */
export const MAX_TARGET_CHANGE_FRAC = 0.30;
