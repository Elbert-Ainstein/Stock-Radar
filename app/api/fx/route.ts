import { NextRequest, NextResponse } from "next/server";

/**
 * GET /api/fx?from=EUR&to=USD
 *
 * Returns { rate: number, from: string, to: string, fetched_at: string }
 * Uses the free exchangerate.host API (no key required).
 * Caches rates for 1 hour to avoid excessive calls.
 */

// Simple in-memory cache: "EUR-USD" -> { rate, ts }
const cache: Record<string, { rate: number; ts: number }> = {};
const CACHE_TTL_MS = 60 * 60 * 1000; // 1 hour

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const from = (url.searchParams.get("from") || "USD").toUpperCase();
  const to = (url.searchParams.get("to") || "USD").toUpperCase();

  if (from === to) {
    return NextResponse.json({ rate: 1, from, to, fetched_at: new Date().toISOString() });
  }

  // Validate currency codes (3-letter alpha)
  if (!/^[A-Z]{3}$/.test(from) || !/^[A-Z]{3}$/.test(to)) {
    return NextResponse.json({ error: "invalid currency code" }, { status: 400 });
  }

  const cacheKey = `${from}-${to}`;
  const cached = cache[cacheKey];
  if (cached && Date.now() - cached.ts < CACHE_TTL_MS) {
    return NextResponse.json({ rate: cached.rate, from, to, fetched_at: new Date(cached.ts).toISOString(), cached: true });
  }

  // Try multiple free APIs with fallback
  let rate: number | null = null;

  // Attempt 1: exchangerate.host (free, no key)
  try {
    const resp = await fetch(
      `https://api.exchangerate.host/convert?from=${from}&to=${to}&amount=1`,
      { signal: AbortSignal.timeout(5000) }
    );
    const data = await resp.json();
    if (data.result && typeof data.result === "number" && data.result > 0) {
      rate = data.result;
    }
  } catch { /* fall through */ }

  // Attempt 2: open.er-api.com (free, no key)
  if (!rate) {
    try {
      const resp = await fetch(
        `https://open.er-api.com/v6/latest/${from}`,
        { signal: AbortSignal.timeout(5000) }
      );
      const data = await resp.json();
      if (data.result === "success" && data.rates?.[to]) {
        rate = data.rates[to];
      }
    } catch { /* fall through */ }
  }

  if (!rate) {
    return NextResponse.json({ error: "unable to fetch exchange rate", from, to }, { status: 502 });
  }

  // Cache it
  cache[cacheKey] = { rate, ts: Date.now() };

  return NextResponse.json({ rate, from, to, fetched_at: new Date().toISOString() });
}
