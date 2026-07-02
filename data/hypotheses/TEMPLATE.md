# Hypothesis: <one-line claim>

**Ticker(s):** <TICKER>  ·  **Author:** Hume  ·  **Date:** YYYY-MM-DD
**Status:** draft | active | falsified | confirmed
**Horizon:** <years — should match config/thesis_horizons.json for the name>

## Claim
One paragraph. What do you believe that the market does not?

## Mechanism
WHY does the claim produce returns? Input-vs-substitute position, bottleneck,
flywheel, wave/layer — the causal chain, not the conclusion.

## Signatures expected (map to S1–S6)
Which observable facts should appear if the claim is true, and roughly when:
- S1 anomaly-survives-verification: …
- S2 sold-out-before-noticed: …
- S3 smart-money-before-analysts: …
- S4 TAM redefinition: …
- S5 new primitive: …
- S6 hated inflection: …
(Delete rows that don't apply. A hypothesis predicting no observable signature
is not testable — sharpen it.)

## Kill conditions (dated, external signposts — L5 rules)
What dated event, print, or decision would falsify this? "Competition
intensifies" does not count. Examples: "certification decision by 2027-Q2",
"NRR < 110% two consecutive prints", "capacity financing fails to close".

---
*Intake: save as `data/hypotheses/<TICKER>.md`. run_thesis injects it into the
PRIOR CONTEXT block with instructions to falsify, not flatter. The engine is
the falsifier; this file is the formal front door for the hypothesis
generator (lesson L7, docs/design/HORIZON_DISCOVERY_TYPEA_2026-07-02.md).*
