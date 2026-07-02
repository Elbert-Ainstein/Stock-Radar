from datetime import datetime, timezone, timedelta
from supabase_helper import get_client
sb = get_client()
rows = sb.table("prediction_log").select("id,ticker,created_at,current_price,target_low,target_base,target_high").order("created_at", desc=True).execute().data or []
good = [r for r in rows if r.get("current_price") not in (None,0) and r.get("current_price")!=0.0]
today = datetime.now(timezone.utc).date()
print(f"WELL-FORMED seals: {len(good)} (today={today})")
for r in good:
    seal_date = datetime.fromisoformat(str(r['created_at']).replace('Z','+00:00')).date()
    ripe=[h for h in (30,60,90) if seal_date+timedelta(days=h)<=today]
    print(f"  id={r['id']} {r['ticker']} sealed={seal_date} cur={r['current_price']} low={r['target_low']} base={r['target_base']} high={r['target_high']} ripe_horizons={ripe}")
# also outcomes table count
oc = sb.table("prediction_outcomes").select("id", count="exact").execute()
print("existing prediction_outcomes rows:", oc.count)
