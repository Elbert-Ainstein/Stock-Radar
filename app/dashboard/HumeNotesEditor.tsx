"use client";

import { useEffect, useState, useCallback } from "react";
import { cn } from "./helpers";

const MAX_CHARS = 8000;

/**
 * Mirror of scripts/lib/memory.py::_sanitize_notes_body.
 * Replaces leading `## ` with `### ` (preserving leading whitespace) so a
 * read-back-failure fallback already matches what the server will return.
 */
function clientSanitize(body: string): string {
  return body.replace(/^([ \t]*)## /gm, "$1### ");
}

export default function HumeNotesEditor({ ticker }: { ticker: string }) {
  const [notes, setNotes] = useState<string>("");
  const [serverNotes, setServerNotes] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastSavedAt, setLastSavedAt] = useState<number | null>(null);
  // Tick once a second so "saved Xs ago" stays accurate without re-saving.
  const [, setNowTick] = useState(0);
  useEffect(() => {
    if (lastSavedAt == null) return;
    const id = setInterval(() => setNowTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [lastSavedAt]);

  const dirty = notes !== serverNotes;

  // Format "saved Xs ago / Xm ago / Xh ago" relative to now.
  const savedAgoLabel = (() => {
    if (lastSavedAt == null) return null;
    const sec = Math.max(0, Math.round((Date.now() - lastSavedAt) / 1000));
    if (sec < 60) return `${sec}s ago`;
    if (sec < 3600) return `${Math.round(sec / 60)}m ago`;
    return `${Math.round(sec / 3600)}h ago`;
  })();

  // Load on mount + when ticker changes
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(`/api/thesis/${encodeURIComponent(ticker)}/notes`)
      .then((r) => r.json())
      .then((d) => {
        if (cancelled) return;
        const v = typeof d.notes === "string" ? d.notes : "";
        setNotes(v);
        setServerNotes(v);
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  const save = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      const r = await fetch(`/api/thesis/${encodeURIComponent(ticker)}/notes`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes }),
      });
      const data = await r.json();
      if (!r.ok) {
        const msg = data.message || data.error || `HTTP ${r.status}`;
        throw new Error(msg);
      }
      // Use the server-returned (post-sanitize) body, not the local one.
      // Otherwise sanitized differences (## -> ###) make dirty stay true
      // after every save that triggered sanitization.
      // Prefer the server's post-sanitize body. If absent (re-read failed),
      // apply the same sanitization client-side so dirty stays accurate.
      const savedNotes =
        typeof data.notes === "string" ? data.notes : clientSanitize(notes);
      setServerNotes(savedNotes);
      setNotes(savedNotes);
      setLastSavedAt(Date.now());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [ticker, notes]);

  return (
    <div className="mb-6">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs uppercase tracking-wider text-[var(--accent-muted)] font-semibold">
          Hume Notes · preserved verbatim
        </h3>
        <span className="text-[10px] text-[var(--muted)] font-mono">
          {notes.length}/{MAX_CHARS}ch
        </span>
      </div>
      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        disabled={loading || saving}
        placeholder="- I had dinner with management; they hinted at OCS upside&#10;- Watch for Q3 capex commentary&#10;&#10;Markdown supported. Preserved verbatim across thesis re-runs."
        className={cn(
          "w-full min-h-[120px] max-h-[400px] p-3 rounded-lg border bg-[var(--bg)] text-sm",
          "font-mono leading-relaxed resize-y outline-none",
          "border-[var(--border)] focus:border-[var(--accent-muted)]",
          loading && "opacity-50",
        )}
        maxLength={MAX_CHARS}
      />
      <div className="flex items-center justify-between mt-2">
        <div className="text-[11px] text-[var(--muted)]">
          {error && <span className="text-red-400">⚠ {error}</span>}
          {!error && savedAgoLabel && !dirty && (
            <span className="text-emerald-400">● saved {savedAgoLabel}</span>
          )}
          {!error && dirty && !saving && (
            <span className="text-yellow-400">● unsaved changes</span>
          )}
          {saving && <span className="text-[var(--muted)]">○ saving…</span>}
        </div>
        <button
          onClick={save}
          disabled={!dirty || saving || loading}
          className={cn(
            "px-3 py-1.5 rounded-md text-xs font-semibold transition-colors",
            dirty && !saving
              ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 hover:bg-emerald-500/30"
              : "bg-[var(--hover)] text-[var(--muted)] border border-[var(--border)] cursor-not-allowed",
          )}
        >
          Save notes
        </button>
      </div>
      <p className="text-[10px] text-[var(--muted)] mt-1.5 italic">
        Personal notes for {ticker}. Stored locally in
        <code className="mx-1 px-1 py-0.5 rounded bg-[var(--hover)] text-[var(--secondary)]">
          data/memory/{ticker.replace(/\./g, "_")}.md
        </code>
        under <code className="px-1 py-0.5 rounded bg-[var(--hover)] text-[var(--secondary)]">## Hume Notes</code>.
        The thesis maintenance pass preserves this section verbatim. Tip:
        <code className="mx-1 px-1 py-0.5 rounded bg-[var(--hover)] text-[var(--secondary)]">## headings</code>
        inside your notes are auto-converted to
        <code className="mx-1 px-1 py-0.5 rounded bg-[var(--hover)] text-[var(--secondary)]">###</code>
        on save (avoids breaking the section parser). Use
        <code className="mx-1 px-1 py-0.5 rounded bg-[var(--hover)] text-[var(--secondary)]">###</code>
        or bullets for sub-structure.
      </p>
    </div>
  );
}
