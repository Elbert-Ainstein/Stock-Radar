import { NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";
import Anthropic from "@anthropic-ai/sdk";
import { execFile } from "child_process";
import path from "path";
import fs from "fs";

const ANTHROPIC_API_KEY = process.env.ANTHROPIC_API_KEY || "";
const SCRIPTS_DIR = path.join(process.cwd(), "scripts");

// ─── Tool definitions for Claude ─────────────────────────────────────────────

const TOOLS: Anthropic.Tool[] = [
  {
    name: "run_scout",
    description:
      "Run a specific scout module for one or more tickers. Use this when the user asks for fresh signals, updated news, or wants to re-scan a stock. Available scouts: quant, news, catalyst, moat, fundamentals, youtube, social, insider, filings. Returns the scout's signal results.",
    input_schema: {
      type: "object" as const,
      properties: {
        scout: {
          type: "string",
          enum: ["quant", "news", "catalyst", "moat", "fundamentals", "youtube", "social", "insider", "filings"],
          description: "Which scout to run",
        },
        ticker: {
          type: "string",
          description: "Stock ticker to scan (e.g., 'MRVL'). If omitted, runs for all watchlist stocks.",
        },
      },
      required: ["scout"],
    },
  },
  {
    name: "regenerate_model",
    description:
      "Regenerate the target price model for a specific ticker. This re-runs the full model generation pipeline (Perplexity research + Claude analysis → structured valuation model). Use when the user wants updated price targets, or when scout signals have changed significantly. Takes 1-2 minutes per stock.",
    input_schema: {
      type: "object" as const,
      properties: {
        ticker: {
          type: "string",
          description: "Stock ticker to regenerate model for (e.g., 'LITE')",
        },
      },
      required: ["ticker"],
    },
  },
  {
    name: "what_if_scenario",
    description:
      "Run a what-if scenario by modifying target engine drivers and computing new price targets WITHOUT saving to the database. Use when the user asks hypothetical questions like 'What if WACC goes to 15%?' or 'What if revenue growth drops to 10%?'. Returns bear/base/bull targets under the modified assumptions.",
    input_schema: {
      type: "object" as const,
      properties: {
        ticker: {
          type: "string",
          description: "Stock ticker to run scenario for",
        },
        driver_overrides: {
          type: "object",
          description:
            "Driver overrides as key-value pairs. Valid keys: rev_growth_y1 (decimal, e.g. 0.30 for 30%), rev_growth_terminal, ebitda_margin_target, fcf_sbc_margin_target, ev_ebitda_multiple, ev_fcf_sbc_multiple, discount_rate (WACC), share_change_pct, sbc_pct_rev. Values are decimals (0.12 = 12%).",
          additionalProperties: { type: "number" },
        },
      },
      required: ["ticker", "driver_overrides"],
    },
  },
  {
    name: "search_stocks",
    description:
      "Search for stocks outside the current watchlist. Use when the user asks for recommendations of new stocks to add, or wants to explore a sector/theme. Returns basic info (ticker, name, sector, market cap) for matching stocks. The user can then choose to add any to their watchlist.",
    input_schema: {
      type: "object" as const,
      properties: {
        query: {
          type: "string",
          description: "Search query — can be a ticker, company name, sector, or theme (e.g., 'AI chips', 'semiconductor equipment', 'SMCI')",
        },
      },
      required: ["query"],
    },
  },
  {
    name: "add_to_watchlist",
    description:
      "Add a stock to the user's watchlist and trigger a mini-pipeline (quant scout + analyst + model generation). Use ONLY after you've recommended a stock and the user has confirmed they want to add it. The pipeline runs in the background and takes ~1-2 minutes.",
    input_schema: {
      type: "object" as const,
      properties: {
        ticker: { type: "string", description: "Stock ticker (e.g., 'SMCI')" },
        name: { type: "string", description: "Company name (e.g., 'Super Micro Computer')" },
        sector: { type: "string", description: "Sector (e.g., 'Technology')" },
      },
      required: ["ticker", "name", "sector"],
    },
  },
  {
    name: "get_portfolio_summary",
    description:
      "Get the current portfolio snapshot with all stocks, scores, signals, and targets. Use at the start of complex analysis to have fresh data. Already loaded in system context, but call this to refresh if the conversation is long.",
    input_schema: {
      type: "object" as const,
      properties: {},
    },
  },
];

// ─── Tool execution ──────────────────────────────────────────────────────────

function execPython(script: string, args: string[] = []): Promise<{ stdout: string; stderr: string; exitCode: number }> {
  return new Promise((resolve) => {
    execFile("python", [path.join(SCRIPTS_DIR, script), ...args], {
      cwd: process.cwd(),
      timeout: 180000,
      env: { ...process.env },
    }, (error, stdout, stderr) => {
      resolve({
        stdout: stdout?.slice(-3000) || "",
        stderr: stderr?.slice(-1000) || "",
        exitCode: error ? (error as any).code || 1 : 0,
      });
    });
  });
}

async function executeTool(name: string, input: any): Promise<string> {
  switch (name) {
    case "run_scout": {
      const scoutMap: Record<string, string> = {
        quant: "scout_quant.py", news: "scout_news.py", catalyst: "scout_catalyst.py",
        moat: "scout_moat.py", fundamentals: "scout_fundamentals.py", youtube: "scout_youtube.py",
        social: "scout_social.py", insider: "scout_insider.py", filings: "scout_filings.py",
      };
      const script = scoutMap[input.scout];
      if (!script) return JSON.stringify({ error: `Unknown scout: ${input.scout}` });

      const args = input.ticker ? ["--ticker", input.ticker.toUpperCase()] : [];
      const result = await execPython(script, args);

      // Also fetch updated signals from Supabase
      const ticker = input.ticker?.toUpperCase();
      if (ticker) {
        const { data: signals } = await supabase
          .from("latest_signals")
          .select("scout, signal, summary")
          .eq("ticker", ticker)
          .eq("scout", input.scout.charAt(0).toUpperCase() + input.scout.slice(1));
        return JSON.stringify({
          status: result.exitCode === 0 ? "success" : "error",
          scout: input.scout,
          ticker: ticker || "all",
          updated_signals: signals || [],
          output_tail: result.stdout.slice(-800),
        });
      }
      return JSON.stringify({ status: result.exitCode === 0 ? "success" : "error", output_tail: result.stdout.slice(-800) });
    }

    case "regenerate_model": {
      const ticker = input.ticker.toUpperCase();
      const result = await execPython("generate_model.py", ["--ticker", ticker]);

      // Fetch the updated model from Supabase
      const { data: stock } = await supabase
        .from("stocks")
        .select("scenarios, target_price, archetype")
        .eq("ticker", ticker)
        .maybeSingle();

      const scenarios = stock?.scenarios || {};
      return JSON.stringify({
        status: result.exitCode === 0 ? "success" : "error",
        ticker,
        new_targets: {
          base: scenarios.base?.price,
          bear: scenarios.bear?.price,
          bull: scenarios.bull?.price,
        },
        archetype: stock?.archetype,
        output_tail: result.stdout.slice(-500),
      });
    }

    case "what_if_scenario": {
      const ticker = input.ticker.toUpperCase();
      const overrides = input.driver_overrides || {};

      // Run the target engine with overrides via a small Python script
      const overridesJson = JSON.stringify(overrides);
      const pyCode = `
import sys, json
sys.path.insert(0, "${SCRIPTS_DIR.replace(/\\/g, "/")}")
from finance_data import fetch_financials
from target_engine import build_target, compute_smart_defaults

fin = fetch_financials("${ticker}")
result = build_target(fin)
drivers = dict(result.drivers)

# Apply overrides
overrides = json.loads('${overridesJson.replace(/'/g, "\\'")}')
for k, v in overrides.items():
    if k in drivers:
        drivers[k] = v

# Rebuild with overrides
from target_engine import _scenario_price, _annual_label_from_q, SCENARIO_OFFSETS, _discount_years_for_horizon
base_year = _annual_label_from_q(fin.latest_quarter_label() or "")
scenarios = {}
for name in ("downside", "base", "upside"):
    d = dict(drivers)
    offs = SCENARIO_OFFSETS[name]
    for key, mult in offs.items():
        base_key = key.replace("_mult", "").replace("_delta", "")
        if key.endswith("_mult") and base_key in d:
            d[base_key] = d[base_key] * mult
        elif key.endswith("_delta") and base_key in d:
            d[base_key] = d[base_key] + mult
    s = _scenario_price(fin, d, name, base_year)
    scenarios[name] = {"price": round(s.price, 2)}

original = {
    "base": round(result.base, 2),
    "bear": round(result.low, 2),
    "bull": round(result.high, 2),
}
print(json.dumps({"original": original, "what_if": scenarios, "overrides_applied": overrides, "current_price": result.current_price}))
`;
      const tmpFile = path.join(SCRIPTS_DIR, "_tmp_whatif.py");
      fs.writeFileSync(tmpFile, pyCode);
      try {
        const result = await execPython("_tmp_whatif.py");
        try { fs.unlinkSync(tmpFile); } catch {}

        if (result.exitCode !== 0) {
          return JSON.stringify({ error: "What-if scenario failed", details: result.stderr.slice(-300) });
        }
        // Parse the last JSON line from stdout
        const lines = result.stdout.trim().split("\n");
        const lastLine = lines[lines.length - 1];
        return lastLine;
      } catch (e: any) {
        try { fs.unlinkSync(tmpFile); } catch {}
        return JSON.stringify({ error: e.message });
      }
    }

    case "search_stocks": {
      // Search discovery candidates first, then Supabase stocks
      const query = input.query.toUpperCase();
      const results: any[] = [];

      // Check discovery candidates
      const { data: candidates } = await supabase
        .from("discovery_candidates")
        .select("ticker, name, sector, market_cap_b, score, thesis_summary")
        .or(`ticker.ilike.%${query}%,name.ilike.%${query}%,sector.ilike.%${query}%`)
        .limit(10);

      if (candidates?.length) {
        for (const c of candidates) {
          results.push({
            ticker: c.ticker, name: c.name, sector: c.sector,
            market_cap: c.market_cap_b ? `$${c.market_cap_b.toFixed(1)}B` : "?",
            discovery_score: c.score, thesis: c.thesis_summary?.slice(0, 150),
            source: "discovery",
          });
        }
      }

      // If few results, also try a general ticker lookup
      if (results.length < 5) {
        // Use the quant scout's ticker search as fallback
        const { data: existing } = await supabase
          .from("stocks")
          .select("ticker, name, sector")
          .or(`ticker.ilike.%${query}%,name.ilike.%${query}%`)
          .eq("active", true)
          .limit(5);

        for (const s of existing || []) {
          if (!results.find((r: any) => r.ticker === s.ticker)) {
            results.push({ ticker: s.ticker, name: s.name, sector: s.sector, source: "watchlist (already tracked)" });
          }
        }
      }

      return JSON.stringify({
        query: input.query,
        results,
        note: results.length === 0
          ? "No matches found in discovery universe or watchlist. Try a different query, or ask me to run the discovery scanner first."
          : `Found ${results.length} matches. To add any to your watchlist, just say 'Add [TICKER]'.`,
      });
    }

    case "add_to_watchlist": {
      const ticker = input.ticker.toUpperCase();

      // Check if already exists
      const { data: existing } = await supabase
        .from("stocks")
        .select("ticker")
        .eq("ticker", ticker)
        .eq("active", true)
        .maybeSingle();

      if (existing) {
        return JSON.stringify({ status: "already_exists", ticker, message: `${ticker} is already in your watchlist.` });
      }

      // Insert stock
      const { error: insertErr } = await supabase.from("stocks").upsert({
        ticker,
        name: input.name,
        sector: input.sector || "Unknown",
        thesis: "Added via Ask AI — pipeline running...",
        kill_condition: "TBD — will be generated after pipeline analysis",
        tags: [input.sector || "Unknown"],
        active: true,
      }, { onConflict: "ticker" });

      if (insertErr) {
        return JSON.stringify({ error: insertErr.message });
      }

      // Trigger mini-pipeline in background
      execFile("python", [path.join(SCRIPTS_DIR, "run_pipeline.py"), "--ticker", ticker], {
        cwd: process.cwd(),
        timeout: 180000,
      }, (err) => {
        if (err) console.error(`[ask] Mini-pipeline error for ${ticker}:`, err.message);
        else console.log(`[ask] Mini-pipeline completed for ${ticker}`);
      });

      return JSON.stringify({
        status: "added",
        ticker,
        name: input.name,
        message: `${ticker} (${input.name}) added to watchlist. Mini-pipeline is running — quant scout, analyst, and model generation will complete in ~1-2 minutes. Check the dashboard for results.`,
      });
    }

    case "get_portfolio_summary": {
      const ctx = await buildContext();
      return buildPortfolioSummaryText(ctx);
    }

    default:
      return JSON.stringify({ error: `Unknown tool: ${name}` });
  }
}

// ─── Main POST handler with agentic loop ─────────────────────────────────────

export async function POST(req: Request) {
  if (!ANTHROPIC_API_KEY) {
    return NextResponse.json(
      { error: "ANTHROPIC_API_KEY not configured. Add it to your .env file." },
      { status: 500 }
    );
  }

  const body = await req.json().catch(() => ({}));
  const question = body.question?.trim();
  if (!question) {
    return NextResponse.json({ error: "No question provided" }, { status: 400 });
  }
  const conversationHistory: { role: string; content: string }[] = body.conversationHistory || [];

  try {
    const context = await buildContext();
    const systemPrompt = buildSystemPrompt(context);

    // Build messages
    const messages: Anthropic.MessageParam[] = [];
    for (const msg of conversationHistory.slice(-10)) {
      messages.push({
        role: msg.role === "assistant" ? "assistant" : "user",
        content: msg.content,
      });
    }
    messages.push({ role: "user", content: question });

    const client = new Anthropic({ apiKey: ANTHROPIC_API_KEY });
    let totalTokens = 0;
    const actionsLog: { tool: string; input: any; result: string }[] = [];

    // ── Agentic loop: Claude calls tools, we execute, feed back results ──
    const MAX_ITERATIONS = 5;
    let currentMessages = [...messages];

    for (let i = 0; i < MAX_ITERATIONS; i++) {
      const response = await client.messages.create({
        model: "claude-sonnet-4-20250514",
        max_tokens: 4096,
        system: systemPrompt,
        tools: TOOLS,
        messages: currentMessages,
      });

      totalTokens += response.usage.input_tokens + response.usage.output_tokens;

      // If Claude wants to use tools
      if (response.stop_reason === "tool_use") {
        // Add assistant's response (with tool_use blocks) to messages
        currentMessages.push({ role: "assistant", content: response.content });

        // Execute each tool call
        const toolResults: Anthropic.ToolResultBlockParam[] = [];
        for (const block of response.content) {
          if (block.type === "tool_use") {
            console.log(`[ask] Executing tool: ${block.name}`, JSON.stringify(block.input).slice(0, 200));
            const result = await executeTool(block.name, block.input);
            actionsLog.push({ tool: block.name, input: block.input, result: result.slice(0, 500) });
            toolResults.push({
              type: "tool_result",
              tool_use_id: block.id,
              content: result,
            });
          }
        }

        // Feed tool results back to Claude
        currentMessages.push({ role: "user", content: toolResults });
        continue; // Next iteration — Claude will process results and either call more tools or respond
      }

      // Claude is done — extract final text response
      const answer = response.content
        .filter((b): b is Anthropic.TextBlock => b.type === "text")
        .map((b) => b.text)
        .join("\n") || "No response generated.";

      return NextResponse.json({
        answer,
        model: response.model,
        tokens_used: totalTokens,
        actions: actionsLog.length > 0 ? actionsLog : undefined,
      });
    }

    // If we hit max iterations, return what we have
    return NextResponse.json({
      answer: "I ran into my action limit for this question. Here's what I was able to do so far — please ask a follow-up to continue.",
      model: "claude-sonnet-4-20250514",
      tokens_used: totalTokens,
      actions: actionsLog,
    });
  } catch (err: any) {
    console.error("[ask] Error:", err.message);
    return NextResponse.json(
      { error: `Error: ${err.message?.slice(0, 200)}` },
      { status: 500 }
    );
  }
}

// ─── Context builder ─────────────────────────────────────────────────────────

interface PortfolioContext {
  stocks: any[];
  signals: any[];
  pipelineRun: any | null;
}

async function buildContext(): Promise<PortfolioContext> {
  const [stocksRes, signalsRes, pipelineRes] = await Promise.all([
    supabase.from("stocks").select("*").eq("active", true),
    supabase.from("latest_signals").select("*"),
    supabase
      .from("pipeline_runs")
      .select("run_id, started_at, completed_at, success, scout_details")
      .order("started_at", { ascending: false })
      .limit(1)
      .maybeSingle(),
  ]);

  return {
    stocks: stocksRes.data || [],
    signals: signalsRes.data || [],
    pipelineRun: pipelineRes.data,
  };
}

function buildPortfolioSummaryText(ctx: PortfolioContext): string {
  return ctx.stocks.map((s: any) => {
    const signals = ctx.signals.filter((sig: any) => sig.ticker === s.ticker);
    const bullish = signals.filter((sig: any) => sig.signal === "bullish").length;
    const bearish = signals.filter((sig: any) => sig.signal === "bearish").length;
    const scenarios = s.scenarios || {};
    const archetype = s.archetype ? (typeof s.archetype === "string" ? s.archetype : s.archetype.primary || "?") : "?";
    return `${s.ticker}: score=${s.composite_score || "?"}, signals=${bullish}B/${bearish}Be/${signals.length}T, archetype=${archetype}, base=$${scenarios.base?.price?.toFixed?.(0) ?? scenarios.base?.price ?? "?"}, kill=${s.kill_condition_eval?.status || "?"}`;
  }).join("\n");
}

function buildSystemPrompt(ctx: PortfolioContext): string {
  const stockSummaries = ctx.stocks.map((s: any) => {
    const signals = ctx.signals.filter((sig: any) => sig.ticker === s.ticker);
    const bullish = signals.filter((sig: any) => sig.signal === "bullish").length;
    const bearish = signals.filter((sig: any) => sig.signal === "bearish").length;
    const neutral = signals.filter((sig: any) => sig.signal === "neutral").length;

    const scenarios = s.scenarios || {};
    const defaults = s.model_defaults || {};
    const scenarioBase = scenarios.base;
    const scenarioDown = scenarios.bear;
    const scenarioUp = scenarios.bull;
    const archetype = s.archetype ? (typeof s.archetype === "string" ? s.archetype : s.archetype.primary || "unknown") : "unclassified";
    const killEval = s.kill_condition_eval;
    const killStatus = killEval ? `${killEval.status} (${killEval.reasoning?.slice(0, 80)})` : "not evaluated";

    const signalSummaries = signals
      .filter((sig: any) => sig.summary)
      .slice(0, 4)
      .map((sig: any) => `  - [${sig.scout}] ${sig.signal}: ${sig.summary.slice(0, 120)}`)
      .join("\n");

    return `### ${s.ticker} — ${s.name || ""}
Sector: ${s.sector || "N/A"} | Archetype: ${archetype}
Price: $${s.price_data?.price || "?"} | Market cap: ${s.price_data?.market_cap_b ? `$${s.price_data.market_cap_b.toFixed(1)}B` : "?"}
Composite score: ${s.composite_score || "?"}/100
Signal consensus: ${bullish}B / ${bearish}Be / ${neutral}N (${signals.length} total)
Thesis: ${s.thesis || "none"}
Kill condition: ${s.kill_condition || "none"} → Status: ${killStatus}
Targets: Base=${scenarioBase?.price ? `$${scenarioBase.price.toFixed(0)}` : "?"} | Bear=${scenarioDown?.price ? `$${scenarioDown.price.toFixed(0)}` : "?"} | Bull=${scenarioUp?.price ? `$${scenarioUp.price.toFixed(0)}` : "?"}
Drivers: rev=${defaults.revenue_b ? `$${defaults.revenue_b}B` : "?"}, margin=${defaults.op_margin ? (defaults.op_margin * 100).toFixed(0) + "%" : "?"}, PE=${defaults.pe_multiple || "?"}, PS=${defaults.ps_multiple || "n/a"}
Signals:
${signalSummaries || "  (no signals)"}`;
  });

  const lastRun = ctx.pipelineRun;
  const pipelineInfo = lastRun
    ? `Last pipeline: ${lastRun.completed_at || lastRun.started_at} | Success: ${lastRun.success}`
    : "No pipeline runs recorded.";

  return `You are the AI analyst agent for Stock Radar, an investment research platform. You have real-time access to the user's portfolio data AND you can take actions using tools.

## YOUR CAPABILITIES
1. **Buy/sell recommendations**: Rank stocks by conviction, explain the thesis, flag risks.
2. **Stock deep-dives**: Pull all signals, model targets, kill conditions, and catalysts into a narrative.
3. **Portfolio-level analysis**: Assess sector concentration, correlation risk, and diversification gaps.
4. **What-if scenarios**: Use the what_if_scenario tool to re-run the engine with modified drivers and show exact price impact.
5. **Run scouts**: Trigger specific scouts for fresh signal data when the user wants updated information.
6. **Regenerate models**: Re-run model generation when signals have changed or the user wants fresh targets.
7. **Discover & add stocks**: Search for new stocks, recommend additions, and add to watchlist with full pipeline.

## TOOL USAGE RULES
- For what-if questions ("what if rates go up"), ALWAYS use the what_if_scenario tool — don't estimate, compute it.
- For "run the news scout on X", use run_scout directly.
- For "add SMCI to my watchlist", use search_stocks first to get the correct name/sector, then add_to_watchlist.
- For recommendations of NEW stocks (not in watchlist), use search_stocks to find candidates from the discovery universe.
- When recommending a stock to add, present your recommendation first and WAIT for the user to confirm before calling add_to_watchlist.
- After running a tool, ALWAYS explain the results in plain language with specific numbers.

## ANALYSIS RULES
- Always cite specific data (scores, signals, targets) — never make up numbers.
- When recommending, explain WHY using the archetype framework (GARP, Cyclical, Compounder, Transformational, Special Situation).
- Flag any stock where kill_condition status is "warning" or "triggered".
- If a stock's model shows negative base-case upside, mention that explicitly.
- Be direct and opinionated — the user wants conviction-ranked insights, not hedged disclaimers.
- For macro what-if scenarios, walk through the transmission mechanism: macro change → sector impact → company-level driver → use what_if_scenario tool to compute exact target price change.
- Use $ values and percentages, not vague qualitative language.

## PORTFOLIO SNAPSHOT (${ctx.stocks.length} stocks)
${pipelineInfo}

${stockSummaries.join("\n\n")}

## PORTFOLIO STATISTICS
- Stocks tracked: ${ctx.stocks.length}
- Total signals: ${ctx.signals.length}
- Sectors: ${[...new Set(ctx.stocks.map((s: any) => s.sector).filter(Boolean))].join(", ") || "various"}`;
}
