import { NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";
import { execFile } from "child_process";
import path from "path";
import fs from "fs";

const SCRIPTS_DIR = path.join(process.cwd(), "scripts");

interface ProviderStatus {
  name: string;
  available: boolean;
  keySet: boolean;
}

interface TestResult {
  passed: number;
  failed: number;
  total: number;
  lastRun: string;
  details: string;
}

interface PipelineHealth {
  lastRunId: string | null;
  lastRunAt: string | null;
  lastRunSuccess: boolean | null;
  scoutSuccessRate: number | null;
  scoutDetails: Record<string, { success: boolean; duration_s: number; error?: string }>;
  modelGenMeta: Record<string, { tokens_used?: number; repair_attempts?: number; repair_method?: string }>;
}

/**
 * GET /api/health — Returns system health: data providers, test status, pipeline health
 */
export async function GET() {
  const [providers, tests, pipeline] = await Promise.all([
    getProviderStatus(),
    getTestStatus(),
    getPipelineHealth(),
  ]);

  return NextResponse.json({
    providers,
    tests,
    pipeline,
    timestamp: new Date().toISOString(),
  });
}

async function getProviderStatus(): Promise<ProviderStatus[]> {
  // Check which API keys are set by looking at .env presence
  // We don't expose the keys — just whether they're configured
  const envPath = path.join(process.cwd(), ".env");
  let envContent = "";
  try {
    envContent = fs.readFileSync(envPath, "utf-8");
  } catch {
    // .env might not exist in production
  }

  const hasKey = (name: string) => {
    const re = new RegExp(`^${name}=.+`, "m");
    return re.test(envContent);
  };

  return [
    { name: "EODHD", available: true, keySet: hasKey("EODHD_API_KEY") },
    { name: "yfinance", available: true, keySet: true }, // No key needed
    { name: "Alpha Vantage", available: true, keySet: hasKey("ALPHA_VANTAGE_API_KEY") },
    { name: "Perplexity", available: true, keySet: hasKey("PERPLEXITY_API_KEY") },
    { name: "Claude", available: true, keySet: hasKey("ANTHROPIC_API_KEY") },
    { name: "Gemini", available: true, keySet: hasKey("GEMINI_API_KEY") },
    { name: "Supabase", available: true, keySet: hasKey("SUPABASE_KEY") },
  ];
}

function getTestStatus(): Promise<TestResult> {
  return new Promise((resolve) => {
    const testFile = path.join(SCRIPTS_DIR, "test_engine.py");
    if (!fs.existsSync(testFile)) {
      resolve({ passed: 0, failed: 0, total: 0, lastRun: "", details: "test_engine.py not found" });
      return;
    }

    execFile(
      "python",
      ["-m", "pytest", testFile, "-q", "--tb=line", "--no-header"],
      { cwd: SCRIPTS_DIR, timeout: 30000 },
      (error, stdout, stderr) => {
        const output = stdout + "\n" + stderr;
        // Parse pytest summary line like "19 passed in 0.42s" or "2 failed, 17 passed in 0.55s"
        const passedMatch = output.match(/(\d+) passed/);
        const failedMatch = output.match(/(\d+) failed/);
        const passed = passedMatch ? parseInt(passedMatch[1]) : 0;
        const failed = failedMatch ? parseInt(failedMatch[1]) : (error ? -1 : 0);
        resolve({
          passed,
          failed: Math.max(0, failed),
          total: passed + Math.max(0, failed),
          lastRun: new Date().toISOString(),
          details: output.trim().split("\n").slice(-3).join("\n"),
        });
      }
    );
  });
}

async function getPipelineHealth(): Promise<PipelineHealth> {
  try {
    const { data: run } = await supabase
      .from("pipeline_runs")
      .select("run_id, started_at, completed_at, success, scout_details, stock_count, error, duration_s")
      .order("started_at", { ascending: false })
      .limit(1)
      .maybeSingle();

    if (!run) {
      return {
        lastRunId: null, lastRunAt: null, lastRunSuccess: null,
        scoutSuccessRate: null, scoutDetails: {}, modelGenMeta: {},
      };
    }

    // Parse scout_details JSONB for success rates
    const details = run.scout_details || {};
    const scoutEntries = Object.entries(details).filter(([k]) => k.startsWith("scout_"));
    const scoutSuccess = scoutEntries.filter(([, v]: any) => v?.success).length;
    const scoutTotal = scoutEntries.length;

    return {
      lastRunId: run.run_id,
      lastRunAt: run.completed_at || run.started_at,
      lastRunSuccess: run.success,
      scoutSuccessRate: scoutTotal > 0 ? scoutSuccess / scoutTotal : null,
      scoutDetails: details,
      modelGenMeta: details.model_gen || {},
    };
  } catch {
    return {
      lastRunId: null, lastRunAt: null, lastRunSuccess: null,
      scoutSuccessRate: null, scoutDetails: {}, modelGenMeta: {},
    };
  }
}
