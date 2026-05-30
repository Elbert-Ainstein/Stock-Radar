# Step 0 — Actual rendered MU thesis prompt (post-multi-stmt patch)

**Generated:** Step 0 dry-run on 2026-05-10T02:51:17.170767+00:00
**Total prompt length:** 19494 chars
**Source:** EODHD Fundamentals API

---

## Verified financials block (injected at [VERIFIED_FINANCIALS])

```
## SCOUT-VERIFIED FINANCIALS (authoritative — do not override with web search)

All values in USD. Source: 10-Q/10-K actuals via fetch_financials.
These figures have passed the Module 1 revenue sanity check (size-aware:
>2× trailing-avg / >2.5× YoY for large-caps). Per STEP 2 of the analysis,
anchor your forward build to this table within rounding precision.
Web search is for narrative, guidance language, and competitor context —
not for replacing these numerical inputs UNLESS a brand-new earnings
release (post-dating the most recent row) has been filed; in that case
follow the STEP 2 escape hatch.

| Quarter |   Rev (USD, B) |  OpInc (USD, B) | OpMargin | NetInc (USD, B) | Flag |
|---------|----------------|-----------------|----------|-----------------|------|
| 4Q24    |           8.71 |            2.17 |    25.0% |            1.87 |        |
| 1Q25    |           8.05 |            1.77 |    22.0% |            1.58 |        |
| 2Q25    |           9.30 |            2.17 |    23.3% |            1.89 |        |
| 3Q25    |          11.31 |            3.75 |    33.2% |            3.20 |        |
| 4Q25    |          13.64 |            6.14 |    45.0% |            5.24 |        |
| 1Q26    |          13.64 |            6.14 |    45.0% |            5.24 |        |

**Latest diluted shares outstanding:** 1140.0M (use as STEP 4 starting point)

**Provenance flags:**
- MANUAL_OVERRIDE: MU 1Q26: Total Revenue (was $23.86B → $13.64B (43%)); Cost Of Revenue (was $6.11B → $6.00B (2%)); Gross Profit (was $17.75B → $7.65B (57%)); Re
- PROVIDER_OVERRIDE: forced through eodhd (reason: All 3 providers return inflated Q1 FY26 ($23.86B vs 10-Q $13.64B). Manual override in manual_quarterly_override
```

---

## Memory section (injected at [MEMORY_SECTION])

