import { loadStocksForModel, loadMeta } from "@/lib/data";
import TargetPriceModel from "./TargetPriceModel";

export const dynamic = "force-dynamic";

export default async function ModelPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await searchParams;
  const initialTicker = typeof params.ticker === "string" ? params.ticker : undefined;

  const [stocksData, meta] = await Promise.all([loadStocksForModel(), loadMeta()]);

  return <TargetPriceModel stocks={stocksData} meta={meta} initialTicker={initialTicker} />;
}
