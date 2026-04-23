// ─── Helpers ───

export function cn(...classes: (string | false | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

export function signalColor(s: string) {
  if (s === "bullish") return "text-[var(--success)]";
  if (s === "bearish") return "text-[var(--danger)]";
  return "text-[var(--secondary)]";
}

export function signalBg(s: string) {
  if (s === "bullish") return "bg-emerald-400/10 border-emerald-400/20";
  if (s === "bearish") return "bg-rose-400/10 border-rose-400/20";
  return "bg-gray-400/10 border-gray-400/20";
}

export function signalIcon(s: string) {
  if (s === "bullish") return "▲";
  if (s === "bearish") return "▼";
  return "●";
}

export function aiColor(ai: string) {
  const map: Record<string, string> = {
    Gemini: "#4285f4", Perplexity: "#20b2aa", Grok: "#e040e0",
    Claude: "#a78bfa", ChatGPT: "#74aa9c", Script: "#888",
  };
  return map[ai] || "#888";
}

export function scoreColor(score: number) {
  if (score >= 8) return "text-[var(--success)]";
  if (score >= 6) return "text-amber-400";
  return "text-[var(--danger)]";
}

export function scoreBg(score: number) {
  if (score >= 8) return "bg-[var(--success)]";
  if (score >= 6) return "bg-amber-400";
  return "bg-[var(--danger)]";
}

export function formatTime(iso: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-US", {
      month: "short", day: "numeric", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}