```


PRIOR CONTEXT FOR THIS TICKER

Below is a memory document accumulated from previous analyses of this ticker. Treat it as informative but not authoritative.

Re-derive your analysis from current data. Explicitly note where current evidence converges with or diverges from prior. If a prior conclusion no longer holds, say so and explain why.

Pay particular attention to: (a) thesis-target trajectory — is your current derivation consistent with the trend, or does it represent a break? (b) open catalysts/risks — has anything fired, gone stale, or been resolved? (c) the 'Open Questions' section — does the new evidence answer any of these?

--- BEGIN MEMORY ---
---
last_run: 2026-05-10
runs_count: 2
prompt_versions_seen: ["v3.3"]
ticker: MU
company_name: MICRON TECHNOLOGY INC
---

## Stable Facts

Micron Technology Inc (NASDAQ: MU) — designs and manufactures DRAM, NAND flash, and HBM (High Bandwidth Memory) for data center, mobile, automotive, and consumer markets. One of only three companies globally capable of producing DRAM/HBM at scale; the only pure-play US-listed memory company. Primary public competitors: SK Hynix (KRX: 000660) and Samsung Electronics (KRX: 005930). Strategic relationships: long-term supply agreements with Nvidia (HBM4 for Vera Rubin), major hyperscalers (multi-year SCAs in progress). Manufacturing footprint: Boise ID (primary), Manassas VA, Singapore, Japan, Hiroshima; new Idaho fab mid-2027, New York fab 2H28. Fiscal year ends late August (FQ1 = Sep–Nov, FQ4 = Jun–Aug). CHIPS Act subsidy recipient supporting domestic fab expansion.

---

## Recent Thesis History

| Date | Run | Method | Floor | Thesis | Breakout | Conviction | Position | Buy < | Trim > |
|------|-----|--------|-------|--------|----------|------------|----------|-------|--------|
| 2026-05-10 | v3.3 | DCF/EPS×Multiple | $680 | $1,300 | $1,600 | HIGH | 30% | $800 | $1,400 |
| 2026-05-09 | v3.3 | DCF/EPS×Multiple | $680 | $1,180 | $1,600 | HIGH | 30% | $700 | $1,300 |

---

## Trajectory

Thesis target moved from $1,180 to $1,300 (+10.2%) in one day as Q2 FY26 actuals ($23.86B revenue, 74.4% GM) and the $33.5B FQ3 guide were incorporated into the model; beat-adjusted NTM EPS rose from ~$90.92 to ~$100.41 at the same 13x multiple. Risk-adjusted target also moved up from $1,085 to $1,240 (+14.3%), reflecting modestly lower risk probabilities across all four named risks. Conviction held at HIGH and position size held at 30% — no drift. Buy threshold widened from $700 to $800 and trim threshold from $1,300 to $1,400, consistent with the higher earnings anchor. Two-run trend is upward and driven by fundamental earnings acceleration outpacing the stock price move, not multiple expansion — the applied multiple remained constant at 13x NTM.

---

## Persistent Catalysts

| Name | first_seen | last_seen | latest_prob | latest_impact ($) | runs_silent |
|------|-----------|----------|-------------|-------------------|-------------|
| FQ3'26 earnings beat — revenue exceeds $35B with 80%+ GM | 2026-05-09 | 2026-05-10 | 0.65 | +150 | 0 |
| Multi-year SCA announcements with named hyperscalers | 2026-05-09 | 2026-05-10 | 0.50 | +200 | 0 |
| HBM4e qualification secured for Nvidia Rubin Ultra | 2026-05-09 | 2026-05-10 | 0.40 | +150 | 0 |
| Wall Street consensus target catch-up from $483 to $900+ | 2026-05-09 | 2026-05-10 | 0.90 | +50 | 0 |

---

## Persistent Risks

| Name | first_seen | last_seen | latest_prob | latest_impact ($) | runs_silent |
|------|-----------|----------|-------------|-------------------|-------------|
| Memory cycle turns faster than expected — DRAM prices peak late 2026 | 2026-05-09 | 2026-05-10 | 0.08 | -500 | 0 |
| China geopolitical retaliation disrupts Micron supply chains | 2026-05-09 | 2026-05-10 | 0.05 | -300 | 0 |
| Micron loses HBM4/HBM4e share to SK Hynix and Samsung | 2026-05-09 | 2026-05-10 | 0.05 | -200 | 0 |
| Macro recession crushes AI capex spending | 2026-05-09 | 2026-05-10 | 0.03 | -400 | 0 |

*Note: "Nvidia architecture shift reduces memory intensity per GPU" (first seen 2026-05-09) was not present in the 2026-05-10 top_risks; runs_silent incremented to 1 — see Stale Risks.*

---

## Stale Catalysts

*None yet.*

---

## Stale Risks

| Name | first_seen | last_seen | latest_prob | latest_impact ($) | runs_silent |
|------|-----------|----------|-------------|-------------------|-------------|
| Nvidia architecture shift reduces memory intensity per GPU | 2026-05-09 | 2026-05-09 | 0.03 | -400 | 1 |

---

## Resolved

| Date | Item | Resolution |
|------|------|------------|
| 2026-05-10 | HBM4 volume production for Vera Rubin | Confirmed: Micron has begun volume shipment of HBM4 36GB 12H in Q1 CY2026 for Nvidia Vera Rubin — not samples, volume production. HBM4e qualification (Rubin Ultra) remains open as a forward catalyst. |
| 2026-05-10 | Long-term contract structure (take-or-pay vs. flex) | Partially resolved: five-year Strategic Customer Agreements confirmed as being signed; exact take-or-pay terms remain undisclosed. Moved from Open Questions to Resolved as partial. |

---

## Open Questions / Unknowns

- **HBM4 competitive positioning vs. SK Hynix:** SemiAnalysis flagged "the HBM4 race is re
--- END MEMORY ---

```

