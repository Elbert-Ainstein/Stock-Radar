import { loadStocks, loadMeta } from "@/lib/data";
import StockDetailPage from "./StockDetailPage";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function Page({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker: rawTicker } = await params;
  const ticker = decodeURIComponent(rawTicker).toUpperCase();
  const [stocks, meta] = await Promise.all([loadStocks(), loadMeta()]);
  const stock = stocks.find(s => s.ticker.toUpperCase() === ticker);
  if (!stock) return notFound();
  return <StockDetailPage stock={stock} meta={meta} />;
}
