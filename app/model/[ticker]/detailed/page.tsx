import DetailedModel from "./DetailedModel";

export const dynamic = "force-dynamic";

/**
 * /model/[ticker]/detailed
 *
 * Full institutional-grade spreadsheet view for a ticker:
 *   - P&L Summary with forecast
 *   - Income Statement (historical quarters + forecast)
 *   - Cash Flow
 *   - Valuation (EV/EBITDA × P/E blend, scenarios)
 *   - Capitalization
 *
 * All numbers are driven by the same target_engine.py that powers the brief
 * view and the Excel export — single source of truth.
 */
export default async function DetailedPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;
  return <DetailedModel ticker={ticker.toUpperCase()} />;
}
