"use client";

import { useEffect, useState } from "react";
import type { Stock } from "@/lib/data";
import StockDetail from "@/app/dashboard/StockDetail";

export default function StockDetailPage({
  stock,
  meta,
}: {
  stock: Stock;
  meta: { generatedAt: string };
}) {
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  useEffect(() => {
    const saved = typeof window !== "undefined" ? localStorage.getItem("sr-theme") : null;
    if (saved === "light") {
      setTheme("light");
      document.documentElement.setAttribute("data-theme", "light");
    }
  }, []);
  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    if (next === "light") document.documentElement.setAttribute("data-theme", "light");
    else document.documentElement.removeAttribute("data-theme");
    localStorage.setItem("sr-theme", next);
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--sr-paper)", color: "var(--sr-ink)" }}>

      {/* Main detail content */}
      <main className="max-w-[1400px] mx-auto" style={{ padding: "20px 18px" }}>
        <StockDetail stock={stock} onDelete={() => {
          // From a full page, deleting redirects back to watchlist after the API call.
          if (typeof window === "undefined") return;
          if (!confirm(`Remove ${stock.ticker} from watchlist?`)) return;
          fetch("/api/stocks/delete", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tickers: [stock.ticker] }),
          }).then(() => { window.location.href = "/"; });
        }} />
      </main>
    </div>
  );
}
