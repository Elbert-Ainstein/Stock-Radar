"""
model_d_generate.py — produce Model D vision scenarios for a ticker.

Model D's math (model_d.py) is pure but needs inputs: a set of TAM-capture paths.
This module generates them. The discipline lives in the PARSER, not the prompt:
`parse_vision_scenarios` REQUIRES a complete scenario set whose probabilities sum
to ~1.0 — which forces a downside/zero case into every vision valuation. That is
the guard against the "manufacture a bullish number" failure mode (a model asked
"how big can this get" will inflate; a model forced to also assign probability to
the failure case cannot quietly omit it).

`parse_vision_scenarios` is PURE and unit-tested. `generate_vision_scenarios`
(the LLM call) and `model_d_for_ticker` (the orchestrator) are guarded and are NOT
wired into the live pipeline — that's a separate, reviewed step.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from model_d import VisionScenario, optionality_value, bracket

MODEL_D_PROMPT = """You are valuing {ticker} with the OPTIONALITY / VISION lens — "how big can this
get, and with what probability." This is the complement to a conservative earnings model, NOT a
license to inflate. Decompose the optimism into explicit, probability-weighted paths.

Produce 3–5 scenarios spanning the full outcome distribution. EXACTLY ONE must be a downside /
"vision fails" case, and the probabilities MUST sum to 1.0. For each scenario give the economics at
a {years}-year horizon:
  - label: short name (e.g. "vision: becomes the standard", "base", "capex digestion")
  - prob: probability this path is the one that plays out (0–1; all sum to 1.0)
  - tam_usd: total addressable market at the horizon, in dollars
  - capture: the company's share of that TAM (0–1)
  - net_margin: terminal net margin (0–1)
  - exit_pe: P/E applied to terminal net earnings
  - rationale: one sentence, anchored to the research below

Be honest: anchor multiples to comparable regime-shift names (do not assume a monopoly multiple
without a sole-source argument), use fully-diluted share economics, and give the downside real
probability mass. Return ONLY JSON:
{{"scenarios": [{{"label": "...", "prob": 0.0, "tam_usd": 0, "capture": 0.0, "net_margin": 0.0, "exit_pe": 0.0, "rationale": "..."}}]}}

RESEARCH CONTEXT:
{context}
"""


def parse_vision_scenarios(data, prob_tolerance: float = 0.05) -> list[VisionScenario]:
    """Parse model output into [VisionScenario]. PURE. Raises ValueError on anything
    malformed, out-of-range, or whose probabilities don't sum to ~1.0."""
    if isinstance(data, dict):
        items = data.get("scenarios") or data.get("vision_scenarios")
    else:
        items = data
    if not isinstance(items, list) or not items:
        raise ValueError("expected a non-empty list of scenarios")

    out: list[VisionScenario] = []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            raise ValueError(f"scenario {i} is not an object")
        try:
            s = VisionScenario(
                label=str(it["label"]),
                prob=float(it["prob"]),
                tam_usd=float(it["tam_usd"]),
                capture=float(it["capture"]),
                net_margin=float(it["net_margin"]),
                exit_pe=float(it["exit_pe"]),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"scenario {i} malformed: {e}")
        if not (0.0 <= s.prob <= 1.0):
            raise ValueError(f"scenario {i} prob {s.prob} out of [0,1]")
        if not (0.0 <= s.capture <= 1.0):
            raise ValueError(f"scenario {i} capture {s.capture} out of [0,1]")
        if s.tam_usd < 0 or s.exit_pe < 0:
            raise ValueError(f"scenario {i} has negative tam_usd / exit_pe")
        out.append(s)

    total = sum(s.prob for s in out)
    if abs(total - 1.0) > prob_tolerance:
        raise ValueError(
            f"probabilities sum to {total:.3f}; must be ~1.0 (include all outcomes, "
            f"including the downside/zero case)"
        )
    return out


def _extract_json(text: str) -> Optional[dict]:
    """Last balanced {...} in the text, parsed. None if none parses."""
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    for end in range(len(text) - 1, -1, -1):
        if text[end] == "}":
            depth = 0
            for start in range(end, -1, -1):
                if text[start] == "}":
                    depth += 1
                elif text[start] == "{":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:end + 1])
                        except json.JSONDecodeError:
                            break
    return None


def generate_vision_scenarios(ticker: str, context: str, *, years: float = 5.0,
                              model: str = "claude-opus-4-8") -> list[VisionScenario]:
    """Guarded LLM call -> parsed, validated scenarios. Raises on failure (the caller
    decides whether Model D is available for this ticker)."""
    import os
    import anthropic
    from utils import create_message

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    client = anthropic.Anthropic(api_key=api_key)
    prompt = MODEL_D_PROMPT.format(ticker=ticker, years=years, context=context)
    resp = create_message(client, model=model, max_tokens=2000, temperature=0.2,
                          messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    data = _extract_json(text)
    if data is None:
        raise ValueError("model returned no parseable JSON")
    return parse_vision_scenarios(data)


def should_run_model_d(archetype: Optional[str]) -> bool:
    """Model D (the vision lens) runs ONLY for regime-shift / transformational names.
    Gating it keeps the extra Opus call off every ticker and off mature names where
    the vision frame doesn't apply."""
    return str(archetype or "").lower() == "transformational"


def model_d_for_ticker(ticker: str, *, context: str, shares: float,
                       engine_target: Optional[float] = None,
                       discount_rate: float = 0.12, years: float = 5.0) -> dict:
    """Orchestrator: generate scenarios -> optionality_value -> bracket vs the engine
    floor. Returns {model_d, bracket}. NOT wired into the live pipeline."""
    scenarios = generate_vision_scenarios(ticker, context, years=years)
    md = optionality_value(scenarios, shares, discount_rate=discount_rate, years=years)
    return {"model_d": md, "bracket": bracket(engine_target, md)}
