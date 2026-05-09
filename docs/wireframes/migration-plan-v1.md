# Stock Radar Frontend Migration Plan — v1

**Goal:** translate the Production wireframe (warm-neutral palette, sr- prefix, 5×4 surface tones, 3-breakpoint, both themes) into the actual Next.js codebase. Fix the four gaps Hume named while we're at it. Don't ratchet complexity.

---

## Confirmed gaps (per Hume's spot-check of the production wireframes)

1. **DriftChip lacks semantic labels.** Currently shows direction + magnitude. Brief required "engine corroborates / thesis above floor / regulatory or cycle risk" semantic copy paired with the percentage.
2. **Hume Notes treatment got generic-ified.** Production wireframes show a curated bullet list with "Add a note…" input. Brief required: monospace block, "preserved verbatim" eyebrow, "● saved Xs ago · NNNch" save indicator, no distinction between Hume-typed and Sonnet-curated.
3. **Model detail tab strip is wrong.** Production wireframes show 4 tabs (Thesis / Floor / Inputs / Runs). Real product has 8 (Thesis / Setup / Risks / Floor / Income / Cashflow / Formulas / What-If). No mobile/tablet artboards exist.
4. **`conv-fade` token has no source.** V3 prompt emits HIGH/MEDIUM/LOW/BROKEN — four values. Wireframes added a fifth color (FADE). Either drop the token or extend the prompt.

## Decisions locked before building

- **Conviction:** keep HIGH/MEDIUM/LOW/BROKEN as the canonical labels (data + display). Map at render time to color tokens (`HIGH → conv-strong`, `MEDIUM → conv-good`, `LOW → conv-watch`, `BROKEN → conv-broken`). Drop `conv-fade` for now; reserve as extension point if a future v4 prompt emits a fifth tier.
- **Variants chosen:**
  - Watchlist: A (Bloomberg-tight) as default, C (right-rail preview) as `≥1280px` enhancement
  - Stock detail: A (inline accordion) as default, B (full route `/stock/[ticker]`) as deep-link
  - Model detail: A (canonical layout)
- **Token migration strategy:** keep existing `--bg / --text / --muted / --border` aliases as backwards-compatible pointers to the new `--paper-1 / --ink-1` tokens; new components target the new tokens, old components keep working until migrated.
- **Animation:** add ONE shimmer keyframe globally for skeletons. No other animation.

---

## Phases

### Phase 0 — save the artifacts (5 min)
Save the production HTML and wireframe JSX/CSS into `docs/wireframes/v2-production/` so the source of truth lives in the repo.

### Phase 1 — token system (1 session)
File: `app/globals.css`

- Add new tokens: `--paper-1/-2/-3`, `--ink-1/-2/-3/-4`, `--rule-soft/-strong`, `--conv-strong/-strong-bg`, `--conv-good/-good-bg`, `--conv-watch/-watch-bg`, `--conv-broken/-broken-bg`. Both `:root` (light) and `[data-theme="dark"]` blocks.
- Map existing aliases for back-compat: `--bg → --paper-1`, `--bg-elevated → --paper-2`, `--text → --ink-1`, `--secondary → --ink-2`, `--muted → --ink-3`, `--faint → --ink-4`, `--border → --rule-soft`, `--border-hover → --rule-strong`, etc.
- Add ONE global keyframe: `@keyframes sr-shimmer { 0% { background-position: -200% 0; } 100% { background-position: 200% 0; } }` and a `.sr-skel` utility class.
- Verify: visit existing dashboard, confirm nothing visually regressed (only the alias change should fire — colors should look identical).

**Deliverable:** new tokens defined, old code still works, one shimmer keyframe globally available.

### Phase 2 — cross-cutting atoms (1 session)
Folder: `app/components/sr/`

Build four small, well-typed components:

