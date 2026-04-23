import { NextResponse } from "next/server";

// Proxy Yahoo Finance autocomplete to avoid CORS issues in the browser
export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const q = searchParams.get("q") || "";

  if (!q || q.length < 1) {
    return NextResponse.json({ quotes: [] });
  }

  try {
    const resp = await fetch(
      `https://query1.finance.yahoo.com/v1/finance/search?q=${encodeURIComponent(q)}&quotesCount=10&newsCount=0&listsCount=0&enableFuzzyQuery=false`,
      {
        headers: {
          "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        },
        signal: AbortSignal.timeout(5000),
      }
    );

    if (!resp.ok) {
      throw new Error(`Yahoo API returned ${resp.status}`);
    }

    const data = await resp.json();
    const quotes = (data.quotes || [])
      .filter(
        (r: any) =>
          r.quoteType === "EQUITY" && r.symbol && !r.symbol.includes(".")
      )
      .map((r: any) => ({
        ticker: r.symbol,
        name: r.shortname || r.longname || r.symbol,
        sector: r.sector || r.industry || "",
        exchange: r.exchange || "",
      }))
      .slice(0, 10);

    return NextResponse.json({ quotes });
  } catch (e: any) {
    console.error("[Search] Yahoo Finance proxy error:", e.message);
    return NextResponse.json({ quotes: [], error: e.message }, { status: 502 });
  }
}
