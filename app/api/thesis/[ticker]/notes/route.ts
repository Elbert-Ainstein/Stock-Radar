import { NextRequest, NextResponse } from "next/server";
import { execFile } from "child_process";
import path from "path";
import fs from "fs";
import { promisify } from "util";

const execFileP = promisify(execFile);

// Allow letters AND digits for HK tickers like 6082.HK
const TICKER_RE = /^[A-Z0-9]{1,6}(\.[A-Z]{1,3})?$/;
function isValidTicker(t: string): boolean {
  return TICKER_RE.test(t);
}

const SCRIPTS_DIR = path.join(process.cwd(), "scripts");
const DATA_DIR = path.join(process.cwd(), "data");
const ARCHIVE_DIR = path.join(DATA_DIR, "memory", "_archive");

// Per-ticker thesis-rerun lockfile (matches /api/thesis/[ticker]/rerun pattern).
// If a thesis run is in flight, we don't write to memory.md to avoid clobbering
// Sonnet's maintenance pass.
function thesisLockPath(ticker: string): string {
  return path.join(DATA_DIR, `.thesis-running-${ticker.replace(/\./g, "_")}`);
}
const STALE_LOCK_MS = 10 * 60 * 1000;
function isLockStale(lf: string): boolean {
  try {
    if (!fs.existsSync(lf)) return false;
    return Date.now() - fs.statSync(lf).mtimeMs > STALE_LOCK_MS;
  } catch {
    return false;
  }
}

const NOTES_MAX_CHARS = 8000; // ~2000 tokens — generous for personal notes

// Inline Python script to call memory helpers without spawning a runner.
// Reads/writes via lib.memory.{get_hume_notes_only, set_hume_notes}.
function pyCommand(action: "get" | "set", ticker: string, body: string = ""): string[] {
  // We pass the body via stdin (avoids shell quoting hell with multi-line markdown)
  return [
    "-c",
    `
import sys, os
sys.path.insert(0, ${JSON.stringify(SCRIPTS_DIR)})
from lib.memory import get_hume_notes_only, set_hume_notes
action = ${JSON.stringify(action)}
ticker = ${JSON.stringify(ticker)}
if action == "get":
    print(get_hume_notes_only(ticker), end="")
elif action == "set":
    body = sys.stdin.read()
    p = set_hume_notes(ticker, body)
    print(str(p), end="")
`,
  ];
}

async function pyExec(action: "get" | "set", ticker: string, body: string = ""): Promise<string> {
  const child = execFile("python", pyCommand(action, ticker), { cwd: process.cwd(), timeout: 10_000 });
  if (action === "set" && child.stdin) {
    child.stdin.write(body);
    child.stdin.end();
  }
  const out: string = await new Promise((resolve, reject) => {
    let stdout = "";
    let stderr = "";
    child.stdout?.on("data", (d) => (stdout += d));
    child.stderr?.on("data", (d) => (stderr += d));
    child.on("close", (code) => {
      if (code === 0) resolve(stdout);
      else reject(new Error(`python exited ${code}: ${stderr.slice(0, 500)}`));
    });
    child.on("error", reject);
  });
  return out;
}

/**
 * GET /api/thesis/[ticker]/notes
 *
 * Returns { ticker, notes: string } — the BODY of the `## Hume Notes`
 * section in data/memory/{TICKER}.md (without the heading), or empty
 * string if no notes exist for this ticker.
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker: rawTicker } = await params;
  const ticker = rawTicker.toUpperCase().replace(/[^A-Z0-9.]/g, "");
  if (!ticker || !isValidTicker(ticker)) {
    return NextResponse.json({ error: "invalid ticker" }, { status: 400 });
  }

  try {
    const notes = await pyExec("get", ticker);
    return NextResponse.json({ ticker, notes });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error(`[notes GET ${ticker}] ${msg}`);
    return NextResponse.json({ error: "read failed", detail: msg }, { status: 500 });
  }
}

/**
 * PUT /api/thesis/[ticker]/notes
 *
 * Body: { notes: string }  (markdown, max 8000 chars)
 *
 * Writes/replaces the `## Hume Notes` section of data/memory/{TICKER}.md
 * atomically. Empty body removes the section.
 *
 * Returns 409 if a thesis run is in flight for this ticker (avoids
 * clobbering Sonnet's maintenance pass).
 */
export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker: rawTicker } = await params;
  const ticker = rawTicker.toUpperCase().replace(/[^A-Z0-9.]/g, "");
  if (!ticker || !isValidTicker(ticker)) {
    return NextResponse.json({ error: "invalid ticker" }, { status: 400 });
  }

  // Lock check: if thesis run is in flight, refuse to avoid race with
  // Sonnet's maintenance write.
  const lf = thesisLockPath(ticker);
  if (fs.existsSync(lf) && !isLockStale(lf)) {
    return NextResponse.json(
      {
        error: "thesis run in flight",
        message: `Cannot save notes while thesis is being regenerated for ${ticker}. Try again in 60-120s.`,
        retry_after_seconds: 60,
      },
      { status: 409, headers: { "Retry-After": "60" } }
    );
  }

  let notesBody: string;
  try {
    const body = await req.json();
    if (!body || typeof body.notes !== "string") {
      return NextResponse.json(
        { error: "body must be { notes: string }" },
        { status: 400 }
      );
    }
    notesBody = body.notes;
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  if (notesBody.length > NOTES_MAX_CHARS) {
    return NextResponse.json(
      {
        error: "notes too long",
        message: `Notes exceeded ${NOTES_MAX_CHARS} chars. Trim and retry.`,
        current_chars: notesBody.length,
        max_chars: NOTES_MAX_CHARS,
      },
      { status: 413 }
    );
  }

  try {
    const path_written = await pyExec("set", ticker, notesBody);

    // Re-read the saved body so the client gets EXACTLY what's on disk —
    // including any sanitization the Python helper applied (e.g., `## ` ->
    // `### ` for section-break protection). Without this round-trip, the
    // editor's `dirty` flag would stay falsely-set after every save that
    // involved a sanitization.
    let savedBody: string;
    try {
      savedBody = await pyExec("get", ticker);
    } catch {
      // Best-effort: if the read-back fails, return the original body so
      // the client at least has something to compare against.
      savedBody = notesBody;
    }

    // Append a one-line audit entry (size, action, timestamp — not the content).
    // Use the post-sanitize savedBody.length so the trail matches disk reality.
    try {
      fs.mkdirSync(ARCHIVE_DIR, { recursive: true });
      const auditFile = path.join(ARCHIVE_DIR, `${ticker.replace(/\./g, "_")}_notes_history.jsonl`);
      const action = notesBody.trim() === "" ? "delete" : "replace";
      const entry = JSON.stringify({
        ts: new Date().toISOString(),
        ticker,
        action,
        notes_chars: savedBody.length,
      });
      fs.appendFileSync(auditFile, entry + "\n", "utf-8");
    } catch (auditErr) {
      const m = auditErr instanceof Error ? auditErr.message : String(auditErr);
      console.warn(`[notes PUT ${ticker}] audit append failed: ${m}`);
    }

    return NextResponse.json({
      success: true,
      ticker,
      chars: savedBody.length,
      path: path_written,
      notes: savedBody,  // post-sanitize body — client uses this to update its serverNotes cache
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error(`[notes PUT ${ticker}] ${msg}`);
    return NextResponse.json({ error: "write failed", detail: msg }, { status: 500 });
  }
}
