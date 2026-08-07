# The Settled-Basis Ladder — a backtestable strategy

**What it is:** the Portfolio Machine's risk discipline, rendered as a mechanical
strategy for the moomoo/FUTU algo platform (`algo/settled_basis_ladder.py`).

**What it is NOT:** the research. The eight-seat panel's judgment — moat
durability, capital-cycle position, whether HBM is sold out through 2027 —
cannot be backtested, because it isn't mechanical. Do not read a good backtest
here as validation of the theses. Read it as a test of one question:

> Does the *discipline* — settled prints only, valley entries, staged thirds,
> pre-declared exit ladders, a sacred cash floor, starter-size-only on
> parabolic names — beat buy-and-hold on the names we actually track?

That question is falsifiable, and the answer might be no. Which is the point.

---

## The translation table

Every rule below exists in the constitution or the codebase already. Nothing was
invented to make a backtest look good.

| Our law | Where it lives now | Mechanical form |
|---|---|---|
| **Law 2 — settled, never provisional** | `engine/fetch.py`, the INTC $91.63→$92.52 scar | every read uses `select=2` (the last **closed** bar). `select=1` is the still-forming bar — that is the trap, in platform form |
| Two-source cross-check, flag never average | `cross_check()` | entry needs **two independent confirmations**; a conflict means do nothing and log it |
| Trade gate clamps **down only** | `trade_gate.py` | size is capped per stage; nothing in the strategy can raise a cap |
| Anti-parabola +100%/6mo | Charter §V | a name that doubled in six months gets **starter size only**, one stage, forever |
| Valley entries — "drawdowns are the queue, not the hazard" | CONSTITUTION §IV | entry requires a **pullback from the recent high with the trend intact**; it never buys a breakout into strength |
| Euphoria protocol (≥2× cost) | `rules.euphoria_checks` | automatic trim of a preset slice at 2× cost, once per episode |
| Ladders (pre-declared rungs) | `rules.effective_condition` | exit rungs written in advance; each fires once, then the next arms |
| Dated kill signpost | `rules.adjudicate_signposts` | **time stop**: no progress within the horizon → the thesis had its window, exit |
| Structural break = thesis break | `kill_condition_eval.py` | settled close below the long trend → full exit |
| The floor is sacred | Charter §V, `valuation.py` | never deploy beyond `net_asset × (1 − floor_pct)` |
| No invisible opinions | Lesson L4 | every decision prints its reason to the log |

---

## Schedule it correctly (v2 — v1 got this wrong)

Trigger: **run at a specified time, ~15:50 ET**, not on the daily bar.

US market orders are RTH-only per the manual, so a daily-bar trigger fires
after the close and every order would be rejected live while filling happily
in the backtest. Running just before the close puts execution inside RTH and
costs nothing in discipline — the decision still reads `select=2`, the last
CLOSED daily bar. Orders are limit orders (bounded slippage, and they work in
extended sessions too).

## Parameters worth touching first

All are exposed in the platform's parameter panel via `show_variable()`.

| Parameter | Default | What it does |
|---|---|---|
| `floor_amount` | 40000 | FIXED dollars never deployed — Charter §V. Not a percentage: a % floor shrinks exactly when the book is losing |
| `max_position_pct` | 25 | max % of *deployable* capital in one name |
| `stages` | 3 | staged thirds — entries are built, not taken |
| `trend_period` | 200 | the structural regime line |
| `pullback_pct` | 8 | how deep a valley must be before it's an entry |
| `parabola_pct` | 100 | 6-month gain that forces starter size (Charter §V) |
| `rung1/2/3_pct` | 50 / 100 / 200 | pre-declared exit ladder |
| `horizon_days` | 252 | the dated signpost — the window the thesis gets |
| `min_progress_pct` | 10 | what counts as progress at the end of that window |
| `hard_stop_pct` | 30 | the backstop against permanent loss |

---

## Before you paste it into the editor

```bash
# 1 · does every call match the manual's documented signature?
python3 algo/verify_against_manual.py algo/settled_basis_ladder.py <Algo_Manual.md>

# 2 · do the constitutional rules still fire when they should?
python3 algo/dryrun_sim.py
```

The first script exists because v1 shipped with seven editor errors: this
platform's `round()` takes **one** argument (no precision) and `min()`
type-checks its arguments as float — so `min(x, total_cash(...) or 0)` is
rejected for the `or 0`. Verifying that a function NAME exists proves nothing
about how it is called. The checker now reproduces the editor's error list
exactly, including the case where the int comes from a *previous* assignment.

## How to judge the result honestly

A backtest that looks good on one symbol proves nothing. Three tests before you
believe it:

1. **Cross-name.** Run identical parameters across LITE, PLTR, RKLB, ACHR, CELH,
   SNDK, MU. If it only works on one, you fit that one name's history.
2. **The settled-basis cost.** Flip `use_settled` to False (reads `select=1`,
   the forming bar) and re-run. If the edge *depends* on peeking at unsettled
   prices, the edge is not real — it is the lookahead the whole constitution
   exists to prevent.
3. **Versus buy-and-hold.** On a strong trending name, buy-and-hold usually
   wins on raw return. The claim here is not "more return"; it is **less
   permanent-loss risk and no decision made on a rumor**. Compare max drawdown
   and worst-trade, not just CAGR.

If it fails all three, that is a finding worth having — it says the discipline
costs more than it saves, and we should know that before it manages real money.

---

## Known limitations, stated up front

- **Parameter count.** Eleven knobs on a few years of data will overfit if you
  tune them per name. Tune once, globally, or not at all.
- **No fundamentals.** The strategy cannot see an HBM sold-out horizon or a
  qualification slip. It sees price. It is the *guard*, not the *analyst*.
- **Trend-following inheritance.** Regime filters chop badly in sideways
  markets; expect a string of small losses there. The time stop bounds that.
- **The floor is simulated**, not enforced by the broker. In the real book, the
  floor is a separate account — that is the point of it.
