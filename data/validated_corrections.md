# Validated Corrections — Engine-Verified Facts

**Purpose:** This file contains research-confirmed corrections to common market narratives. It is loaded into EVERY Socratic run (not just for a single ticker), so that engine-verified facts about Company A do not get re-stated incorrectly when analyzing Company B that mentions Company A.

**Treatment in prompts:** Unlike `data/operator_notes/{TICKER}.md` (subjective operator views), entries here are FACTS verified by engine research. Models must treat them as ground truth. If a model contradicts a validated correction, that's a failure mode — surface it in `reasoning_bullets`.

**How to add an entry:** when a Socratic research_round produces a HIGH-confidence factual correction to a widely-cited claim, add it here with the source filing and date. Old corrections stay (they're historical record), unless explicitly invalidated by a later filing.

---

## LITE — Contracted backlog

**Wrong claim widely cited:** "LITE has $42B contracted backlog through 2028."

**Actual fact:** LITE's reported backlog was $420.7M as of FY2024 (Form ARS, June 29, 2024). The 10-K explicitly states backlog "is not necessarily indicative of actual revenue" and carries cancellation risk.

**Verified by:** Socratic research_2 on LITE id=16 (2026-05-25), HIGH confidence. Re-verified in LITE id=21 (2026-05-26).

**Why this matters across tickers:** the $42B figure is likely a misattribution of a hyperscaler's total AI capex commitment. When analyzing LITE competitors (COHR, AAOI) or downstream / upstream names, do NOT cite the $42B figure as a LITE advantage — it is wrong by ~100x and materially mis-frames LITE's contracted-revenue protection.

**What's actually contracted (more recent disclosures):** OCS backlog "well beyond $400M" (Q2 FY2026 8-K). CPO order "multi-hundred-million-dollar, deliverable H1 2027" (Q2 FY2026 8-K). NVIDIA $2B equity investment + multi-billion purchase commitment (March 2, 2026 8-K). All real, all materially smaller than $42B.

---

## COHR — 200G EML for 1.6T transceivers

**Wrong claim widely cited:** "COHR has no current-generation 200G EML product; COHR is only a next-gen 3.2T threat."

**Actual fact:** COHR explicitly disclosed "200G EML solutions for 1.6T transceivers" at OFC 2026 (March 17, 2026 press release / GlobeNewswire). COHR's 200G D-EML general availability was targeted for 2026 per COHR's own OFC 2025 disclosure (March 27, 2025).

**Verified by:** Socratic research_1 on LITE id=16 (2026-05-25), MEDIUM confidence. Re-confirmed in LITE id=21 (2026-05-26).

**Why this matters across tickers:** COHR competes with LITE at CURRENT generation (1.6T), not just next-gen (3.2T). The structural pre-condition for hyperscaler dual-sourcing of EML lasers exists today. When analyzing LITE, this is a moat-erosion vector. When analyzing COHR, this is a competitive positioning fact (current-gen overlap with LITE, not next-gen-only positioning).

**No confirmed Tier-1 design wins yet as of May 2026** — the watch signal is `hyperscaler_dual_sourcing_language`.

---

## NVIDIA partnership exclusivity (LITE + COHR)

**Wrong claim widely cited:** "NVIDIA $2B investment in LITE = sole-source lock-in" OR "NVIDIA $2B investment in COHR = sole-source lock-in."

**Actual fact:** Both NVDA-LITE (March 2, 2026 8-K) and NVDA-COHR (March 2026 disclosures) agreements are explicitly **non-exclusive**. NVDA retains the right to source from either party or others. The $2B represents capacity reservation + R&D co-development, not sole-source commitment.

**Verified by:** Socratic research on LITE id=16 (confirmed in id=19, id=21) and COHR id=23.

**Why this matters:** Bulls on either name treat the NVDA partnership as moat-confirming. It is moat-NEUTRAL on exclusivity, and potentially moat-eroding if NVDA uses its leverage to negotiate ASP concessions (standard behavior for large strategic investors). The partnership signals demand validation, not supplier monopoly.

---

## Format note for future entries

Each correction should include:
- **Wrong claim widely cited** (so models recognize the pattern they should NOT repeat)
- **Actual fact** (the verified version)
- **Verified by** (source: Socratic run + research_N + confidence level + date)
- **Why this matters across tickers** (the cross-ticker implication)
- Optional: what IS true (replacement facts that may be cited)
