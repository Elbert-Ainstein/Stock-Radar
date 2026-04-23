import { loadStocks, loadMeta } from "@/lib/data";
import Dashboard from "./dashboard/Dashboard";

export const dynamic = "force-dynamic";

export default async function Page() {
  const [stocks, meta] = await Promise.all([loadStocks(), loadMeta()]);
  return <Dashboard stocks={stocks} meta={meta} />;
}
