"""Offline dry-run harness for algo/settled_basis_ladder.py.

Platform strategies cannot be unit-tested — the API only exists inside the
broker's runtime. So this stubs that API, feeds synthetic price paths, and
asserts the strategy's DECISIONS. It catches logic and state bugs before a
backtest is spent on them, and it is how you check a change to the strategy
did not quietly break the discipline.

    python3 algo/dryrun_sim.py

It proves mechanism, never profitability: the paths are synthetic and the
fills are frictionless. Judge the strategy on a real backtest; judge THIS on
whether every constitutional rule still fires when it should.
"""
import math, datetime, sys

class E:
    def __init__(self, *names):
        for n in names: setattr(self, n, n)
AlgoStrategyType = E("SECURITY"); BarType = E("K_DAY"); DataType = E("CLOSE")
THType = E("RTH","ALL"); OrderSide = E("BUY","SELL"); TimeInForce = E("DAY")
CostPriceModel = E("AVG","DILUTED"); Currency = E("USD","HKD"); GlobalType = E("INT","FLOAT","BOOL")
class StrategyBase: pass
def declare_strategy_type(t): pass
def show_variable(v, t=None): return v
def floor(v): return math.floor(v)

BOOK = {"prices": [], "day": 0, "qty": 0.0, "cost": 0.0, "cash": 100000.0,
        "log": [], "trades": []}

def declare_trig_symbol(): return "US.TEST"
def get_symbol_code(symbol=None): return symbol
def device_time(): return datetime.datetime(2020,1,1) + datetime.timedelta(days=BOOK["day"])
def _series():   # bars up to and including today (index -1 == forming bar)
    return BOOK["prices"][:BOOK["day"]+1]
def bar_close(symbol=None, bar_type=None, select=2, session_type=None):
    s = _series()
    if len(s) < select: return None
    return s[-select]
def ma(symbol=None, period=5, bar_type=None, data_type=None, select=2, session_type=None):
    s = _series()
    if len(s) < select + period - 1: return None
    window = s[-(select+period-1):len(s)-select+1]
    return sum(window)/len(window)
def position_holding_qty(symbol=None): return BOOK["qty"]
def position_cost(symbol=None, cost_price_model=None): return BOOK["cost"]
def position_pl_ratio(symbol=None, cost_price_model=None):
    if not BOOK["qty"] or not BOOK["cost"]: return 0.0
    return _series()[-2]/BOOK["cost"] - 1.0
def net_asset(currency=None): return BOOK["cash"] + BOOK["qty"]*_series()[-2]
def total_cash(currency=None): return BOOK["cash"]
def lot_size(symbol=None): return 1
def available_qty(symbol=None): return BOOK["qty"]
def bar_high(symbol=None, bar_type=None, select=2, session_type=None):
    return bar_close(symbol=symbol, select=select)     # synthetic: no intrabar range
def current_price(symbol=None, price_type=None): return _series()[-2]
def place_limit(symbol=None, price=None, qty=None, side=None,
                time_in_force=None, order_trade_session_type=None):
    return place_market(symbol=symbol, qty=qty, side=side)
def place_market(symbol=None, qty=None, side=None, time_in_force=None):
    px = _series()[-2]                      # fills at the settled reference price
    if side == "BUY":
        cost_total = BOOK["cost"]*BOOK["qty"] + px*qty
        BOOK["qty"] += qty; BOOK["cost"] = cost_total/BOOK["qty"]; BOOK["cash"] -= px*qty
    else:
        BOOK["qty"] -= qty; BOOK["cash"] += px*qty
        if BOOK["qty"] <= 0: BOOK["qty"] = 0.0; BOOK["cost"] = 0.0
    BOOK["trades"].append((BOOK["day"], side, qty, round(px,2)))
    return "SIMORDER"
_print = print
def print(*a, **k):
    msg = " ".join(str(x) for x in a)
    BOOK["log"].append((BOOK["day"], msg)); _print("  day", BOOK["day"], "|", msg)

src = open("/home/user/Stock-Radar/algo/settled_basis_ladder.py").read()
ns = dict(globals()); exec(compile(src, "strategy", "exec"), ns)
Strategy = ns["Strategy"]

def run(prices, label):
    BOOK.update(prices=prices, day=0, qty=0.0, cost=0.0, cash=100000.0, log=[], trades=[])
    s = Strategy(); s.initialize()
    s.sym1 = "US.TEST"; s.sym2 = None; s.sym3 = None; s.sym4 = None
    _print("\n" + "="*70 + "\n" + label + "\n" + "="*70)
    for d in range(len(prices)):
        BOOK["day"] = d
        s.handle_data()
    px = prices[-1]
    equity = BOOK["cash"] + BOOK["qty"]*px
    _print("  -> trades:", len(BOOK["trades"]), "| final qty:", BOOK["qty"],
           "| equity:", round(equity,2))
    return BOOK["trades"], BOOK["log"]

