# Stock Radar — Frontend Redesign Brief

**Audience:** Claude (acting as senior product designer + frontend engineer).
**Goal:** Deliver a clean, professional, information-dense interface for a solo discretionary equity research tool that the operator uses daily to make real money decisions.

---

## 1. What this product actually is

Stock Radar is a single-operator equity research platform built around a Claude-driven "thesis engine" that produces investment theses with explicit conviction and position-sizing recommendations. It is **not** a retail trading app, a marketing landing page, or a SaaS dashboard for a team. It is a serious analyst's working surface — the operator opens it multiple times per day, reads dense outputs, types notes, and acts on the calls.

The user has a multi-month track record of ~40%/month equity returns from manual research conversations and is building this product to systematize that workflow into a progressively-more-autonomous trader. Treat the visual design accordingly: this is the cockpit for someone who already knows what they're doing, not a wizard for a beginner. Bias toward the aesthetic of a Bloomberg terminal, FactSet workstation, or Koyfin — but cleaner, calmer, and more typographically refined than any of those.

**Anti-patterns to avoid:**
- Marketing-page aesthetics: hero sections, gradients, big illustrations, social proof rows
- Generic "modern SaaS" templates (Vercel Analytics, Stripe Dashboard, Linear-clone): too much whitespace, too few numbers per inch
- Toy-like animation: page transitions, parallax, micro-bouncy hover states
- Beginner-friendly hand-holding: tooltips that explain what P/E means, "Welcome!" empty states, onboarding overlays
- Hiding real information on smaller screens: use scroll, not progressive disclosure, when content is genuinely needed
- Dark mode as the only mode (operator wants both; both must be equally polished)

