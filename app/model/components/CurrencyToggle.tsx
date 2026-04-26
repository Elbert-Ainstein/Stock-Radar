"use client";

import { cn } from "../helpers";
import type { CurrencyState } from "../hooks/useCurrency";

/**
 * Small toggle button: shows native currency badge + USD conversion toggle.
 * Hidden for USD stocks (no conversion needed).
 */
export default function CurrencyToggle({ cx }: { cx: CurrencyState }) {
  if (!cx.needsConversion) return null;

  return (
    <div className="inline-flex items-center gap-1.5">
      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[var(--border)] text-[var(--secondary)]">
        {cx.currency}
      </span>
      <button
        onClick={cx.toggleUSD}
        className={cn(
          "text-[10px] font-mono px-2 py-0.5 rounded border transition-colors",
          cx.showUSD
            ? "bg-blue-500/20 border-blue-500/40 text-blue-300"
            : "bg-[var(--card)] border-[var(--border)] text-[var(--muted)] hover:text-[var(--secondary)]"
        )}
        title={cx.showUSD ? "Showing USD converted prices" : "Click to convert to USD"}
      >
        {cx.showUSD ? "USD" : "→ USD"}
      </button>
      {cx.fxLoading && (
        <span className="w-3 h-3 border border-blue-400 border-t-transparent rounded-full animate-spin" />
      )}
    </div>
  );
}

/**
 * Inline currency badge (no toggle) — for dashboard rows.
 */
export function CurrencyBadge({ currency }: { currency: string }) {
  if (!currency || currency === "USD") return null;
  return (
    <span
      className="text-[9px] font-mono ml-1 px-1 py-0.5 rounded bg-blue-500/10 text-blue-300/70 border border-blue-500/20"
      title={`Prices in ${currency}`}
    >
      {currency}
    </span>
  );
}
