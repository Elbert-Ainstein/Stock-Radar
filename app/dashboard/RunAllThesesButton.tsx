"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { cn } from "./helpers";

interface Props {
  tickers: string[];
  onAllComplete?: () => void;
}

type Status = "idle" | "starting" | "running" | "complete" | "partial" | "error";

const POLL_MS = 7_000;
const TIMEOUT_MS = 8 * 60 * 1_000;

export default function RunAllThesesButton({ tickers, onAllComplete }: Props) {
  const [status, setStatus] = useState<Status>("idle");
  const [done, setDone] = useState<Set<string>>(new Set());
  const [errors, setErrors] = useState<Map<string, string>>(new Map());
  // Refs mirror state so the poll closure always reads live values, not the
  // captured snapshot from when setInterval was created. Without these mirrors
  // the interval ticks regress the counter and lose completed tickers.
  const doneRef = useRef<Set<string>>(new Set());
  const errorsRef = useRef<Map<string, string>>(new Map());
  const startedAt = useRef(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const total = tickers.length;

  const trigger = useCallback(async () => {
    if (total === 0) return;
    setStatus("starting");
    setDone(new Set());
    setErrors(new Map());
    doneRef.current = new Set();
    errorsRef.current = new Map();
    startedAt.current = Date.now();

    const results = await Promise.allSettled(
      tickers.map((t) =>
        fetch(`/api/thesis/${encodeURIComponent(t)}/rerun`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ trigger_reason: "manual" }),
        }).then(async (r) => {
          if (r.status === 409) return { ticker: t, kicked: true, alreadyRunning: true };
          if (!r.ok) {
            const d = await r.json().catch(() => ({}));
            throw new Error(d.message || d.error || `HTTP ${r.status}`);
          }
          return { ticker: t, kicked: true, alreadyRunning: false };
        }),
      ),
    );

    const kickErrors = new Map<string, string>();
    for (let i = 0; i < results.length; i++) {
      const r = results[i];
      if (r.status === "rejected") {
        kickErrors.set(tickers[i], r.reason instanceof Error ? r.reason.message : String(r.reason));
      }
    }
    errorsRef.current = new Map(kickErrors);
    if (mounted.current) setErrors(kickErrors);

    if (kickErrors.size === total) {
      if (mounted.current) setStatus("error");
      return;
    }

    if (mounted.current) setStatus("running");

    pollRef.current = setInterval(async () => {
      if (!mounted.current) {
        if (pollRef.current) clearInterval(pollRef.current);
        return;
      }
      if (Date.now() - startedAt.current > TIMEOUT_MS) {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = null;
        setStatus("partial");
        return;
      }

      const stillRunning: string[] = [];
      const newlyDone = new Set(doneRef.current);
      const newErrors = new Map(errorsRef.current);

      const checks = await Promise.allSettled(
        tickers.map((t) =>
          fetch(`/api/thesis/${encodeURIComponent(t)}/rerun`)
            .then((r) => r.json())
            .then((d) => ({ ticker: t, running: !!d.running, last_status: d.last_status })),
        ),
      );

      for (const r of checks) {
        if (r.status !== "fulfilled") continue;
        const { ticker, running, last_status } = r.value;
        if (running) {
          stillRunning.push(ticker);
        } else {
          newlyDone.add(ticker);
          const ls = last_status as { ok?: boolean; error?: string | null } | null;
          if (ls && ls.ok === false) {
            newErrors.set(ticker, ls.error?.split("\n")[0].slice(0, 200) || "Subprocess failed");
          } else if (!ls && !kickErrors.has(ticker)) {
            newErrors.set(ticker, "Run finished but no status file (verify manually)");
          }
        }
      }

      doneRef.current = newlyDone;
      errorsRef.current = newErrors;
      if (mounted.current) {
        setDone(newlyDone);
        setErrors(newErrors);
      }

      if (stillRunning.length === 0) {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = null;
        if (mounted.current) {
          setStatus(newErrors.size > 0 ? "partial" : "complete");
          onAllComplete?.();
          setTimeout(() => {
            if (mounted.current) setStatus("idle");
          }, 4000);
        }
      }
    }, POLL_MS);
  }, [tickers, total, onAllComplete]);

  const disabled = status === "starting" || status === "running" || status === "complete";
  const label =
    status === "idle"
      ? `Run all theses (${total})`
      : status === "starting"
      ? "Starting…"
      : status === "running"
      ? `Running… ${done.size}/${total}`
      : status === "complete"
      ? `✓ All ${total} done`
      : status === "partial"
      ? `⚠ ${done.size}/${total} (${errors.size} errors)`
      : "Failed";

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={trigger}
        disabled={disabled || total === 0}
        className={cn(
          "px-3 py-1.5 rounded-md text-xs font-semibold transition-colors border",
          status === "idle" &&
            "bg-emerald-500/10 text-emerald-300 border-emerald-500/30 hover:bg-emerald-500/20",
          (status === "starting" || status === "running") &&
            "bg-yellow-500/10 text-yellow-300 border-yellow-500/30 cursor-wait",
          status === "complete" &&
            "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
          status === "partial" &&
            "bg-orange-500/15 text-orange-300 border-orange-500/35",
          status === "error" &&
            "bg-red-500/10 text-red-400 border-red-500/30",
        )}
        title={
          errors.size > 0
            ? Array.from(errors.entries()).map(([t, m]) => `${t}: ${m}`).join("\n")
            : `Triggers run_thesis.py for all ${total} watchlist tickers in parallel.`
        }
      >
        {label}
      </button>
    </div>
  );
}
