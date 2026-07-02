from supabase_helper import get_client
sb = get_client()
rows = sb.table("prediction_log").select("id,ticker,created_at,current_price,target_low,target_base,target_high").order("created_at", desc=True).execute().data or []
bad = [r for r in rows if r.get("current_price") in (None, 0) or r.get("current_price")==0.0]
print(f"total seals: {len(rows)}  bad current_price (null/0): {len(bad)}")
for r in bad:
    print(f"  id={r['id']} {r['ticker']} created={r['created_at']} current_price={r['current_price']!r} base={r.get('target_base')!r}")
