Build an interactive stock target price model with the following specifications:

INPUT: Company ticker, current financial data, research context, time horizon (default 2-3 years).

VALUATION FRAMEWORK:
This model feeds into a 5-year DCF engine. Your job is to provide the engine's inputs
(revenue trajectory, margins, multiples, scenarios) grounded in company fundamentals
and forward research. The engine handles the actual computation:

  Enterprise Value = Terminal EBITDA × EV/EBITDA multiple (blended with FCF-SBC leg)
  Present Value = EV / (1 + WACC)^discount_years
  Equity Value = PV(EV) − Net Debt
  Target Price = Equity Value / Diluted Shares

This is a standard enterprise-to-equity bridge. Do NOT use NOPAT × P/E (that mixes
firm-level cash flow with an equity-level multiple). If using P/E for quick sanity
checks, pair it with Net Income (after interest), never with NOPAT.

For pre-profit or high-growth companies where earnings are negative, use P/S
(Price / Revenue) as the primary multiple. The engine handles both modes.

The model should:

1. DERIVE each input independently from current financials and forward research.
   Start from base rates (historical growth, sector margins, peer multiples),
   then adjust incrementally based on company-specific evidence. Never start
   from a target price and work backward — that operationalizes anchoring bias.
   Show the current state of each variable and your estimated forward state,
   with explicit justification for every deviation from the base rate.

2. PERFORM SENSITIVITY ANALYSIS across the key drivers.
   After deriving inputs independently, test how the target changes when
   assumptions shift. Show which variables the target is most sensitive to
   and where the thesis is most vulnerable. This replaces "reverse-engineering"
   — instead of asking "what must be true to hit $X?", ask "what does the data
   say, and how wrong could I be?"

3. GENERATE 8-12 specific, measurable, time-bound criteria that must hold
   for the thesis to remain intact. Each criterion should:
   - Map to exactly ONE of these driver groups: Revenue (R), Margins (M),
     Multiples (P), Capital Structure (S), or External/Macro (E)
   - Have a weight: Critical (2×), Important (1.5×), or Monitoring (1×)
   - Be verifiable from quarterly earnings reports or public data
   - MECE RULE: Criteria within the same driver group describe different
     facets of that driver — they are NOT additive price impacts. If three
     criteria map to Revenue, they collectively inform one revenue trajectory,
     not three independent +X% bumps. The "price_impact_pct" represents
     how much the TOTAL target changes if this criterion's driver group
     deviates from the base case — not a stackable increment.

4. BUILD A SENSITIVITY TABLE: show target price at different combinations
   of two key drivers (e.g., Revenue Growth × EV/EBITDA multiple, or
   Revenue × Operating Margin). Color code: green (above base target),
   neutral, red (below base target).

5. DEFINE THREE SCENARIOS with state-contingent probabilities:
   - Bear: probability should reflect CURRENT conditions, not a fixed range.
     Late-cycle with falling PMI / inverted curve → 30-45%.
     Mid-cycle with stable growth → 20-30%.
     Early-cycle trough with tailwinds → 10-20%.
     For cyclical stocks (semis, commodities, energy), check where in the
     industry cycle the company sits. Every semiconductor upcycle since 1996
     has ended with a 30%+ correction. Bear case must model the cycle turn,
     not just a token haircut.
   - Base: management guidance met, consensus estimates roughly achieved.
     Probability = 1 − (bear + bull).
   - Bull: upside catalysts materialize, above-consensus execution.
     Probability should be lower than base but meaningful (15-30%).
   Compute expected value = probability-weighted average price.
   Probabilities must sum to 1.0. Avoid round numbers like 0.25 or 0.35
   (these are themselves anchoring artifacts — be precise, e.g., 0.22, 0.53).

6. CONSTRUCT A TIME PATH: Show projected price quarterly from today to
   target date. At each quarterly step, compute the warranted multiple
   using the fundamental formula:

     Forward P/E = Payout × (1 + g) / (r − g)
     where g = expected growth, r = cost of equity

   This relationship is CONVEX, not linear: small changes in growth
   expectations at high growth rates cause large multiple swings (e.g.,
   a 300bp growth cut from 10% to 7% reduces warranted P/E by ~23%).
   Multiple compression is front-loaded — the 30%→20% growth phase
   destroys more multiple than 10%→0%. Do not use a linear taper.

   For P/S mode: P/S = Net Margin × P/E (derived from Gordon Growth).
   The same convexity applies.

7. MAP CRITERIA TO CONFIDENCE LEVELS:
   - ≥80% weighted score → Aggressive target supported
   - 60-80% → Base target supported
   - 40-60% → Only conservative target
   - <40% → Thesis broken

8. PROVIDE A QUARTERLY UPDATE MODE where actual results can be input
   and criteria status updated, recomputing confidence and adjusted target.

OUTPUT should include:
- Driver derivation chain (current → estimated, with justification)
- Sensitivity table (two key drivers)
- Criteria checklist with status indicators and driver-group mapping
- Confidence gauge
- Time path line chart with convex multiple trajectory
- Scenario expected value calculation
- Clear decision framework (buy/hold/trim/exit)

REVENUE DATA RULE (CRITICAL):
  Always use TRAILING TWELVE MONTHS (TTM) revenue = sum of last 4 reported
  quarters. This cancels seasonal patterns by construction. TTM is the
  Bloomberg/FactSet/Capital IQ standard.
  If management guides a quarterly run rate AND the business is documented
  non-seasonal (quarterly revenue CV < 5% over 8 quarters), annualizing
  by ×4 is acceptable as a supplement — but TTM remains the anchor.
  For seasonal businesses (retail, tax software, agriculture), Q×4 can
  produce 60%+ errors. Intuit Q3×4 overstates annual revenue by ~66%.
  Never use Q×4 as the sole revenue figure for a seasonal company.

DESIGN: Clean, analytical, not promotional. Show all math.
Distinguish fact (observed data, reported results) from judgment
(growth estimates, multiple selection, probability assignment).
Flag every assumption that deviates >20% from the historical base rate
or sector median with an explicit "[DEVIATION]" tag and justification.
