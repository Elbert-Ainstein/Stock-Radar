"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { STOCK_DATABASE } from "./stock-database";

// ─── Ticker Search with Live Yahoo Finance Autocomplete ───

export default function TickerSearch({
  existingTickers,
  onAddTicker,
}: {
  existingTickers: string[];
  onAddTicker: (ticker: string, name: string, sector: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [liveSuggestions, setLiveSuggestions] = useState<{ ticker: string; name: string; sector: string; exchange: string }[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, []);

  // Live search via Yahoo Finance autocomplete API
  const searchTickers = useCallback(async (q: string) => {
    if (!q || q.length < 1) {
      setLiveSuggestions([]);
      return;
    }
    setIsSearching(true);
    try {
      // Use our server-side proxy to avoid CORS issues
      const resp = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
      if (resp.ok) {
        const data = await resp.json();
        const quotes = (data.quotes || [])
          .filter((r: any) => !existingTickers.includes(r.ticker))
          .slice(0, 8);
        setLiveSuggestions(quotes);
      } else {
        throw new Error("Search API failed");
      }
    } catch {
      // Fallback: match against local STOCK_DATABASE
      const upper = q.toUpperCase();
      const local = STOCK_DATABASE
        .filter(s => !existingTickers.includes(s.ticker) && (s.ticker.includes(upper) || s.name.toUpperCase().includes(upper)))
        .map(s => ({ ...s, exchange: "" }))
        .slice(0, 8);
      setLiveSuggestions(local);
    }
    setIsSearching(false);
  }, [existingTickers]);

  // Debounced search
  const handleInputChange = (val: string) => {
    setQuery(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => searchTickers(val), 250);
  };

  // Allow manual add by pressing Enter (for any ticker, even if not in suggestions)
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && query.trim()) {
      const ticker = query.trim().toUpperCase();
      if (existingTickers.includes(ticker)) return;
      // Check if it matches a suggestion
      const match = liveSuggestions.find(s => s.ticker === ticker);
      if (match) {
        onAddTicker(match.ticker, match.name, match.sector);
      } else {
        // Manual add — name will be the ticker, pipeline will enrich
        onAddTicker(ticker, ticker, "");
      }
      setQuery("");
      setLiveSuggestions([]);
    }
  };

  const showSuggestions = isFocused && (liveSuggestions.length > 0 || isSearching);

  return (
    <div className="relative">
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <input
            type="text"
            value={query}
            onChange={e => handleInputChange(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setTimeout(() => setIsFocused(false), 200)}
            placeholder="Search any ticker or company name to add..."
            className="w-full px-4 py-2.5 bg-[var(--bg-elevated)] border border-[var(--border)] rounded-lg text-sm text-[var(--text)] placeholder-[var(--muted)] outline-none focus:border-[var(--accent-muted)] transition-colors"
          />
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--muted)] text-xs">
            {isSearching ? "..." : "+"}
          </span>
        </div>
      </div>

      {/* Suggestions dropdown */}
      {showSuggestions && (
        <div className="absolute z-50 w-full mt-1 bg-[var(--card)] border border-[var(--border)] rounded-lg shadow-xl overflow-hidden">
          {isSearching && liveSuggestions.length === 0 && (
            <div className="px-4 py-3 text-xs text-[var(--muted)]">Searching...</div>
          )}
          {liveSuggestions.map(s => (
            <button
              key={s.ticker}
              onMouseDown={() => {
                onAddTicker(s.ticker, s.name, s.sector);
                setQuery("");
                setLiveSuggestions([]);
              }}
              className="w-full px-4 py-3 flex items-center gap-3 hover:bg-[var(--hover)] transition-colors text-left"
            >
              <span className="font-mono font-bold text-sm text-[var(--text)] min-w-[60px]">{s.ticker}</span>
              <div className="flex-1">
                <div className="text-xs text-[var(--secondary)]">{s.name}</div>
                <div className="text-[10px] text-[var(--muted)]">{s.sector}{s.exchange ? ` · ${s.exchange}` : ""}</div>
              </div>
            </button>
          ))}
          {query.trim() && !isSearching && (
            <button
              onMouseDown={() => {
                const ticker = query.trim().toUpperCase();
                if (!existingTickers.includes(ticker)) {
                  onAddTicker(ticker, ticker, "");
                  setQuery("");
                  setLiveSuggestions([]);
                }
              }}
              className="w-full px-4 py-2.5 flex items-center gap-2 border-t border-[var(--border)] hover:bg-[var(--hover)] transition-colors text-left"
            >
              <span className="text-xs text-[var(--accent-muted)]">+ Add</span>
              <span className="font-mono font-bold text-sm text-[var(--text)]">{query.trim().toUpperCase()}</span>
              <span className="text-[10px] text-[var(--muted)]">manually</span>
            </button>
          )}
        </div>
      )}
    </div>
  );
}