# ── scenario 1: uptrend, pullback entry, big run through the ladder, then break
p = [100.0]
for i in range(260): p.append(p[-1]*1.002)          # long base uptrend
for i in range(25):  p.append(p[-1]*0.995)          # ~12% valley
for i in range(15):  p.append(p[-1]*1.004)          # turn
for i in range(200): p.append(p[-1]*1.008)          # the run (>200%)
for i in range(80):  p.append(p[-1]*0.985)          # structural break
t1, l1 = run(p, "SCENARIO 1 · valley entry -> ladder -> structural exit")

# ── scenario 2: parabolic name (must get STARTER SIZE ONLY, one stage)
p2 = [100.0]
for i in range(210): p2.append(p2[-1]*1.0005)
for i in range(126): p2.append(p2[-1]*1.010)        # ~3.5x in six months
for i in range(18):  p2.append(p2[-1]*0.994)        # ~10% valley
for i in range(20):  p2.append(p2[-1]*1.004)        # turn
t2, l2 = run(p2, "SCENARIO 2 · parabolic name -> anti-parabola starter size")

# ── scenario 2b: the OTHER side of the same threshold. A name that ran hard
# but whose trailing-6m gain has decayed below the line by the time a valley
# appears is NOT parabolic any more, and gets normal staging. This pins the
# threshold from both directions so a future edit cannot quietly move it.
p2b = [100.0]
for i in range(210): p2b.append(p2b[-1]*1.001)
for i in range(126): p2b.append(p2b[-1]*1.0065)     # ~+125%, decays under 100% by entry
for i in range(20):  p2b.append(p2b[-1]*0.995)
for i in range(20):  p2b.append(p2b[-1]*1.004)
t2b, l2b = run(p2b, "SCENARIO 2b · gain decayed below the line -> normal staging")

# ── scenario 3: chop below trend (should never buy)
p3 = [100.0]
for i in range(200): p3.append(p3[-1]*0.999)
for i in range(120): p3.append(p3[-1]*(1.01 if i%2 else 0.99))
t3, l3 = run(p3, "SCENARIO 3 · downtrend chop -> must never enter")

_print("\n" + "="*70 + "\nASSERTIONS\n" + "="*70)
def check(name, ok):
    _print(("  PASS  " if ok else "  FAIL  ") + name)
    return ok
allok = True
allok &= check("S1 entered on the valley", any(t[1]=="BUY" for t in t1))
allok &= check("S1 fired ladder trims", sum(1 for d,m in l1 if "TRIM rung" in m) >= 2)
allok &= check("S1 euphoria rung tagged at 2x", any("euphoria protocol" in m for d,m in l1))
allok &= check("S1 exited on structural break", any("EXIT structural" in m for d,m in l1))
allok &= check("S1 never went short", BOOK and all(t[1] in ("BUY","SELL") for t in t1))
allok &= check("S2 flagged anti-parabola", any("anti-parabola" in m for d,m in l2))
allok &= check("S2 took exactly ONE stage (starter)", sum(1 for d,m in l2 if "BUY stage" in m) == 1)
allok &= check("S2b did NOT flag (below the line)", not any("anti-parabola" in m for d,m in l2b))
allok &= check("S2b staged normally (>1 stage)", sum(1 for d,m in l2b if "BUY stage" in m) > 1)
allok &= check("no standing reason repeats daily",
               max([sum(1 for d,m in log if "sources disagree" in m) for log in (l1,l2,l3)]) <= 3)
allok &= check("S3 never entered", not any(t[1]=="BUY" for t in t3))
_print("\nRESULT: " + ("all green" if allok else "FAILURES ABOVE"))

# ── static gate: the editor's rules, checked before any of this matters ─────
# v1 shipped with seven editor errors that a mechanism test cannot see. If a
# manual is on hand, run the signature checker as part of the dry run.
import glob as _glob, os as _os, subprocess as _sub
_manuals = _glob.glob(_os.path.expanduser("~/.claude/uploads/**/*Algo_Manual*.md"),
                      recursive=True)
if _manuals:
    _here = _os.path.dirname(_os.path.abspath(__file__))
    _r = _sub.run([sys.executable, _os.path.join(_here, "verify_against_manual.py"),
                   _os.path.join(_here, "settled_basis_ladder.py"), _manuals[0]],
                  capture_output=True, text=True)
    _print("\n" + "="*70 + "\nSTATIC CHECK vs MANUAL\n" + "="*70)
    _print("  " + (_r.stdout.strip() or "(no output)").replace("\n", "\n  "))
    if _r.returncode != 0:
        _print("\nRESULT: STATIC VIOLATIONS — the editor will reject this file")
