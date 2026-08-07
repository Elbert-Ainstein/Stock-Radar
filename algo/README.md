# algo/ — The Settled-Basis Ladder

**Paste `settled_basis_ladder.py` whole into the strategy editor.** It is
documentation comments plus the strategy class, and nothing else — the editor
allows no top-level code at all.

**Trigger — backtest and live want different settings:**

* **Long backtest (years): the DAILY candle.** Never an intraday trigger.
  `handle_data` only runs when a trigger fires, and intraday candle history is
  kept for a far shorter window than daily history. A 1h trigger silently
  clamps a 2019-start run to roughly the last year — and the giveaway is that
  changing the start date does not change the result at all.
* **Live: run at a specified time, ~15:50 ET.** US *market* orders are
  RTH-only; this strategy places *limit* orders, which are accepted outside
  RTH, so a daily trigger is safe either way — an intraday run just gets
  same-session fills.

Either way the discipline is identical: decisions read `select=2`, the last
closed daily bar.

Everything else — the translation from the constitution's laws, every
parameter, the three acceptance tests, the known limitations — lives in the
file's header, so there is one place to keep current.

## Symbols — one trigger, multi-select

The strategy declares **one** trigger symbol. In the backtest dialog, click the
`+` on `Trigger_Symbol1` and tick every ticker you want — the whole basket
rides one trigger.

Declaring one slot per name is the trap: you get N single-symbol boxes and the
dialog will not enable **Next** while any of them is empty.

`handle_data` then fires once per attached security. Everything in the strategy
is written per-symbol for that reason — state is keyed by symbol code, the
once-a-day gate is per symbol (a global one would let the first security
consume the day and skip the rest, stops included), and the day's cash budget
is shared across the basket so several securities cannot each size against the
same untouched cash.

## Zero trades? Check these first

1. **Does the log's FIRST line match the start date you set?** The backtest
   window is the *intersection* of every symbol's available history — one
   ticker that is not listed for the whole period clamps the entire run. A
   real case: 20 symbols, one of them (`US.SPCX`) with no prices at all, and a
   380-session request executed as 42 sessions. The log now says `[NO DATA]`
   for that symbol specifically, separately from `[warming up]`.
2. **Is it still warming up?** With `trend_period=200` the first entry is
   impossible until ~201 sessions — about **ten months** — after the first
   trigger, because no history is served from before the backtest window. On a
   Jan-2025 start that is November 2025 before anything can happen. You do not
   have to work that out: the `[first trigger]` line now **names the earliest
   date an entry is possible**, and the log counts down to it — `[warming up]
   US.MSFT: session 47 of ~201`. Lower `trend_period` (100 → ~5 months, 50 →
   ~2.5) or start earlier.
3. **Is the trigger intraday?** See above — a 1h trigger bounds the run to
   whatever intraday history exists, no matter what period you set. The Log's
   `[first trigger]` line names the first date the strategy was ever asked to
   think.
4. **Is the Trigger Symbol an index?** `.IXIC`, `.SPX` and the like have
   prices, so every rule evaluates perfectly and nothing is ever buyable. The
   strategy now says `[NOT TRADABLE]` once and stops. Set the trigger to real
   tickers.
5. **Read the Log tab.** Every refusal is printed with its reason — `[gap]`,
   `[no-trade] sources disagree`, `[error]`. A run with no trades and no log
   lines means the strategy never got a trigger at all.
6. **Warm-up** (below): a 200-day trend needs 201 closed bars.

## Two things about the backtest dialog

**Currency.** The strategy values the book in USD throughout, so
`floor_amount` is in USD regardless of what the dialog's Initial Capital says.
1,000,000 HKD is roughly 128,000 USD — against which a 40,000 floor is ~31% of
the book. Either set Initial Capital in USD, or set `floor_amount` to the
reserve you actually intend.

**Warm-up comes out of your backtest window.** The platform serves NO history
from before the period you set, so the 200-bar trend is unavailable for the
first **201 sessions of the run** — about ten months — and the indicator call
*raises* rather than returning None during that time. Budget for it: start the
backtest ten months earlier than the first trades you want to see, or shorten
`trend_period`. The log says `[warming up]` once while this is happening.

A real example: a run starting 2025-02-12 on a 1h trigger produced its first
trade on 2025-11-28 — exactly 201 sessions later — inside a window the
intraday trigger had already clamped to 18 months. Two constraints stacked:
~8 months of actual trading out of a 7-year request.

## Before pasting

```bash
python3 algo/check_and_simulate.py                     # structure + mechanism
python3 algo/check_and_simulate.py <Algo_Manual.md>    # + API signatures
```

This tool is never pasted anywhere. It encodes every editor rule learned from
a rejection: `round()` takes one argument; `min`/`max` type-check float and
require two arguments (no iterable form); and **nothing may exist at module
level except the strategy class** — no imports, no constants, no `if __name__`
block, no shim classes or stub functions, since those also trip "class/function
already defined line 0". That last rule is why the test harness cannot live
inside the strategy file: the editor analyses the whole file regardless of
guards.
