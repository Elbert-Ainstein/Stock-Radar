# algo/ — The Settled-Basis Ladder

**Paste `settled_basis_ladder.py` whole into the strategy editor.** It is
documentation comments plus the strategy class, and nothing else — the editor
allows no top-level code at all.

**Trigger: run at a specified time, ~15:50 ET — not on the daily bar.** US
market orders are RTH-only, so a daily-bar trigger fires after the close: live
rejects every order while the backtest fills happily. Decisions still read the
last closed bar; only execution moves inside market hours.

Everything else — the translation from the constitution's laws, every
parameter, the three acceptance tests, the known limitations — lives in the
file's header, so there is one place to keep current.

## Symbols

Twelve trigger slots (`sym1`…`sym12`); fill as many as you want, empty ones are
skipped. To go further — the platform allows 50 — add a `declare_trig_symbol()`
line in `trigger_symbols()` **and** its entry in `_symbols()`; both places, or
the slot is declared but never evaluated.

Note `max_position_pct` is a per-name cap, not a target: with 25% of deployable
capital per name, at most four positions can be full size, and the rest are
rationed by cash in the order they are evaluated.

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
