import { NextResponse } from "next/server";
import { execFile } from "child_process";
import path from "path";

// Batch-fetch HQ locations using yfinance (Python, server-side).
// The Yahoo Finance v10 quoteSummary API requires crumb+cookie auth that
// is unreliable from Node.js fetch. yfinance handles auth internally.
//
// POST body: { tickers: ["AAPL", "AEHR", ...] }
// Returns: { locations: { "AAPL": { city, state, country }, ... } }

const TICKER_RE = /^[A-Z]{1,6}(\.[A-Z]{1,3})?$/;
function isValidTicker(t: string): boolean {
  return TICKER_RE.test(t);
}

const SCRIPTS_DIR = path.join(process.cwd(), "scripts");

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const tickers: string[] = (body.tickers || []).slice(0, 30);

    if (tickers.length === 0) {
      return NextResponse.json({ locations: {} });
    }

    // Validate each ticker against strict regex
    const safeTickers = tickers
      .map((t) => t.toUpperCase().replace(/[^A-Z0-9.]/g, ""))
      .filter((t) => isValidTicker(t));

    if (safeTickers.length === 0) {
      return NextResponse.json({ locations: {} });
    }

    const scriptPath = path.join(SCRIPTS_DIR, "fetch_locations.py");
    const args = [scriptPath, ...safeTickers];

    return new Promise<Response>((resolve) => {
      execFile("python", args, { cwd: process.cwd(), timeout: 60000 }, (error, stdout, stderr) => {
        if (error) {
          console.error("[Locations] Python error:", error.message);
          if (stderr) console.error("[Locations] stderr:", stderr.slice(-500));
          resolve(NextResponse.json({ locations: {} }));
          return;
        }

        try {
          const locations = JSON.parse(stdout.trim());
          resolve(NextResponse.json({ locations }));
        } catch {
          console.error("[Locations] Failed to parse Python output:", stdout.slice(0, 200));
          resolve(NextResponse.json({ locations: {} }));
        }
      });
    });
  } catch (e: any) {
    return NextResponse.json(
      { locations: {}, error: e.message },
      { status: 500 }
    );
  }
}