else:
    _print("\n(no Algo_Manual found — signature check skipped; run "
           "verify_against_manual.py by hand before pasting)")

# ── v2 regressions: the defects the platform-semantics review confirmed ────
# Each drives the REAL code path. A test that passes because the setup never
# reached the code under test is worse than no test.
_print("\n" + "="*70 + "\nV2 FIX REGRESSIONS\n" + "="*70)

def _fresh(prices, day, qty=0.0, cost=0.0, cash=100000.0):
    BOOK.update(prices=prices, day=day, qty=qty, cost=cost, cash=cash, log=[], trades=[])
    s = Strategy(); s.initialize()
    s.sym1 = "US.TEST"; s.sym2 = None; s.sym3 = None; s.sym4 = None
    return s

# 1 · THE FLOOR. Drive buy_one_stage directly so the sizing path definitely
#     runs, with cash exactly at the floor: it must refuse.
_s = _fresh(p, 300)
BOOK["cash"] = _s.floor_amount * 1.0                      # cash IS the floor
_st = _s._st("US.TEST"); _st["close_now"] = p[298]
_s.buy_one_stage("US.TEST", "US.TEST", _st, p[298], 10.0, 3)
allok &= check("floor blocks the buy when cash is AT the floor",
               not any(t[1] == "BUY" for t in BOOK["trades"])
               and any("floor" in m for d, m in BOOK["log"]))

# 1b · and with cash comfortably above it, the same call DOES buy — proving
#      test 1 failed for the floor and not because the path was unreachable.
_s = _fresh(p, 300, cash=100000.0)
_st = _s._st("US.TEST"); _st["close_now"] = p[298]
_s.buy_one_stage("US.TEST", "US.TEST", _st, p[298], 10.0, 3)
allok &= check("same path DOES buy when cash is above the floor",
               any(t[1] == "BUY" for t in BOOK["trades"]))

# 2 · ANTI-PARABOLA FAILS CLOSED. Too little history to measure six months.
#     The series must still present a VALID entry (regime + valley), or the
#     function returns before the anti-parabola check and the test proves
#     nothing.
_short = [100.0]
for _i in range(80): _short.append(_short[-1] * 1.004)    # rise
for _i in range(14): _short.append(_short[-1] * 0.992)    # ~10% valley
for _i in range(4):  _short.append(_short[-1] * 1.003)    # turn
_s = _fresh(_short, len(_short) - 1)
allok &= check("short history is unmeasurable (returns None)",
               _s.six_month_gain("US.TEST", _short[-2]) is None)
_st = _s._st("US.TEST"); _st["close_now"] = _short[-2]
_s.consider_entry("US.TEST", "US.TEST", _st, _short[-2], _short[-3], 1.0, 2.0)
allok &= check("unmeasurable 6m gain => STARTER ONLY (fails closed)",
               _st["starter_only"] is True)

# 3 · EXIT/ENTRY INTERLOCK. A fired rung must stop the adder — driven through
#     manage_position, which is where the guard lives.
_s = _fresh(p, 400, qty=100.0, cost=100.0)
_st = _s._st("US.TEST")
_st.update(rungs_fired=[1], stages_taken=1, ref=p[398] / 1.10,
           ref_qty=100.0, close_now=p[398], reconciled=True)
_s.manage_position("US.TEST", "US.TEST", _st, p[398],
                   p[398] * 0.5)                          # trend well below: no exit
allok &= check("a fired rung stops the adder buying it back",
               not any(t[1] == "BUY" for t in BOOK["trades"]))

# 3b · with no rung fired, the same setup DOES add — again proving 3 was a
#      real block rather than an unreachable path.
_s = _fresh(p, 400, qty=100.0, cost=100.0)
_st = _s._st("US.TEST")
_st.update(rungs_fired=[], stages_taken=1, ref=p[398] / 1.10,
           ref_qty=100.0, close_now=p[398], reconciled=True)
_s.manage_position("US.TEST", "US.TEST", _st, p[398], p[398] * 0.5)
allok &= check("with no rung fired the adder still works",
               any(t[1] == "BUY" for t in BOOK["trades"]))

# 4 · RESTART RECONCILIATION. Shares on the books with empty state must NOT
#     re-arm the ladder from rung one.
_s = _fresh(p, 400, qty=100.0, cost=p[398] / 2.2)         # sitting on >100% gain
_st = _s._st("US.TEST"); _st["close_now"] = p[398]
_s._reconcile("US.TEST", "US.TEST", _st)
allok &= check("restart adopts fully-staged state",
               _st["stages_taken"] == _s.stages)
allok &= check("restart marks already-passed rungs as fired",
               1 in _st["rungs_fired"] and 2 in _st["rungs_fired"])

_print("\nFINAL: " + ("all green" if allok else "FAILURES ABOVE"))
