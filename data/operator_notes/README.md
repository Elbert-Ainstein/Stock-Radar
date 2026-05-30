# Per-ticker operator notes

Files in this directory are loaded by `run_socratic.py` via `fetch_operator_notes(ticker)` and
injected into the 5 Socratic prompts (model_a/b/c, corpus_callosum, rough_target_range) as the
`[OPERATOR_NOTES]` block.

## Format

- Filename: `{TICKER}.md` (uppercase, e.g. `LITE.md`, `CAMT.md`)
- Plain markdown body; the entire file content (minus a leading H1 title if present) is injected verbatim
- Keep concise — single page max. Models read this for every Socratic run on the ticker.

## What belongs here

Hume's subjective view on the ticker that the engine cannot see by reading data:
- Long-term thesis additions (e.g. "long washout ending → rally")
- Domain knowledge not in 10-K / 10-Q (e.g. "2027 product price hikes confirmed by IR call")
- Pushback on prior engine output (e.g. "system $1,050 upper bound undershoots because...")

## What does NOT belong here

- Anything observable in finance_data (revenue, margin, guidance — engine sees these)
- Macro view (that lives in `macro_environment` table, propagated via `[MACRO_CONTEXT]`)
- Wave-level view (that lives in `wave_health` table, propagated via `[WAVE_CONTEXT]`)
- One-off "is this stock interesting?" — that's discovery, not operator notes

## Anti-sycophancy contract

The prompts instruct models to treat operator notes as **Hume's subjective view**, not as fact.
Models must address the notes by name in `reasoning_bullets` but are free (and encouraged) to
disagree with explicit math. The goal is captured pushback that re-runs see, not coerced agreement.