**Aspirational reference points:**
- Bloomberg Terminal (information density, monospace numerics, subdued chrome)
- The Browser Company / Arc (typographic care, restraint)
- Vercel docs (light mode that isn't washed out)
- Stripe API reference (calm density)
- A really good print financial newspaper laid out by a designer who knows InDesign

The result should feel like a tool that takes the user seriously.

---

## 2. The architectural framing the design MUST respect

The product has a strong opinion baked into its data model. The design must make this opinion visible.

**The thesis is the headline.** Each watched stock has a Claude-generated V3 thesis with a `thesis_target`, `conviction` level (HIGH / MEDIUM / LOW / BROKEN), `position_size_pct`, `breakout_price`, `risk_adj_target`, `buy_below`, `trim_above`, plus structured `top_risks`, `top_catalysts`, `kill_triggers`, and a 5-filter setup quality grid. This is the dominant view.

**The DCF is the floor.** A separate engine produces a conservative discounted-cash-flow target (`floor_low`, `floor_base`, `floor_high`). The DCF is positioned as the downside anchor, NOT the headline. Visually it should sit below or behind the thesis, never in equal billing. When the thesis target and DCF base disagree, that drift is itself a diagnostic signal worth surfacing ("engine corroborates" / "thesis above floor" / "thesis below floor").

**Conviction colors are load-bearing.** HIGH = emerald, MEDIUM = yellow, LOW = orange, BROKEN = red. These map to position-sizing decisions, so they must be unambiguous and accessible in both light and dark modes. Never use these colors decoratively for non-conviction elements.

**Memory accumulates; Hume Notes are sacred.** The system maintains a per-ticker `memory.md` document with sections like "Stable Facts", "Recent Thesis History", "Persistent Catalysts/Risks", "Resolved", and a verbatim "Hume Notes" section. The Hume Notes section is preserved verbatim across all automated re-runs — the design must clearly distinguish the user's own writing from machine-generated content.

---

## 3. Pages and what lives on each

### 3.1 Watchlist (`/`)
Default page. Shows all 10–20 actively-tracked tickers as a list (not a grid; horizontal density matters more than card-iness).

Per-row data:
- Ticker (large, monospace)
- Company name (small, beneath ticker)
- Current price + intraday change (signed, colored)
- Currency badge (USD / HKD / EUR — small chip)
- Monitor Score (0–10, large number with sparkline of last 30 days)
- **Thesis target + conviction badge** (this is the most-glanced field — it must be visible at every breakpoint)
- 5-filter setup quality (pass/fail dots, tiny — only as a hover-revealed detail or at md+)
- Sector tag (small chip)
- Scout-bullishness ratio (e.g. "4/9 bullish")
- Last-thesis-run timestamp (relative — "3h ago")

Top of page chrome:
- Logo + "Stock Radar" + nav links (Watchlist, Discovery, Models, Ask AI, Logs)
- Theme toggle (dark/light)
- "Run pipeline" / "Stop pipeline" buttons (with subtle "running" state indicator)
- "Run all theses" button (primary CTA — kicks off Opus thesis runs in parallel for the whole watchlist; shows live `done/total` counter while running)

Sort/filter affordance:
- Sort by Score / Conviction / Upside / Sector / Last-run
- Filter by conviction tier (toggle chips)
- No fancy multi-faceted search panel — this is a 20-row list, not a CRM

### 3.2 Stock Detail (expanded inline OR `/stock/[ticker]`)
When a row is clicked, the row expands to reveal a detail panel (or routes to a full page — designer's call, both are acceptable). Panel shows:

1. **Thesis Headline strip** (top, dominant): thesis target, conviction badge, position size, breakout price, buy-below, trim-above, "X% upside from current". This is the single most important view in the entire product — get it right.
2. **Setup Quality** — five filter tiles (demand_inflecting, ceiling_visible, best_competitor, complete_chain, macro_supportive), each pass/fail with one-line evidence
3. **Top Risks** (with probability × price-impact, plus "Watch:" early signal)
4. **Top Catalysts** (with probability × price-impact, plus "Confirms:" signal)
5. **Kill Triggers** — bulleted "sell if" list
6. **Hume Notes editor** — large textarea, monospace, with explicit "this is your verbatim space" framing
7. **Memory Panel** — collapsible sections from `memory.md` (excluding Hume Notes which has its own editor above). Stale and Resolved sections collapsed by default.
8. **Scout Signals** — 9 scouts (Fundamentals, News, Filings, Insider, Catalyst, Quant, Social, Discovery, Moat) each with a one-line summary and signal direction
9. **Two affordances at the bottom:** "What-If Sandbox" (slider playground) and "Full Workbook" (deep DCF + financials view)

### 3.3 Models — picker (`/model`)
Grid or list of all watchlist tickers with their current DCF target. Lightweight — this is just a launcher into the Detailed Model view. Each card shows ticker, name, current price, DCF base, and a "Open Workbook" button.

### 3.4 Model Detail (`/model/[ticker]/detailed`)
The deep workbook. Tabs (in this order, default to first):

1. **Thesis** — re-renders the thesis headline with destination/breakout/risk-adj/conviction tiles
2. **Setup** — five filters with evidence (same data as detail panel)
3. **Risks & Catalysts** — full risks + catalysts + kill triggers
4. **Floor (DCF)** — yellow framing banner ("this is the floor, not the headline"); shows the DCF summary tiles, scenario grid, and a drift indicator vs. the thesis
5. **Income** — quarterly + annual income statement projections
6. **Cash** — cashflow projections
7. **Formulas** — explicit deduction steps showing how the DCF target was computed
8. **What-If** — sliders for growth/margin/multiple/discount-rate that recompute the target live

Page header:
- Ticker + company name
- Sector + currency badge
- Horizon picker (12mo / 24mo / 36mo)
- Excel download button (live formulas)
- Back-to-picker link

Above the tab strip but below the page header: a **thesis anchor strip** (emerald) with thesis_target, conviction, breakout, upside-from-current. Below that: a **DCF summary grid** (Current / Downside / Floor base / Upside) — this grid must visibly read as secondary to the thesis strip above it.

### 3.5 Discovery (`/discovery`)
A list/feed of newly-scouted candidate tickers that aren't yet in the watchlist. Each card: ticker, why-this-came-up reason, "Add to watchlist" button. Lightweight.

### 3.6 Ask AI (`/ask`)
A clean Q&A interface — single textarea, response area below. Used for ad-hoc questions across the entire dataset. Should feel like ChatGPT but stripped to essentials and themed to match the rest of the product.

### 3.7 Logs (`/logs`)
Pipeline run history. Reverse-chronological list of runs with: timestamp, mode (full / scouts-only / rebuild-only / theses), duration, status (ok / partial / failed), per-stage breakdown.

---

## 4. Components I need designed (atoms → organisms)

**Numeric primitives:**
- `<MoneyValue>` — handles USD/HKD/EUR formatting, large + small variants, monospace, signed coloring when delta
- `<PercentValue>` — signed, colored, with arrow glyph
- `<DeltaChip>` — small pill showing change vs. baseline
- `<ConvictionBadge>` — HIGH/MEDIUM/LOW/BROKEN with sized variants and accessible color contrast in both themes
- `<Sparkline>` — 30-day trend glyph, colored by direction

**Layout/structure:**
- `<DataRow>` — the watchlist row pattern; expandable; works at every breakpoint
- `<KPITile>` — labeled value with optional sub-text (used for Current/Downside/Base/Upside, etc.)
- `<TabBar>` — horizontal tabs that scroll-snap on mobile, clean underline on desktop
- `<Section>` — labeled content block with consistent header treatment
- `<CollapsibleSection>` — for memory sections; clean disclosure triangle

**Inputs/actions:**
- `<RunButton>` — has idle / starting / running / done / partial / error states with live counter for fan-out operations
- `<NoteEditor>` — large textarea with monospace font, auto-save indicator, character count
- `<HorizonPicker>` — 3-option segmented control (12 / 24 / 36)
- `<ConvictionFilter>` — toggle chips for HIGH/MEDIUM/LOW/BROKEN
- `<ThemeToggle>` — sun/moon, no animation theatrics

**Status/feedback:**
- `<EmptyState>` — for "no thesis run yet" / "no memory yet" cases. Clear, calm, never apologetic.
- `<LoadFailed>` — distinguishable from empty state; amber border, terse explanation
- `<ProgressIndicator>` — for pipeline runs, fan-out thesis, etc. Inline, not modal.

---

## 5. Data primitives the design must accommodate

So mocks don't ship with toy data, here's what real records look like:

**Watchlist row (12 of these on the landing page):**
```
ticker: "LITE"
name: "Lumentum Holdings"
sector: "Photonics / Optical Components"
price: 949.93
change: +47.61 (+5.28%)
currency: "USD"
score: 7.7
score_delta: +0.3
thesis_target: 1250
conviction: "HIGH"
position_size_pct: 25
upside_pct: +31.6%
filters_passing: 4 / 5
last_run: "3h ago"
```

**Thesis full record (see in detail panel + model detail Thesis tab):**
```
thesis_target: 1250
breakout_price: 1900
risk_adj_target: 1248
conviction: "HIGH"
position_size_pct: 25
buy_below: 800
trim_above: 1500
prompt_version: "v3.2"
run_at: "2026-05-03T09:23:00Z"
coverage_quality: "HIGH"
filters: { demand_inflecting: { pass: true, evidence: "..." }, ... }
top_risks: [ { name, probability, price_impact, early_signal }, ... ]
top_catalysts: [ { name, probability, price_impact, confirming_signal }, ... ]
kill_triggers: [ "Q4 revenue < $1.5B", ... ]
```

**Currency:** the watchlist mixes USD, HKD, EUR. Display the local currency natively (e.g. "HK$67.5"); never silently translate.

**Conviction tiers and approximate distribution** (12 tickers):
- HIGH: 6 tickers (most upside, full position size)
- MEDIUM: 4 tickers (priced-in or partial setup)
- LOW: 1 ticker (near-floor, small position)
- BROKEN: 0 (rare; reserved for "thesis dead, sell")

---

## 6. Visual system constraints

**Typography:** one sans-serif for body/UI, one monospace for all numerics and tickers. Pick a typeface that has both genuine 0/O distinction and tabular figures (e.g. Inter + JetBrains Mono, IBM Plex Sans + IBM Plex Mono, or similar). Tabular numerics are non-negotiable — numbers in a column must align decimal points.

**Color:** dark theme is the default; light theme must be equally first-class (not an afterthought). Both themes need:
- Background, elevated surface, hover surface, border, border-hover (5 surface tones)
- Text, secondary, muted, faint (4 text tones)
- Conviction colors (emerald/yellow/orange/red) that are legible on both surfaces
- Signed-numeric colors (success/danger) that are colorblind-friendly enough (pair with iconography or sign character, never color alone)

**Density:** the watchlist row should fit 6+ data points per row at 1440px and still be readable at 320px. The model detail page should fit a full income statement on a 1280px screen without horizontal scroll.

**Motion:** minimal. Color transitions on hover (150ms ease-out), nothing else. No page transitions, no element entrance animations.

**Accessibility:** WCAG AA minimum. The conviction colors specifically must hit 4.5:1 contrast against their backgrounds. All numeric data must work for screen readers (use `aria-label` with the unit explicit).

---

## 7. Responsive behavior

**Mobile (<640px):** the watchlist is the most-used view on phone. The row must collapse to: ticker, price, score, **thesis target + conviction** (this is non-negotiable — the thesis is the whole point of opening the app). Sector, sparkline, scout ratio can hide. Detail panel becomes a full-screen drawer.

**Tablet (640–1024px):** add sparkline and sector. Detail panel can be a side sheet.

**Desktop (1024–1440px):** add scout ratio, score bar, full row layout.

**Wide (>1440px):** consider showing a sticky right rail with the open detail panel + watchlist still visible on the left.

---

## 8. What I want delivered

In this priority order:

1. **Watchlist row + detail panel** — the most-used view; nail it first
2. **Model detail page header + tab strip + Thesis tab + Floor tab** — the second-most-used view
3. **Theme system** — both modes, polished
4. **The 4 cross-cutting components**: ConvictionBadge, MoneyValue, RunButton, NoteEditor
5. Then everything else (Discovery, Ask AI, Logs, model picker)

Deliverables I'd love to receive:
- A live React + Tailwind artifact that I can interact with at multiple screen sizes
- Both light and dark themes working
- Real-looking mock data populated (use the LITE / AEHR / 6082.HK ticker examples above as reference shapes)
- A short style note explaining the typography pairing, the surface-tone scale, and one or two tradeoffs you made

---

## 9. Constraints on my end

- The current implementation is Next.js 14 (app router) + Tailwind + React 18 + TypeScript
- I read theses from a Supabase `theses` table; data shape is given above
- I have ~12 watchlist tickers in active use right now; the design should look right at N=12 but also work at N=5 and N=30
- The product must work in both `dark` and `light` mode (cookies-driven theme persistence already exists)
- Component CSS variable scheme is already in place (`--bg`, `--text`, `--muted`, `--border`, `--accent`, `--success`, `--danger`, etc.); the redesign can change these values but should keep the variable structure
- I don't need a redesigned logo or mascot
- I don't need illustrations or icons beyond Heroicons / Lucide standard sets

---

## 10. Tone of the work itself

When you reply: be opinionated. If I've asked for something that conflicts with information density (e.g. "make the detail panel feel airy"), push back and explain. If two design choices are in tension (e.g. dark-mode contrast vs. visual calm), name the tradeoff and pick one. The product is for someone who values being argued with by a sharper collaborator.
