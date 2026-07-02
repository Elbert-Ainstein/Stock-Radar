import sys; sys.argv=['x']
from datetime import datetime, timezone
import run_checkpoint as rc
from checkpoint_seal import close_on_or_after
from supabase_helper import get_client

today = datetime.now(timezone.utc).date()
sb = get_client()
seals = rc._load_seals(sb, None)
for s in seals:
    for h, target in rc.ripe_horizons(s.get("created_at"), today, rc.HORIZONS):
        series = rc.fetch_close_series(s["ticker"], target)
        pick = close_on_or_after(series, target)
        if pick is None:
            continue
        price, date_used = pick
        if price is None or not isinstance(price,(int,float)):
            print("BAD PICK:", s["ticker"], "id",s["id"],"T+",h,"target",target,"pick",pick,"series_head",series[:3])
            sys.exit(0)
print("no bad pick found in scan")
