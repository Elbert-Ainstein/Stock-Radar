"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { cn } from "./helpers";

type RunState = "idle" | "starting" | "running" | "complete" | "error";

interface Props {
  ticker: string;
  /** Optional ISO timestamp of the last successful thesis run. */
  lastRunAt?: string | null;
  /** Called when a re-run finishes successfully (so caller can refresh). */
  onComplete?: () => void;
}

const POLL_INTERVAL_MS = 5_000;
const MAX_POLL_DURATION_MS = 5 * 60 * 1_000;

/** Detect Module 1 sanity-check failure from the Python error tail. */
function isSanityCheckError(err: string | null): boolean {
  if (!err) return false;
  return (
    err.includes("revenue sanity check FAILED") ||
    err.includes("SUSPECT DATA") ||
    err.includes("EarningsFetchError")
  );
}

/** Strip the Node.js execFile wrapper to get just the Python message. */
function cleanError(err: string | null): string {
  if (!err) return "";
  // Node.js execFile prepends "Command failed: <command>\n" — strip it
  const idx = err.indexOf("\n");
  if (err.startsWith("Command failed:") && idx > 0) {
    return err.slice(idx + 1).trim();
  }
  return err.trim();
}

export default function ThesisRerunButton({ ticker, lastRunAt, onComplete }: Props) {
  const [state, setState] = useState<RunState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [showFullError, setShowFullError] = useState(false);
  const pollStartRef = useRef<number>(0);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, [ticker]);

  // On mount: check if a run is already in flight
  useEffect(() => {
    let cancelled = false;
    fetch(`/api/thesis/${encodeURIComponent(ticker)}/rerun`)
      .then((r) => r.json())
      .then((d) => {
        if (cancelled) return;
        if (d.running) {
          setState("running");
          startPolling();
        } else if (d.last_status && d.last_status.ok === false && d.last_status.error) {
          // Surface the prior failure so the user can retry without re-clicking blind
          setState("error");
          setError(d.last_status.error);
        }
      })
      .catch(() => { /* non-fatal */ });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker]);

  const startPolling = useCallback(() => {
    if (!mountedRef.current) return;
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    pollStartRef.current = Date.now();
    pollTimerRef.current = setInterval(async () => {
      if (!mountedRef.current) {
        if (pollTimerRef.current) clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
        return;
      }
      try {
        const r = await fetch(`/api/thesis/${encodeURIComponent(ticker)}/rerun`);
        const d = await r.json();
        if (!d.running) {
          if (pollTimerRef.current) clearInterval(pollTimerRef.current);
          pollTimerRef.current = null;
          const status = d.last_status as { ok?: boolean; error?: string | null } | null | undefined;
          if (!status || status.ok === false) {
            setState("error");
            setError(status?.error || "Run finished but no status file — verify data manually");
            return;
          }
          setState("complete");
          onComplete?.();
          setTimeout(() => setState("idle"), 3000);
          return;
        }
        if (Date.now() - pollStartRef.current > MAX_POLL_DURATION_MS) {
          if (pollTimerRef.current) clearInterval(pollTimerRef.current);
          pollTimerRef.current = null;
          setState("error");
          setError("Run did not finish within 5 minutes — check server logs");
        }
      } catch (e) {
        console.warn(`[thesis rerun ${ticker}] poll error:`, e);
      }
    }, POLL_INTERVAL_MS);
  }, [ticker, onComplete]);

  const trigger = useCallback(async (overrideSuspectRecent = false) => {
    setState("starting");
    setError(null);
    setShowFullError(false);
    try {
      const r = await fetch(`/api/thesis/${encodeURIComponent(ticker)}/rerun`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          trigger_reason: "manual",
          override_suspect_recent: overrideSuspectRecent,
        }),
      });
      const d = await r.json();
      if (r.status === 409) {
        setState("running");
        startPolling();
        return;
      }
      if (!r.ok) {
        throw new Error(d.message || d.error || `HTTP ${r.status}`);
      }
      setState("running");
      startPolling();
    } catch (e) {
      setState("error");
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [ticker, startPolling]);

  const disabled = state === "starting" || state === "running" || state === "complete";
  const label =
    state === "idle"     ? "Re-run thesis"
  : state === "starting" ? "Starting…"
  : state === "running"  ? "Running… (~60-120s)"
  : state === "complete" ? "✓ Complete"
  :                        "Failed";

  const lastRunHint = formatLastRun(lastRunAt);
  const cleanedError = cleanError(error);
  const isSanityCheck = isSanityCheckError(cleanedError);
  const errorSummary = cleanedError ? cleanedError.split("\n")[0].slice(0, 200) : "";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "stretch" }}>
      <div className="flex items-center gap-2">
        {lastRunHint && (
          <span className="text-[10px] text-[var(--muted)] hidden sm:inline">
            Last run: <span className="font-mono text-[var(--secondary)]">{lastRunHint}</span>
          </span>
        )}
        <button
          onClick={() => trigger(false)}
          disabled={disabled}
          className={cn(
            "px-2.5 py-1 rounded-md text-xs font-semibold transition-colors border",
            state === "idle" &&
              "bg-emerald-500/10 text-emerald-300 border-emerald-500/30 hover:bg-emerald-500/20",
            (state === "starting" || state === "running") &&
              "bg-yellow-500/10 text-yellow-300 border-yellow-500/30 cursor-wait",
            state === "complete" &&
              "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
            state === "error" &&
              "bg-red-500/10 text-red-400 border-red-500/30 hover:bg-red-500/15",
          )}
          title={errorSummary || "Triggers run_thesis.py via /api/thesis/[ticker]/rerun"}
        >
          {label}
        </button>
      </div>

      {state === "error" && cleanedError && (
        <div style={{
          padding: "8px 10px",
          background: "var(--sr-err-bg, rgba(255, 80, 80, 0.08))",
          border: "1px solid var(--sr-err-ink, rgba(255, 80, 80, 0.3))",
          borderRadius: 4,
          fontSize: 11,
          color: "var(--sr-err-ink, #c25)",
          fontFamily: "var(--sr-font-mono, monospace)",
          maxWidth: 480,
          lineHeight: 1.45,
        }}>
          {isSanityCheck ? (
            <>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>
                Module 1 sanity check blocked the run
              </div>
              <div style={{ marginBottom: 6, fontFamily: "inherit" }}>
                The data provider returned a recent quarter that's 2-3× the trailing average.
                If you've cross-checked against the 10-Q and the jump is real (post-spinoff,
                post-IPO, M&A close), retry with override. For known provider bugs (e.g. MU's
                yfinance/EODHD anomaly), don't override — the thesis would be built on bad numbers.
              </div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                <button
                  onClick={() => trigger(true)}
                  style={{
                    padding: "4px 10px",
                    background: "var(--sr-action, #14120f)",
                    color: "var(--sr-action-ink, #fcfcfa)",
                    border: "none",
                    borderRadius: 3,
                    fontSize: 11,
                    fontWeight: 500,
                    cursor: "pointer",
                  }}
                  title="POST with override_suspect_recent=true"
                >
                  Retry with override
                </button>
                <button
                  onClick={() => setShowFullError(!showFullError)}
                  style={{
                    padding: "4px 10px",
                    background: "transparent",
                    color: "var(--sr-err-ink, #c25)",
                    border: "1px solid currentColor",
                    borderRadius: 3,
                    fontSize: 11,
                    cursor: "pointer",
                  }}
                >
                  {showFullError ? "Hide details" : "Show details"}
                </button>
              </div>
            </>
          ) : (
            <>
              <div style={{ marginBottom: 4 }}>
                <span aria-hidden style={{ marginRight: 4 }}>⚠</span>
                {errorSummary || "Subprocess failed"}
              </div>
              <button
                onClick={() => setShowFullError(!showFullError)}
                style={{
                  padding: "2px 8px",
                  background: "transparent",
                  color: "var(--sr-err-ink, #c25)",
                  border: "1px solid currentColor",
                  borderRadius: 3,
                  fontSize: 10,
                  cursor: "pointer",
                  marginTop: 2,
                }}
              >
                {showFullError ? "Hide details" : "Show details"}
              </button>
            </>
          )}
          {showFullError && (
            <pre style={{
              marginTop: 8,
              padding: 8,
              background: "rgba(0,0,0,0.05)",
              borderRadius: 3,
              fontSize: 10,
              maxHeight: 240,
              overflow: "auto",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              fontFamily: "var(--sr-font-mono, monospace)",
              color: "var(--sr-ink-1, #34302a)",
            }}>{cleanedError}</pre>
          )}
        </div>
      )}
    </div>
  );
}

function formatLastRun(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (!isFinite(t)) return null;
  const ageMs = Date.now() - t;
  if (ageMs < 60_000) return "just now";
  if (ageMs < 3600_000) return `${Math.floor(ageMs / 60_000)}m ago`;
  if (ageMs < 86400_000) return `${Math.floor(ageMs / 3600_000)}h ago`;
  return `${Math.floor(ageMs / 86400_000)}d ago`;
}
