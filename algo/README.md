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

## Symbols — declare exactly as many as you will fill

Seven slots (`sym1`…`sym7`). **The backtest dialog will not enable "Next"
while any declared slot is empty**, so a spare slot is not free — it blocks
the run. To change the count, edit BOTH `trigger_symbols()` and the tuple in
`_symbols()`; one without the other declares a slot that is never evaluated.
The platform allows up to 50.

Note `max_position_pct` is a per-name cap, not a target: with 25% of deployable
capital per name, at most four positions can be full size, and the rest are
rationed by cash in the order they are evaluated.

## Two things about the backtest dialog

**Currency.** The strategy values the book in USD throughout, so
`floor_amount` is in USD regardless of what the dialog's Initial Capital says.
1,000,000 HKD is roughly 128,000 USD — against which a 40,000 floor is ~31% of
the book. Either set Initial Capital in USD, or set `floor_amount` to the
reserve you actually intend.

**Warm-up.** The 200-day trend line needs 201 closed bars, so a run starting
2019-05-01 cannot trade until roughly Feb–Mar 2020. That is expected, not a
broken run. (The 6-month parabola lookback needs only 128 bars, so the MA
binds first and there is no starter-size-only artifact during warm-up.)

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
