# algo/ — The Settled-Basis Ladder

**One file: `settled_basis_ladder.py`.** Paste it whole into the strategy
editor. It contains the strategy, its full documentation, and an offline
self-test the platform never runs.

```bash
python3 settled_basis_ladder.py                     # mechanism self-test
python3 settled_basis_ladder.py <Algo_Manual.md>    # + API signature check
```

If the editor objects to anything below the `OFFLINE SELF-TEST` banner,
delete from that banner to the end of the file — nothing above it depends on
anything below it, and the strategy is complete without it.

**Trigger: run at a specified time, ~15:50 ET — not on the daily bar.** US
market orders are RTH-only, so a daily-bar trigger fires after the close and
is rejected live while filling happily in a backtest. Decisions still read the
last closed bar; only execution moves inside market hours.

Everything else — the translation from the constitution's laws, the
parameters, how to judge results honestly, and the known limitations — is in
the file's header, so there is exactly one place to keep current.
