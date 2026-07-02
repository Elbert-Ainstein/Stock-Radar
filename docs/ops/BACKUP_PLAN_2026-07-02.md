# Backup & disaster-recovery plan — prepared 2026-07-02 (sprint 3.7)

**Status: PREPARED, NOT ACTIVE.** The audit found zero backup automation for a
single-operator, single-laptop topology: the Supabase DB (theses, seals,
grades, signals) and `data/memory/*.md` (per-ticker thesis memory incl.
hand-written Hume Notes) each exist in exactly one place. A lost laptop
silently degrades every future thesis run (memory loads return None, no
error); an accidental table wipe destroys the append-only calibration record.

## 1. Supabase — nightly logical dump to GitHub Actions artifacts

Draft workflow: `.github/workflows/db-backup.yml` (workflow_dispatch ONLY —
no schedule until you approve; it is inert until the secret below exists).

- Dumps via `pg_dump` over the Supabase pooled connection.
- Uploads as a workflow artifact with 30-day retention (private repo).
- To activate: add the schedule block (commented in the file) after a manual
  dispatch has produced one good artifact you've test-restored.

**Needed from you (GitHub repo → Settings → Secrets and variables → Actions):**
- `SUPABASE_DB_URL` — the Postgres connection string from Supabase dashboard →
  Project Settings → Database → Connection string (URI, port 5432, include
  the password). This is the DB superuser path — a secret, never in .env.

Alternative (zero-maintenance, paid): enable Point-in-Time Recovery in the
Supabase dashboard (Settings → Database → PITR). Recommended in addition to,
not instead of, the dumps — PITR protects against oops-deletes, the dumps
against account/project loss.

## 2. `data/memory/*.md` — version in git

These are the highest-value irreplaceable files (accumulated thesis memory +
operator notes) and are currently gitignored, existing only on your laptop.

**Proposed change (needs your OK — the notes may contain private views, but
the repo is private):** whitelist them in `.gitignore`:

```gitignore
# keep pipeline outputs ignored, but version the irreplaceable memory layer
!data/memory/
!data/memory/*.md
```

Then on your machine: `git add data/memory && git commit`. From then on the
memory layer travels with every clone and push.

## 3. Explicitly out of scope (low value)

- `data/cron/` logs, `data/analyst_panel.json` — regenerable.
- Local `analysis.json` artifacts — rebuilt by any pipeline run.

## Restore drill (do once after activation)

1. Download the latest backup artifact; `pg_restore --list` to inspect.
2. Restore into a scratch Supabase project; run
   `python scripts/run_checkpoint.py --dry-run` against it — the grader
   listing genuine seals proves theses/prediction tables survived intact.
3. Clone the repo fresh on a second machine; confirm `data/memory/` is
   present and a thesis dry-run picks up the PRIOR CONTEXT block.
