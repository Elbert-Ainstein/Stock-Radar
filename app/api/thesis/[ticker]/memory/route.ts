import { NextRequest, NextResponse } from "next/server";
import { readFile } from "fs/promises";
import path from "path";

const TICKER_RE = /^[A-Z0-9]{1,6}(\.[A-Z]{1,3})?$/;
const MEMORY_DIR = path.join(process.cwd(), "data", "memory");

/**
 * GET /api/thesis/[ticker]/memory
 *
 * Returns the per-ticker memory document from data/memory/{TICKER}.md.
 * Previously shelled out to python via execFile (lib/memory.py). That broke
 * on Windows because the Next dev server's PATH may not resolve "python".
 * Memory reads are just a file fetch with "." -> "_" ticker normalization,
 * so they're inlined here.
 */
function normalizeTicker(t: string): string {
  return t.toUpperCase().replace(/\./g, "_");
}

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker: rawTicker } = await params;
  const ticker = rawTicker.toUpperCase().replace(/[^A-Z0-9.]/g, "");
  if (!ticker || !TICKER_RE.test(ticker)) {
    return NextResponse.json({ error: "invalid ticker" }, { status: 400 });
  }

  const filename = `${normalizeTicker(ticker)}.md`;
  const filepath = path.join(MEMORY_DIR, filename);

  try {
    const md = await readFile(filepath, "utf-8");
    return NextResponse.json({ ticker, exists: md.length > 0, markdown: md });
  } catch (e: unknown) {
    const errno = (e as { code?: string })?.code;
    if (errno === "ENOENT") {
      return NextResponse.json({ ticker, exists: false, markdown: "" });
    }
    const m = e instanceof Error ? e.message : String(e);
    return NextResponse.json(
      { error: "read failed", detail: m, path: filepath },
      { status: 500 }
    );
  }
}