1. `<ConvictionBadge tier="HIGH"|"MEDIUM"|"LOW"|"BROKEN" size="sm"|"lg" />` — internal map to `conv-strong/-good/-watch/-broken` color tokens. ≥4.5:1 contrast in both themes. Renders the data label verbatim ("HIGH" not "STRONG").
2. `<MoneyValue value={number} currency="USD"|"HKD"|"EUR" big? signed? />` — tabular figures, decimal-aligned, signed coloring with sign char (+/−) NOT just color.
3. `<PercentValue value={number} signed? />` — similar shape.
4. `<DeltaChip value={number} unit="%"|"$" />` — small pill.

Each gets a Storybook-equivalent: a route at `/dev/sr-atoms` that renders them in all variants × both themes side by side. Easier to iterate than testing inside the live dashboard.

**Deliverable:** 4 atoms shipped, dev preview route exists, all 8 variants × 2 themes render correctly.

### Phase 3 — layout primitives (1 session)
Folder: `app/components/sr/`

1. `<DataRow>` — the watchlist row. Mobile-first: ticker + price + score + thesis target + conviction badge. Tablet adds sparkline + sector. Desktop: full 12-column. Implements the brief's "thesis target visible at every breakpoint" rule.
2. `<KPITile label value sub? big? />` — the unit used in DCF summary grid and thesis headline strip.
3. `<TabBar tabs activeId onSelect />` — `overflow-x-auto` + `scroll-snap-type: x mandatory` on mobile, clean underline on desktop.
4. `<SectionHeader>`, `<CollapsibleSection>` — for memory panel sections.
5. `<EmptyState>` and `<LoadFailedState>` — calm, never apologetic, distinguishable from each other.
6. `<DriftChip>` with the SEMANTIC labels — small absolute drift produces "engine corroborates"; thesis above floor by ≥15% produces "thesis above floor (re-rating priced)"; thesis below floor produces "thesis below floor (regulatory or cycle risk)". Maps to color via the convention `corroborates → emerald, above → yellow, below → orange`.

**Deliverable:** 6 layout primitives shipped, all preview at `/dev/sr-atoms`. Tab strip works on a 320px viewport.

### Phase 4 — Watchlist migration (1 session)
File: `app/dashboard/StockRow.tsx`, `app/dashboard/Dashboard.tsx`

- Replace `<StockRow>` body with `<DataRow>` composition.
- Mobile breakpoint: `min-w-[100px]` ticker + price + score + `<ConvictionBadge>` + thesis target. Sparkline / scout count / sector hidden via `hidden md:block`.
- Filter strip: rebuild with `<Chip>` atom and the conviction-tier toggle row from variant A.
- `≥1280px`: add right-rail preview pane wired to selected row (variant C). Arrow-key cycling.
- Skeleton state during initial load using `.sr-skel` utility.

**Deliverable:** Watchlist works at 320px / 768px / 1280px / 1440px, four artboards screenshot-able. Existing detail-panel-on-click behavior preserved.

### Phase 5 — Stock detail migration (1 session, FIXES Hume Notes GAP)
File: `app/dashboard/StockDetail.tsx`, plus optional new `/stock/[ticker]/page.tsx`

- Thesis headline strip at top (emerald, dominant).
- 3-column body (Setup | Risks+Catalysts | Hume Notes + Kill Triggers).
- **Hume Notes treatment**: monospace `font-mono`, eyebrow "HUME NOTES · verbatim", live "● saved 12s ago · 412ch" indicator (re-derived from existing /notes API state), `<textarea>` styled to match the wireframe — explicit "this is a logbook" framing. **NOT a bullet list.**
- Memory panel below, collapsible sections (existing component reused, restyled).
- Scout signals strip at bottom.
- Empty state: "No thesis run yet" using `<EmptyState>` primitive.

Optional `/stock/[ticker]/page.tsx` route as deep-link target (same content, full-page chrome).

**Deliverable:** Stock detail looks like wireframe variant A. Hume Notes treatment matches the brief. Empty + load-failed states present.

### Phase 6 — Model detail migration (1 session, FIXES tab strip GAP)
File: `app/model/[ticker]/detailed/DetailedModel.tsx`