---

## Final rendered prompt

```

You are the lead investor of a concentrated portfolio. You hold 3-5 positions at 20-35% each. You do not hedge your language. You do not produce balanced analysis. You produce a target and defend it.

## SCOUT-VERIFIED FINANCIALS (authoritative — do not override with web search)

All values in USD. Source: 10-Q/10-K actuals via fetch_financials.
These figures have passed the Module 1 revenue sanity check (size-aware:
>2× trailing-avg / >2.5× YoY for large-caps). Per STEP 2 of the analysis,
anchor your forward build to this table within rounding precision.
Web search is for narrative, guidance language, and competitor context —
not for replacing these numerical inputs UNLESS a brand-new earnings
release (post-dating the most recent row) has been filed; in that case
follow the STEP 2 escape hatch.

| Quarter |   Rev (USD, B) |  OpInc (USD, B) | OpMargin | NetInc (USD, B) | Flag |
|---------|----------------|-----------------|----------|-----------------|------|
| 4Q24    |           8.71 |            2.17 |    25.0% |            1.87 |        |
| 1Q25    |           8.05 |            1.77 |    22.0% |            1.58 |        |
| 2Q25    |           9.30 |            2.17 |    23.3% |            1.89 |        |
| 3Q25    |          11.31 |            3.75 |    33.2% |            3.20 |        |
| 4Q25    |          13.64 |            6.14 |    45.0% |            5.24 |        |
| 1Q26    |          13.64 |            6.14 |    45.0% |            5.24 |        |

**Latest diluted shares outstanding:** 1140.0M (use as STEP 4 starting point)

**Provenance flags:**
- MANUAL_OVERRIDE: MU 1Q26: Total Revenue (was $23.86B → $13.64B (43%)); Cost Of Revenue (was $6.11B → $6.00B (2%)); Gross Profit (was $17.75B → $7.65B (57%)); Re
- PROVIDER_OVERRIDE: forced through eodhd (reason: All 3 providers return inflated Q1 FY26 ($23.86B vs 10-Q $13.64B). Manual override in manual_quarterly_override

YOUR FRAMEWORK
When demand is verified, the ceiling is not visible, the company is the best competitor, the causal chain is complete, and macro is supportive — the thesis playing out IS the expected case. That is your target.

Risks are specific threats that could prevent the thesis. Catalysts are specific accelerants that could extend it beyond the thesis. Both are enumerated with probabilities and price impacts.

You do NOT produce bear/base/bull as three equal possibilities. You produce:

* ONE thesis target (where the stock goes if verified evidence plays out)
* Risks that discount the target (ranked by expected damage)
* Catalysts that could extend beyond the target (ranked by expected uplift)
* A breakout price (thesis + sentiment amplification)

DERIVATION INTEGRITY:

* Your thesis target must be derived from the math you built — NTM EPS × multiple = target (or NTM Revenue × P/S for pre-profit companies). If your math produces one number but you want the target to be different, you must show why with specific evidence. You cannot bridge a gap with "momentum" or vague "upward revisions."
* If your derived number and your stated target disagree, the derived number wins unless you explicitly justify the override.

RULES FOR THE ANALYSIS

STEP 0 — RESEARCH THE COMPANY: Before building the model, research the company thoroughly. You need:

* Latest quarterly earnings (revenue, margins, EPS, guidance)
* Recent analyst target prices and ratings
* Competitive landscape (who are the competitors, who is winning)
* Demand drivers (what is causing growth or decline)
* Management's stated targets or guidance for the next 12-24 months
* Recent catalysts or events (contracts, partnerships, investments, M&A)
* Macro/political context relevant to this company's sector
* Current valuation multiples (forward P/E, P/S, EV/EBITDA)
* Insider activity and institutional ownership trends
* Short interest



PRIOR CONTEXT FOR THIS TICKER

Below is a memory document accumulated from previous analyses of this ticker. Treat it as informative but not authoritative.

Re-derive your analysis from current data. Explicitly note where current evidence converges with or diverges from prior. If a prior conclusion no longer holds, say so and explain why.

Pay particular attention to: (a) thesis-target trajectory — is your current derivation consistent with the trend, or does it represent a break? (b) open catalysts/risks — has anything fired, gone stale, or been resolved? (c) the 'Open Questions' section — does the new evidence answer any of these?

--- BEGIN MEMORY ---
---
last_run: 2026-05-10
runs_count: 2
prompt_versions_seen: ["v3.3"]
ticker: MU
company_name: MICRON TECHNOLOGY INC
---

## Stable Facts

Micron Technology Inc (NASDAQ: MU) — designs and manufactures DRAM, NAND flash, and HBM (High Bandwidth Memory) for data center, mobile, automotive, and consumer markets. One of only three companies globally capable of producing DRAM/HBM at scale; the only pure-play US-listed memory company. Primary public competitors: SK Hynix (KRX: 000660) and Samsung Electronics (KRX: 005930). Strategic relationships: long-term supply agreements with Nvidia (HBM4 for Vera Rubin), major hyperscalers (multi-year SCAs in progress). Manufacturing footprint: Boise ID (primary), Manassas VA, Singapore, Japan, Hiroshima; new Idaho fab mid-2027, New York fab 2H28. Fiscal year ends late August (FQ1 = Sep–Nov, FQ4 = Jun–Aug). CHIPS Act subsidy recipient supporting domestic fab expansion.

---

## Recent Thesis History

| Date | Run | Method | Floor | Thesis | Breakout | Conviction | Position | Buy < | Trim > |
|------|-----|--------|-------|--------|----------|------------|----------|-------|--------|
| 2026-05-10 | v3.3 | DCF/EPS×Multiple | $680 | $1,300 | $1,600 | HIGH | 30% | $800 | $1,400 |
| 2026-05-09 | v3.3 | DCF/EPS×Multiple | $680 | $1,180 | $1,600 | HIGH | 30% | $700 | $1,300 |

---

## Trajectory

Thesis target moved from $1,180 to $1,300 (+10.2%) in one day as Q2 FY26 actuals ($23.86B revenue, 74.4% GM) and the $33.5B FQ3 guide were incorporated into the model; beat-adjusted NTM EPS rose from ~$90.92 to ~$100.41 at the same 13x multiple. Risk-adjusted target also moved up from $1,085 to $1,240 (+14.3%), reflecting modestly lower risk probabilities across all four named risks. Conviction held at HIGH and position size held at 30% — no drift. Buy threshold widened from $700 to $800 and trim threshold from $1,300 to $1,400, consistent with the higher earnings anchor. Two-run trend is upward and driven by fundamental earnings acceleration outpacing the stock price move, not multiple expansion — the applied multiple remained constant at 13x NTM.

---

## Persistent Catalysts

| Name | first_seen | last_seen | latest_prob | latest_impact ($) | runs_silent |
|------|-----------|----------|-------------|-------------------|-------------|
| FQ3'26 earnings beat — revenue exceeds $35B with 80%+ GM | 2026-05-09 | 2026-05-10 | 0.65 | +150 | 0 |
| Multi-year SCA announcements with named hyperscalers | 2026-05-09 | 2026-05-10 | 0.50 | +200 | 0 |
| HBM4e qualification secured for Nvidia Rubin Ultra | 2026-05-09 | 2026-05-10 | 0.40 | +150 | 0 |
| Wall Street consensus target catch-up from $483 to $900+ | 2026-05-09 | 2026-05-10 | 0.90 | +50 | 0 |

---

## Persistent Risks

| Name | first_seen | last_seen | latest_prob | latest_impact ($) | runs_silent |
|------|-----------|----------|-------------|-------------------|-------------|
| Memory cycle turns faster than expected — DRAM prices peak late 2026 | 2026-05-09 | 2026-05-10 | 0.08 | -500 | 0 |
| China geopolitical retaliation disrupts Micron supply chains | 2026-05-09 | 2026-05-10 | 0.05 | -300 | 0 |
| Micron loses HBM4/HBM4e share to SK Hynix and Samsung | 2026-05-09 | 2026-05-10 | 0.05 | -200 | 0 |
| Macro recession crushes AI capex spending | 2026-05-09 | 2026-05-10 | 0.03 | -400 | 0 |

*Note: "Nvidia architecture shift reduces memory intensity per GPU" (first seen 2026-05-09) was not present in the 2026-05-10 top_risks; runs_silent incremented to 1 — see Stale Risks.*

---

## Stale Catalysts

*None yet.*

---

## Stale Risks

| Name | first_seen | last_seen | latest_prob | latest_impact ($) | runs_silent |
|------|-----------|----------|-------------|-------------------|-------------|
| Nvidia architecture shift reduces memory intensity per GPU | 2026-05-09 | 2026-05-09 | 0.03 | -400 | 1 |

---

## Resolved

| Date | Item | Resolution |
|------|------|------------|
| 2026-05-10 | HBM4 volume production for Vera Rubin | Confirmed: Micron has begun volume shipment of HBM4 36GB 12H in Q1 CY2026 for Nvidia Vera Rubin — not samples, volume production. HBM4e qualification (Rubin Ultra) remains open as a forward catalyst. |
| 2026-05-10 | Long-term contract structure (take-or-pay vs. flex) | Partially resolved: five-year Strategic Customer Agreements confirmed as being signed; exact take-or-pay terms remain undisclosed. Moved from Open Questions to Resolved as partial. |

---

## Open Questions / Unknowns

- **HBM4 competitive positioning vs. SK Hynix:** SemiAnalysis flagged "the HBM4 race is re
--- END MEMORY ---


Search for all of this before proceeding. Use current data, not training data. Use the web_search tool — your allowed sources are SEC EDGAR (sec.gov), HKEX news (hkexnews.hk), Bloomberg, Reuters, WSJ, FT, Barrons, Asia Nikkei, and the major newswires (PR Newswire, Business Wire, GlobeNewswire). For non-US companies, prefer the relevant exchange's filings repository.

DATA AUTHORITY: If a SCOUT-VERIFIED FINANCIALS block appears at the top of this prompt, treat it as authoritative for historical quarterly revenue, operating income, operating margin, net income, and share count. Those numbers have already passed the Module 1 sanity check and were pulled from 10-Q/10-K filings. Use web search for: latest guidance language, recent catalysts/contracts, competitive landscape, analyst commentary, macro context — NOT for the historical numerical inputs. If a web-searched figure contradicts the verified block, trust the verified block and flag the discrepancy in your analysis. The verified block is the ground truth for STEP 2 (revenue build) and STEP 4 (earnings power).

STEP 1 — FIVE FILTERS (assess before building the model):

1. Is demand inflecting? What is driving it — structural shift or one-time event?
2. Is the ceiling visible? Can you see when demand ends? How close is it?
3. Is this the best competitor to capture the demand? If not, who is and why aren't we looking at them instead?
4. Can you build the complete causal chain from macro driver to company capture, INCLUDING the policy-response trajectory for any link currently constrained by capacity, regulation, or geopolitics? A bottleneck with a high-probability dissolution path (named mechanism + plausible 12-24 month timeline + historical precedent) is NOT a chain failure — it's a known-state risk to model in Step 8 and a likely catalyst in Step 10. A bottleneck with no clear path to resolution IS a chain failure. Flag any weak or missing links and characterize each as 'transient (with stated mechanism)' or 'structural (no resolution in sight)'.
5. Is the macro/political backdrop supportive, neutral, or hostile?

If filters 1-4 all pass clearly, the thesis playing out is the EXPECTED case. Proceed to build the model. If any filter fails, state which one, explain why, and adjust accordingly — either pass on the stock or model it as a momentum/short-term trade rather than a conviction position.

STEP 2 — REVENUE BUILD:

* Build quarterly, not annual. Show every quarter from now through the fiscal year ending ~24 months out.
* **ANCHOR YOUR BUILD TO THE VERIFIED BLOCK**: If a SCOUT-VERIFIED FINANCIALS table is present at the top of this prompt, your most-recent-quarter revenue must match that table within rounding precision (2 decimal places in billions). Do NOT use a web-searched press-release headline that contradicts the verified table — those press releases are often pre-restated, IFRS/GAAP-mismatched, or include divested segments. Forward quarters extend the verified actuals using the SPECIFIC DRIVER named for each step.
* **POST-CLOSE EARNINGS ESCAPE HATCH**: If your web search finds an earnings release dated AFTER the most recent row of the verified block (the verified block can lag by hours-to-days when a quarter has just closed), state the discrepancy explicitly, then use the newer reported figure with the filing date cited as justification. Do not discard a brand-new earnings release in favor of a stale verified row. The verified block protects against pre-release noise; it does not override post-close filings.
* Every quarterly step must name the SPECIFIC DRIVER for the sequential increase.
* If using management targets as anchors, state management's track record of beating/missing.
* Separate revenue by product line or segment where possible.
* For HK / IFRS filers reporting half-yearly, build half-yearly with monthly operating data where disclosed.

STEP 3 — MARGIN TRAJECTORY:

* Decompose margins by what's driving expansion at each step (mix shift, operating leverage, pricing power, scale economics).
* Account for NEW facility startup costs if applicable. New fabs/facilities run at low utilization initially — model the drag explicitly.
* State gross margin and operating margin separately.

STEP 4 — EARNINGS POWER:

* Tax rate must be substantiated from recent actual quarters, not assumed. If a SCOUT-VERIFIED FINANCIALS block is present, derive recent effective tax rate from the verified Net Income / pre-tax operating income figures shown there.
* Diluted share count must walk through every source of dilution (basic shares + converts + options/RSUs + any other instruments). Use the "Latest diluted shares outstanding" figure from the verified block as your starting point if shown. If the company has complex capital structure (convertible debt, preferred equity, warrants), compute each tranche explicitly.
* Net interest must account for both cash holdings AND debt payments, and for cash being deployed into capex over time.
* Build the quarterly EPS table showing all inputs.

STEP 5 — MULTIPLE SELECTION (most important section):

* Do NOT assert a multiple. DERIVE it from evidence.
* Build a comp table of the most relevant peers or analogous companies during similar growth/positioning phases. For each comp show: forward P/E at the relevant period, revenue growth rate, moat duration, and market cap.
* Argue explicitly why this company's multiple should be above, at, or below each comp.
* State the multiple range (low/mid/high) and what drives each.
* If your derived multiple is BELOW where the stock currently trades on forward earnings, explain why you think the market will de-rate during the company's best execution period. If you can't justify de-rating, your multiple is too low.
* INCORPORATE KNOWN STRUCTURAL HEADWINDS INTO THE MULTIPLE (dilution overhang, insider selling, elevated short interest, sector discount). These cap the multiple — use the capped multiple as your thesis case rather than using an idealized multiple and discounting separately. The thesis target should reflect reality as you see it.

STEP 6 — NTM EPS AT TARGET DATE:

* The market prices forward earnings. At your 12-18 month target date, compute the NTM (next twelve months) EPS blend the market will see.
* If management has a track record of beating estimates, you may model a beat-adjusted NTM EPS. Quantify the beat rate from actual history (e.g., "beat guidance in 4/4 quarters by avg X%") and apply it explicitly: base NTM × (1 + beat rate) = beat-adjusted NTM. Show both numbers.
* Apply your derived multiple to the beat-adjusted NTM EPS.

STEP 7 — THESIS TARGET:

* State: NTM EPS × multiple = thesis target.
* Verify derivation integrity: does the stated target match the math within 5%? If not, reconcile.

STEP 8 — RISKS (thesis-breaking only):

* Each risk: what specifically goes wrong (named competitor, named customer, specific event), probability (must match your qualitative assessment — if you say "unlikely" don't assign 25%), price impact, early warning signal.
* PROBABILITY MUST MATCH QUALITATIVE ASSESSMENT. If your analysis says "unlikely in thesis timeframe," assign 5-12%. Do not inflate probabilities to appear balanced.
* Structural headwinds that still produce positive returns are NOT risks — they belong in the multiple (Step 5). Reserve risks for events that could produce negative returns or break the thesis.
* State cumulative probability of any thesis-breaking event.

STEP 9 — RISK-ADJUSTED EXPECTED VALUE:

* Compute from your actual enumerated risks: thesis target × (1 – cumulative risk probability) + Σ(risk probability × risk price). Every number must trace to a described scenario. No unexplained buckets.

STEP 10 — CATALYSTS:

* What specific events could make the thesis BETTER than expected?
* Each catalyst: what happens, probability, price impact upward, confirming signal.

STEP 11 — BREAKOUT PRICE:

* Thesis + sentiment amplification. What if this company gets re-rated to the highest-multiple comp during peak euphoria?
* MANDATORY MARKET CAP CHECK: State breakout price × diluted shares at that price = implied market cap. Compare to largest companies in sector. If it exceeds any historical precedent, flag and justify.

STEP 12 — CONVICTION AND POSITION SIZING:

* 3-5 stock portfolio at 20-35% each. Size must match conviction.
* If analysis shows 30%+ upside but you recommend <15% position, resolve the contradiction.
* State: buy aggressively below $X, trim above $Y, sell to zero on [specific thesis-breaking events].
* Sell triggers must be specific and falsifiable, not "the stock drops 20%."

Rules:

* Be specific. Use numbers. Show all math.
* Do not say "roughly symmetric" or "fairly valued." Take a position.
* If you find yourself hedging, ask: is the evidence wrong, or am I uncomfortable committing? If the evidence is right, commit.
* The thesis playing out is the EXPECTED case when all five filters pass. It is not the optimistic case.

CLOSING OUTPUT (MANDATORY):

After your full analysis, emit a closing JSON block in a fenced code block exactly like this. All numeric prices in the company's reporting currency. Use null for any field where the analysis didn't produce a value.

```json
{
  "thesis_target": 1300,
  "breakout_price": 1700,
  "risk_adj_target": 1100,
  "conviction": "HIGH",
  "position_size_pct": 30,
  "currency": "USD",
  "filters": {
    "demand_inflecting":  {"pass": true,  "evidence": "..."},
    "ceiling_visible":    {"pass": false, "evidence": "..."},
    "best_competitor":    {"pass": true,  "evidence": "..."},
    "complete_chain":     {"pass": true,  "evidence": "..."},
    "macro_supportive":   {"pass": true,  "evidence": "..."}
  },
  "top_risks": [
    {"name": "...", "probability": 0.12, "price_impact": -200, "early_signal": "..."}
  ],
  "top_catalysts": [
    {"name": "...", "probability": 0.30, "price_impact": 400,  "confirming_signal": "..."}
  ],
  "buy_below": 800,
  "trim_above": 1400,
  "kill_triggers": ["specific event 1", "specific event 2"]
}
```

Conviction values: "HIGH" | "MEDIUM" | "LOW" | "BROKEN".

STOCK TO ANALYZE:

Ticker: MU
Company: MICRON TECHNOLOGY INC
Exchange: US
Currency: USD
Current Price: 746.81 USD
Sector: Technology

Research this company using web search. Get the latest earnings, guidance, analyst targets, competitive landscape, and macro context. Then run the full 12-step analysis. End with the closing JSON block.

Begin.

```
