# Archetype proposals for the 6 watchlist names

**Status: AWAITING OWNER CONFIRMATION** · drafted 2026-07-02 (sprint 4.1)

The audit confirmed archetype routing is inert for 5 of 6 names: only LITE is
in `config/ticker_archetype_overrides.json`, every `watchlist.json` archetype
is None, so the D1 kill gate and the [ARCHETYPE_OVERRIDE] prompt leg no-op,
and `kill_condition_eval` judges everything under **GARP guidance** — a memory
cyclical's routine drawdown reads as thesis deterioration.

Vocabulary (`registries.py` / engine routing): `garp` · `cyclical` ·
`transformational` · `compounder` · `special_situation`.

| Ticker | Proposal | One-line rationale |
|--------|----------|--------------------|
| LITE | **transformational** (keep) | Already tagged; optical/AI-interconnect regime shift, Model-D-gated. |
| SNDK | **cyclical** | NAND memory mid-supercycle; the dual-system doc's own canonical cyclical (normalized-EBIT valuation, drawdowns are the expected bear case, kill rules must read the cycle). |
| RKLB | **transformational** | Pre-profit launch + space-systems TAM expansion; right-tail optionality is the thesis, uniform ratio-clamp is the documented false-kill risk. |
| ACHR | **transformational** | Pre-revenue eVTOL; certification-milestone driven. (Defensible alternative: `special_situation` if you view it as pure P(certification)×upside — transformational matches the pre_revenue kill-gate carve-out better.) |
| PLTR | **compounder** | Profitable, sticky gov/AIP platform; the load-bearing question is moat durability and quality of earnings power, not cycle position. (Alternative: `garp` if you want the growth-vs-price frame to dominate — but the multiple makes "reasonable price" the wrong lens.) |
| CELH | **garp** | Profitable consumer-beverage growth story; the question is whether re-accelerating growth is fairly priced (Lynch frame). |

**On your confirmation I will:** add the six entries to
`config/ticker_archetype_overrides.json` with these rationales, then verify
end-to-end that (a) `run_thesis`'s kill gate logs the archetype for each name,
(b) `kill_condition_eval` resolves the non-GARP guidance (acceptance: SNDK
kill evaluation runs under cyclical guidance), and (c) the engine's
`_archetype_params` routing picks up val-year/scenario tilts — now safe
because the Phase-2 discount fix landed (before it, tagging PLTR compounder
would have INFLATED its target ~(1+WACC)^2).

**Flag while deciding:** archetype tags also gate Model D (transformational
only → LITE, RKLB, ACHR would each add one Opus call per thesis run) and
scenario probabilities. If you want Model D on LITE only for now, say so and
I'll keep RKLB/ACHR out of Model D via `should_run_model_d` rather than
mis-tagging them.