- Keep all 8 tabs: Thesis / Setup / Risks / Floor / Income / Cashflow / Formulas / What-If.
- Replace tab rendering with `<TabBar>` primitive — gets mobile scroll-snap for free.
- Thesis headline strip (already present from prior session) — restyle with new tokens.
- DCF summary grid: collapse `grid-cols-4` → `grid-cols-2 lg:grid-cols-4`.
- DriftChip on FloorTab: replace direction+magnitude with the SEMANTIC labels per phase 3.
- Tab content panels: each gets a quick pass to use new atoms (`<KPITile>`, `<MoneyValue>`, etc.) — no behavior changes.

**Deliverable:** Model detail still shows all 8 tabs. Mobile scroll-snap works. DriftChip says "engine corroborates" not just "+33%".

### Phase 7 — smaller surfaces (1 session, OPTIONAL)
- Discovery page restyle
- Ask AI page restyle
- Logs page restyle
- Model picker restyle

Skip if time-constrained; these are not on the critical path.

### Phase 8 — theme toggle wiring (≤1 hr)
- Verify the existing cookies-driven theme toggle still flips correctly with the new tokens
- Add a "match system" option if not already present
- Verify all four conviction tiers and the drift indicator render legibly in both themes

### Phase 9 — verify
- `npx tsc --noEmit` — clean
- `pytest scripts/test_engine.py` — 37/37 still pass
- Screenshot at 320 / 640 / 1024 / 1440 widths in both themes
- Review squad red-team pass on the migration

---

## Out of scope for this migration

- Discovery page redesign beyond Phase 7's restyle pass
- New backend functionality
- Re-running theses (the current 12 rows stay as-is)
- Adding a 5th conviction tier (deferred until a v4 prompt that emits it)
- Mobile nav drawer (the existing horizontal nav scrolls — good enough)
- Color-blind alternate theme
- Custom mascot / logo

---

## Sequencing rationale

- Phase 0 → 1 → 2 → 3 is the unshippable foundation. None of it is user-visible until phase 4.
- Phase 4 (watchlist) is the smallest user-visible win; migrating it alone is a meaningful improvement.
- Phase 5 / 6 are independent of each other; either can be done first based on what's most painful daily.
- Phase 7 is genuinely optional.

A reasonable session-by-session breakdown:
- **Session A** (1 evening): Phase 0 + 1 + 2 (foundation + atoms). Zero user-visible change yet, but everything downstream depends on this.
- **Session B** (1 evening): Phase 3 + 4 (primitives + watchlist). First user-visible upgrade.
- **Session C** (1 evening): Phase 5 (stock detail with Hume Notes fix).
- **Session D** (1 evening): Phase 6 (model detail with 8-tab + mobile scroll-snap + DriftChip semantic).
- **Session E** (optional): Phase 7-9.

---

## Risk / what I want red-team to look at

- Token migration period: existing components use `--bg`/`--text`. New components use `--paper-1`/`--ink-1`. The alias plan (point old at new) means there's a moment where some components are visually slightly different from others. Is the alias plan correct, or will old components silently regress?
- Conviction map: if the V3 prompt later emits a string outside HIGH/MEDIUM/LOW/BROKEN (e.g. "MIXED" or empty), does the renderer fall through to a sensible default?
- Skeleton shimmer: is one global keyframe enough or will I need per-component keyframes?
- 4-tab vs 8-tab: the wireframes show 4. Production needs 8. Is the reviewer's instinct that 8 is too many on mobile (where scroll-snap is the workaround) or that the 4-tab consolidation is actually right and I should fold the 4 statement-style tabs into "Inputs" / "Runs"?
- Hume Notes textarea: the brief says monospace `<textarea>` with auto-save. The current implementation already does most of this. Is migrating the styling enough, or does the wireframe imply a deeper UX change (e.g. "notes are a stream, not a single field")?
- Multi-session sequencing: is splitting phase 4/5/6 into separate sessions wise (forces incremental review) or stupid (forces partial-migration ugliness during the in-between weeks)?

