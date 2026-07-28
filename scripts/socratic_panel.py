#!/usr/bin/env python3
"""
socratic_panel.py — the judgment panel as DATA.

Before 2026-07-28 the panel was three seats hardcoded in three places
(`{"a": ..., "b": ..., "c": ...}`). Adding a perspective meant editing the
dispatch, the corpus callosum prompt, and the synthesis prompt. Now the roster
is a registry: a panelist is a row here plus a prompt file.

**The structural finding that motivated the expansion.** The original three
were Fundamentals ("assume growth decays toward historical rates unless
overwhelming evidence"), Regime, and Adversarial ("you are trying to break
one"). Two of three seats carried a bearish prior and NO seat was assigned to
construct the strongest honest bull case — in a system whose stated purpose is
finding 10× companies. A panel shaped that way does not find asymmetric
upside; it filters it out. `steelman` exists to close that hole, and it is
held to the same evidence standard as the adversary: it must build the bull
case out of facts or concede it cannot.

**Every panelist declares a failure mode.** A persona without a named bias is
a caricature that argues its corner forever. Each prompt ends by requiring the
analyst to flag when its own bias is likely firing — that self-report is the
signal the corpus callosum uses to weight disagreement.

**Convergence, not a debate club.** All seats serve one goal: find whether a
durable multi-year re-rating exists here, and name what would prove it wrong.
Disagreement that is FALSIFIABLE (different answers to a checkable fact) is
the panel working; disagreement that is TASTE is noise, and the corpus
callosum is instructed to discard it.

Roster overrides live in `config/socratic_panel.json`:
    {"enabled": ["fundamentals", "regime", "adversarial", "supply_chain"]}
Unknown ids are a loud error, not a silent skip.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
ROSTER_CONFIG = HERE.parent / "config" / "socratic_panel.json"


@dataclass(frozen=True)
class Panelist:
    id: str            # stable slug — appears in seals; NEVER renamed in place
    key: str           # short key used in prompt placeholders / result dicts
    prompt: str        # prompt file stem in prompts/socratic/
    name: str          # display name
    school: str        # the philosophy in one line
    watches: str       # what it treats as evidence
    failure_mode: str  # its declared bias — self-reported per run
    lineage: tuple[tuple[str, str], ...] = ()   # (practitioner, the METHOD they contributed)
    lineage_cost: str = ""                      # what that school demonstrably cost its own practitioners
    legacy: bool = False   # part of the original a/b/c trio


# Order matters: it is the order panelists appear in the synthesis block.
PANEL: tuple[Panelist, ...] = (
    Panelist(
        id="fundamentals", key="a", prompt="model_a_fundamentals",
        name="The Fundamentalist",
        school="Reported numbers over narrative; growth decays toward base rates until proven structural.",
        watches="Six-plus quarters of revenue, margins, comps, multiples vs history.",
        failure_mode="Mean-reversion prior — mistakes a genuine regime change for an unsustainable spike.",
        lineage=(
        ("Benjamin Graham", "margin of safety — a price low enough that being wrong is survivable; value the business, not the quote"),
        ("Terry Smith", "quality at a price you do not have to defend; growth you did not pay for is the only free growth"),
    ),
            lineage_cost="Graham's own method systematically missed the great compounders — Buffett later called the cigar-butt approach a mistake he had to unlearn. Cheapness is not the same as value.",
        legacy=True,
    ),
    Panelist(
        id="regime", key="b", prompt="model_b_regime",
        name="The Regime Reader",
        school="Some inflections cannot be priced by history; find the ones where the old framework simply does not apply.",
        watches="Structural breaks, cross-domain analogies, demand-regime shifts, liquidity conditions.",
        failure_mode="Regime-everywhere — sees a structural break in what is only a cycle.",
        lineage=(
        ("George Soros", "reflexivity — price and fundamentals feed each other, so a boom can manufacture the reality that justifies it (and the bust the reverse)"),
        ("Stanley Druckenmiller", "liquidity and positioning move markets before earnings do; find the change nobody has repriced yet"),
        ("Michael Steinhardt", "variant perception — state precisely where your view differs from consensus, or you have no edge"),
    ),
            lineage_cost="Reflexivity is unfalsifiable in careless hands: every move confirms it. Soros's discipline was a stop and a stated thesis; without those the frame explains everything and predicts nothing.",
        legacy=True,
    ),
    Panelist(
        id="adversarial", key="c", prompt="model_c_adversarial",
        name="The Adversary",
        school="Build nothing; break everything. A thesis that survives a real attack is worth holding.",
        watches="Accounting quality, competitive kill shots, financing risk, disconfirming disclosure.",
        failure_mode="Universal skepticism — an argument against everything is an argument against nothing.",
        lineage=(
        ("Jim Chanos", "structural shorts — find the business model that cannot work, not the stock that looks expensive"),
        ("Howard Schilit", "forensic accounting — cash flow versus reported earnings, revenue recognition, the gap between the two statements"),
    ),
            lineage_cost="Chanos was right and early on Enron and wrong and expensive on Tesla for years. Being correct about quality and wrong about survival is still a loss — date your objections.",
        legacy=True,
    ),
    Panelist(
        id="supply_chain", key="d", prompt="model_d_supply_chain",
        name="The Supply-Chain Empiricist",
        school="The truth is upstream. Revenue is the lagging shadow of an order placed two to four quarters ago.",
        watches="Order books, contracted capacity, customer capex guides, qualification status, lead times.",
        failure_mode="Anecdote inflation — treats one supplier data point as the industry.",
        lineage=(
        ("Philip Fisher", "scuttlebutt — go to customers, suppliers and competitors; the business tells you before the income statement does"),
        ("Peter Lynch", "know what you own by looking at what it actually sells and to whom"),
    ),
            lineage_cost="Scuttlebutt scales badly. Fisher's own method rewards the diligent and punishes the impressionable: three conversations feel like an industry and are not.",
    ),
    Panelist(
        id="capital_cycle", key="e", prompt="model_e_capital_cycle",
        name="The Capital-Cycle Analyst",
        school="High returns invite capacity. Supply response kills more theses than demand disappointment ever does.",
        watches="Industry capex vs depreciation, announced capacity, competitor entry, pricing discipline.",
        failure_mode="Permanently early bear — calls every genuine regime shift 'just a cycle'.",
        lineage=(
        ("Marathon Asset Management / Edward Chancellor", "the capital cycle — follow capex and supply response, not demand forecasts; returns mean-revert because capital chases them"),
        ("Howard Marks", "second-level thinking and cycle position — 'where are we' beats 'what happens next'"),
        ("Jeremy Grantham", "profit margins are the most mean-reverting series in finance"),
    ),
            lineage_cost="This school is famously early. Grantham was bearish through long stretches of real returns; being right about the cycle and wrong about its length is indistinguishable from being wrong.",
    ),
    Panelist(
        id="technologist", key="f", prompt="model_f_technologist",
        name="The Technologist",
        school="Physics and engineering decide who wins; spreadsheets only record it afterwards.",
        watches="Roadmap credibility, yields, node/standard transitions, thermal and power limits, qualification physics.",
        failure_mode="Falls for elegant technology that has no business model or no buyer.",
        lineage=(
        ("Andy Grove", "strategic inflection points — the moment a 10x change in one force rewrites who wins, and management's response to it"),
        ("Philip Fisher", "judge the research organization, not the press release: who actually converts R&D into products that sell"),
    ),
            lineage_cost="Clayton Christensen's disruption framework — the most influential technical lens in investing — predicted the iPhone would fail. An elegant theory of technology change will confidently misclassify the biggest case of its era.",
    ),
    Panelist(
        id="base_rates", key="g", prompt="model_g_base_rates",
        name="The Base-Rate Statistician",
        school="This situation belongs to a reference class. What usually happens to companies like this?",
        watches="Outside-view frequencies, how often comparable claims held, historical multiple-compression rates.",
        failure_mode="Reference-class tyranny — a true outlier is exactly what the base rate says is impossible.",
        lineage=(
        ("Michael Mauboussin", "base rates and expectations investing — start from the reference class, then ask what the price already implies"),
        ("Philip Tetlock", "forecast accuracy is measurable; keep score and update"),
        ("Kahneman & Tversky", "the outside view — the specifics you find compelling are exactly what makes forecasts fail"),
    ),
            lineage_cost="Mauboussin's own point cuts both ways: the base rate for extreme outcomes is low BECAUSE extreme outcomes are rare, not because this one is impossible. A reference class applied bluntly rejects every genuine outlier at the moment it is cheapest.",
    ),
    Panelist(
        id="steelman", key="h", prompt="model_h_steelman",
        name="The Owner",
        school="Build the strongest case the FACTS permit — the disciplined bull the panel otherwise lacks.",
        watches="The chain of things that must be true for a multi-year re-rating, and whether each is evidenced.",
        failure_mode="Advocacy drift — arguing past the evidence because the story is good.",
        lineage=(
        ("Warren Buffett", "own the business, not the quote — would you hold it if the market shut for five years?"),
        ("Charlie Munger", "invert, then sit still; a few excellent decisions held for a long time beat activity"),
        ("Nick Sleep", "scale economies shared — find the model that gets structurally stronger as it grows, and give it years"),
    ),
            lineage_cost="Long-horizon conviction is one step from stubbornness: the same temperament that holds through drawdowns holds through broken theses. Sleep's discipline was that he CLOSED the fund rather than drift — the willingness to stop is part of the method.",
    ),
)

BY_ID = {p.id: p for p in PANEL}
BY_KEY = {p.key: p for p in PANEL}
LEGACY_KEYS = tuple(p.key for p in PANEL if p.legacy)


def load_roster(path: Path = ROSTER_CONFIG) -> list[Panelist]:
    """Active panel. Defaults to every seat; `config/socratic_panel.json` may
    narrow it (cost control). Unknown ids raise — a typo must not silently
    shrink the panel behind a seal that claims a full run."""
    if not path.exists():
        return list(PANEL)
    try:
        cfg = json.loads(path.read_text(encoding="utf-8")) or {}
    except json.JSONDecodeError as e:
        print(f"  [panel] WARN: {path} unreadable ({e}) — running the FULL panel",
              file=sys.stderr, flush=True)
        return list(PANEL)
    enabled = cfg.get("enabled")
    if not enabled:
        return list(PANEL)
    if not isinstance(enabled, list):
        raise ValueError(f"{path}: 'enabled' must be a list of panelist ids")
    unknown = [e for e in enabled if e not in BY_ID]
    if unknown:
        raise ValueError(
            f"{path}: unknown panelist id(s) {unknown}. "
            f"Known ids: {sorted(BY_ID)}")
    # Preserve PANEL order regardless of the order written in config.
    active = [p for p in PANEL if p.id in set(enabled)]
    if not active:
        raise ValueError(f"{path}: 'enabled' selected no panelists")
    return active


def panel_version(active: Optional[list[Panelist]] = None) -> str:
    """Stable identity of the seated panel — recorded on every seal so the
    grader can separate calibration cohorts across roster changes (a panel
    change alters judgment output; comparing across it silently would poison
    the hit-rate)."""
    active = load_roster() if active is None else active
    return "panel-" + "+".join(p.id for p in active)


def format_lineage(panelist: Panelist) -> str:
    """The [LINEAGE] block: where this seat's METHOD comes from, and what that
    method demonstrably cost the people who invented it.

    METHOD, NOT MIMICRY — this is the whole design rule. The block never says
    "you are X" and the prompts never ask "what would X do." Asking a model to
    impersonate a famous investor produces pastiche: remembered quotes,
    borrowed authority, and a house style standing in for analysis. What
    transfers is the TECHNIQUE — scuttlebutt, the capital cycle, forensic cash
    flow, the outside view — which is checkable against evidence in a way a
    persona never is.

    Each lineage carries its own price tag for the same reason each seat
    declares a failure mode: a method presented without its documented
    failures becomes authority, and authority is exactly what this panel is
    built to do without.
    """
    if not panelist.lineage:
        return ""
    lines = ["### Where your method comes from", ""]
    for who, method in panelist.lineage:
        lines.append(f"- **{who}** — {method}")
    if panelist.lineage_cost:
        lines += ["", f"**What this school has cost its own practitioners:** "
                      f"{panelist.lineage_cost}"]
    lines += [
        "",
        "Use the METHOD. Do not impersonate the practitioner, do not quote "
        "them, and never cite a name as evidence — \"Graham would say this is "
        "cheap\" is not an argument, it is borrowed authority. If your "
        "reasoning would survive with every name above deleted, it is real "
        "analysis; if it would collapse, you were doing costume work. The "
        "cost line is there so you know where your own lens goes blind.",
    ]
    return "\n".join(lines)


def format_panel_roster(active: Optional[list[Panelist]] = None) -> str:
    """The [PANEL_ROSTER] block: who else is in the room. Panelists argue
    better when they know which lens is covering which ground — and it stops
    every seat from re-deriving the same revenue table."""
    active = load_roster() if active is None else active
    lines = ["The panel seated for this run — you are one of these. Do NOT "
             "duplicate another seat's work; cover YOUR ground and let the "
             "synthesis reconcile you:", ""]
    for p in active:
        lines.append(f"- **{p.name}** ({p.id}) — {p.school}")
    lines.append("")
    lines.append("You disagree with these colleagues by producing a DIFFERENT "
                 "ANSWER TO A CHECKABLE FACT, never by disliking their taste. "
                 "Falsifiable disagreement is the point of the panel; "
                 "aesthetic disagreement is discarded downstream.")
    return "\n".join(lines)


def format_panel_json_block(round_1: dict[str, dict],
                            active: Optional[list[Panelist]] = None) -> str:
    """The [PANEL_JSON] block for the corpus callosum and synthesis prompts:
    every seated panelist's verdict, labeled with its school and declared
    failure mode so the synthesizer can weight a verdict against its own bias."""
    active = load_roster() if active is None else active
    parts: list[str] = []
    for p in active:
        entry = round_1.get(p.key)
        if not entry:
            continue
        parsed = entry.get("parsed")
        parts.append(
            f"#### {p.name} — id `{p.id}`\n"
            f"- school: {p.school}\n"
            f"- declared failure mode: {p.failure_mode}\n\n"
            "```json\n"
            + json.dumps(parsed, ensure_ascii=False, indent=2)
            + "\n```"
        )
    return "\n\n".join(parts) if parts else "(no panelist output)"


if __name__ == "__main__":
    active = load_roster()
    print(panel_version(active))
    print()
    print(format_panel_roster(active))
