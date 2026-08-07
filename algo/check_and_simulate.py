#!/usr/bin/env python3
"""Offline gate for algo/settled_basis_ladder.py — lint it, then run it.

    python3 algo/check_and_simulate.py [<Algo_Manual.md>]

THIS FILE IS NEVER PASTED ANYWHERE. It exists because the strategy editor is
strict in ways a normal Python linter is not, and because platform strategies
cannot be unit-tested — the broker API only exists inside its runtime. So this
stubs the API, feeds synthetic price paths, and asserts the strategy's
DECISIONS.

EVERY RULE BELOW WAS LEARNED FROM A REJECTION. In order:

  round(x, 2)                 -> the platform's round() takes ONE argument
  min(x, total_cash(...) or 0)-> min() type-checks float; the `or 0` is an int
  max([...])                  -> min/max REQUIRE two arguments; no iterable form
  top-level try/except, if     -> "You can only write code under member
  __name__ block, def, import     functions of the strategy class"
  class StrategyBase           -> "class already defined line 0"
  def bar_close(...)           -> "function already defined line 0"
  self.sym1 = "US.TEST"        -> "Can't assign a value to a trigger symbol"

The last four killed an attempt to embed this harness inside the strategy
file. That is why it lives here: the editor analyses the whole file, so a
self-test cannot coexist with the strategy no matter how it is guarded.
"""
from __future__ import annotations

import ast
import datetime
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STRATEGY = HERE / "settled_basis_ladder.py"

# Documented as taking float args; the editor rejects int literals here.
STRICT_FLOAT = {"min", "max", "abs", "floor", "ceil", "round", "power",
                "mod", "integer_division", "rate_ratio", "math_log"}
PY_OK = {"range", "len", "str", "int", "float", "bool", "list", "dict", "set",
         "tuple", "sorted", "sum", "enumerate", "zip", "getattr", "isinstance",
         "super", "Exception", "type", "repr", "Contract"}


# ══════════════════════════════════════════════════════════════════════════
#  1 · LINT — the editor's rules, checked before anything is pasted
# ══════════════════════════════════════════════════════════════════════════

def lint_structure(source: str) -> list[str]:
    """The editor's hardest rule: 'You can only write code under member
    functions of the strategy class.' Nothing may exist at module level except
    the strategy class itself — no imports, no constants, no helper defs, no
    `if __name__` block, and no shim classes (which also trip 'class already
    defined line 0')."""
    problems = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.ClassDef) and node.name == "Strategy":
            continue
        label = type(node).__name__
        name = getattr(node, "name", "")
        problems.append(
            f"L{node.lineno}: top-level {label}{(' ' + name) if name else ''} — "
            f"the editor allows ONLY the Strategy class at module level")
    return problems


def parse_manual(text: str) -> dict[str, dict]:
    api: dict[str, dict] = {}
    for m in re.finditer(r"^## ([a-z_][a-z0-9_]*)\s*$", text, re.M):
        name = m.group(1)
        section = text[m.end(): m.end() + 2500]
        sig = re.search(r"```\s*\n\s*" + re.escape(name) + r"\((.*?)\)\s*\n```",
                        section, re.S)
        if not sig:
            api.setdefault(name, {"params": None, "required": 0, "varargs": False})
            continue
        raw = sig.group(1).strip()
        params, required, varargs = [], 0, False
        if raw:
            for part in re.split(r",(?![^\[\]{}()]*\))", raw):
                part = part.strip()
                if not part:
                    continue
                if part.startswith("*"):
                    varargs = True
                    continue
                params.append(part.split("=")[0].strip())
                if "=" not in part:
                    required += 1
        api[name] = {"params": params, "required": required, "varargs": varargs}

    ident = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    for block in re.findall(r"```(.*?)```", text, re.S):
        for line in block.splitlines():
            m2 = re.match(r"^\s*(?:[\w.]+\s*=\s*)?([a-z_][a-z0-9_]*)\((.*)\)\s*$", line)
            if not m2:
                continue
            name, raw = m2.group(1), m2.group(2).strip()
            if name in api:
                continue
            params, required, ok = [], 0, True
            if raw:
                for part in raw.split(","):
                    pn = part.split("=")[0].strip()
                    if not ident.match(pn):
                        ok = False
                        break
                    params.append(pn)
                    if "=" not in part:
                        required += 1
            if ok:
                api[name] = {"params": params, "required": required, "varargs": False}
    return api


def lint_calls(source: str, api: dict) -> list[str]:
    tree = ast.parse(source)
    local = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    problems: list[str] = []

    tainted: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.BoolOp):
            for v in node.value.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, int) \
                        and not isinstance(v.value, bool):
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Name):
                            tainted[tgt.id] = node.lineno

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        name = node.func.id
        if name in PY_OK or name in local:
            continue
        spec = api.get(name)
        if spec is None:
            problems.append(f"L{node.lineno}: {name}() is not documented in the manual")
            continue

        if name in STRICT_FLOAT:
            for i, arg in enumerate(node.args, 1):
                for sub in ast.walk(arg):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, int) \
                            and not isinstance(sub.value, bool):
                        problems.append(
                            f"L{node.lineno}: {name}() arg {i} carries int literal "
                            f"{sub.value} — the editor demands float ({sub.value}.0)")
                        break
                if isinstance(arg, ast.Name) and arg.id in tainted:
                    problems.append(
                        f"L{node.lineno}: {name}() arg {i} is '{arg.id}', made int on "
                        f"L{tainted[arg.id]} — the editor infers int and demands float")

        params = spec.get("params")
        if params is None:
            continue
        # TOO FEW is as fatal as too many: max([...]) is a Python idiom the
        # platform does not have ("Interface max() is missing required
        # parameter value2").
        if len(node.args) + len(node.keywords) < spec.get("required", 0):
            problems.append(
                f"L{node.lineno}: {name}() got {len(node.args)} arg(s) but the manual "
                f"requires {spec['required']}: ({', '.join(params)})")
        if not spec.get("varargs") and len(node.args) > len(params):
            problems.append(
                f"L{node.lineno}: {name}() got {len(node.args)} positional args, "
                f"manual documents {len(params)}: ({', '.join(params)})")
        for kw in node.keywords:
            if kw.arg and kw.arg not in params:
                problems.append(
                    f"L{node.lineno}: {name}() has no parameter '{kw.arg}'")
    return problems


# ══════════════════════════════════════════════════════════════════════════
#  2 · SIMULATE — stub the broker API and assert the strategy's decisions
# ══════════════════════════════════════════════════════════════════════════

class _Enum:
    def __init__(self, *names):
        for n in names:
            setattr(self, n, n)


BOOK = {"prices": [], "day": 0, "qty": 0.0, "cost": 0.0, "cash": 100000.0,
        "log": [], "trades": []}
_out = print


def _series():
    return BOOK["prices"][:BOOK["day"] + 1]


def _stub_namespace():
    """Everything the broker injects, faked."""
    def bar_close(symbol=None, bar_type=None, select=2, session_type=None):
        s = _series()
        return s[-select] if len(s) >= select else None

    def ma(symbol=None, period=5, bar_type=None, data_type=None, select=2,
           session_type=None):
        s = _series()
        if len(s) < select + period - 1:
            return None
        w = s[-(select + period - 1):len(s) - select + 1]
        return sum(w) / len(w)

    def place_limit(symbol=None, price=None, qty=None, side=None,
                    time_in_force=None, order_trade_session_type=None):
        px = _series()[-2]
        if side == "BUY":
            total = BOOK["cost"] * BOOK["qty"] + px * qty
            BOOK["qty"] += qty
            BOOK["cost"] = total / BOOK["qty"]
            BOOK["cash"] -= px * qty
        else:
            BOOK["qty"] -= qty
            BOOK["cash"] += px * qty
            if BOOK["qty"] <= 0:
                BOOK["qty"], BOOK["cost"] = 0.0, 0.0
        BOOK["trades"].append((BOOK["day"], side, qty, round(px, 2)))
        return "SIMORDER"

    def logged_print(*a, **k):
        msg = " ".join(str(x) for x in a)
        BOOK["log"].append((BOOK["day"], msg))
        _out("  day", BOOK["day"], "|", msg)

    return {
        "StrategyBase": type("StrategyBase", (), {}),
        "AlgoStrategyType": _Enum("SECURITY"),
        "BarType": _Enum("K_DAY", "K_60M"),
        "DataType": _Enum("CLOSE", "OPEN", "HIGH", "LOW"),
        "THType": _Enum("RTH", "ETH", "ALL"),
        "OrderSide": _Enum("BUY", "SELL"),
        "TimeInForce": _Enum("DAY", "GTC"),
        "CostPriceModel": _Enum("AVG", "DILUTED"),
        "Currency": _Enum("USD", "HKD"),
        "GlobalType": _Enum("INT", "FLOAT", "BOOL"),
        "declare_strategy_type": lambda t: None,
        "show_variable": lambda v, t=None: v,
        "declare_trig_symbol": lambda: "US.TEST",
        "get_symbol_code": lambda symbol=None: symbol,
        "floor": math.floor,
        "device_time": lambda: datetime.datetime(2020, 1, 1) + datetime.timedelta(days=BOOK["day"]),
        "bar_close": bar_close,
        "bar_high": lambda symbol=None, bar_type=None, select=2, session_type=None:
            bar_close(symbol=symbol, select=select),
        "ma": ma,
        "current_price": lambda symbol=None, price_type=None: _series()[-2],
        "position_holding_qty": lambda symbol=None: BOOK["qty"],
        "available_qty": lambda symbol=None: BOOK["qty"],
        "position_cost": lambda symbol=None, cost_price_model=None: BOOK["cost"],
        "net_asset": lambda currency=None: BOOK["cash"] + BOOK["qty"] * _series()[-2],
        "total_cash": lambda currency=None: BOOK["cash"],
        "lot_size": lambda symbol=None: 1,
        "place_limit": place_limit,
        "print": logged_print,
    }


def load_strategy():
    ns = _stub_namespace()
    exec(compile(STRATEGY.read_text(encoding="utf-8"), "strategy", "exec"), ns)
    return ns["Strategy"]


def main() -> int:
    source = STRATEGY.read_text(encoding="utf-8")
    ok = True

    _out("=" * 70 + "\nEDITOR STRUCTURE RULES\n" + "=" * 70)
    structural = lint_structure(source)
    for pnote in structural:
        _out("  " + pnote)
    if structural:
        ok = False
    else:
        _out("  clean — only the Strategy class at module level")

    if len(sys.argv) > 1:
        _out("\n" + "=" * 70 + "\nAPI SIGNATURES vs MANUAL\n" + "=" * 70)
        api = parse_manual(Path(sys.argv[1]).read_text(encoding="utf-8"))
        calls = lint_calls(source, api)
        for pnote in calls:
            _out("  " + pnote)
        if calls:
            ok = False
        else:
            _out("  clean — every call matches the manual's signature")
    else:
        _out("\n(pass the Algo_Manual.md path to also check every call "
             "against the manual's signatures)")

    Strategy = load_strategy()
    allok = [ok]

    def check(name, cond):
        _out(("  PASS  " if cond else "  FAIL  ") + name)
        allok[0] = allok[0] and bool(cond)

    def run(prices, label):
        BOOK.update(prices=prices, day=0, qty=0.0, cost=0.0, cash=100000.0,
                    log=[], trades=[])
        s = Strategy()
        s.initialize()
        s.sym1, s.sym2, s.sym3, s.sym4 = "US.TEST", None, None, None
        _out("\n" + "=" * 70 + "\n" + label + "\n" + "=" * 70)
        for d in range(len(prices)):
            BOOK["day"] = d
            s.handle_data()
        _out("  -> trades:", len(BOOK["trades"]), "| final qty:", BOOK["qty"])
        return BOOK["trades"], list(BOOK["log"])

    def fresh(prices, day, qty=0.0, cost=0.0, cash=100000.0):
        BOOK.update(prices=prices, day=day, qty=qty, cost=cost, cash=cash,
                    log=[], trades=[])
        s = Strategy()
        s.initialize()
        s.sym1, s.sym2, s.sym3, s.sym4 = "US.TEST", None, None, None
        return s

    p = [100.0]
    for _ in range(260):
        p.append(p[-1] * 1.002)
    for _ in range(25):
        p.append(p[-1] * 0.995)
    for _ in range(15):
        p.append(p[-1] * 1.004)
    for _ in range(200):
        p.append(p[-1] * 1.008)
    for _ in range(80):
        p.append(p[-1] * 0.985)
    t1, l1 = run(p, "SCENARIO 1 · valley entry -> ladder -> structural exit")

    p2 = [100.0]
    for _ in range(210):
        p2.append(p2[-1] * 1.0005)
    for _ in range(126):
        p2.append(p2[-1] * 1.010)
    for _ in range(18):
        p2.append(p2[-1] * 0.994)
    for _ in range(20):
        p2.append(p2[-1] * 1.004)
    t2, l2 = run(p2, "SCENARIO 2 · parabolic -> anti-parabola starter size")

    p2b = [100.0]
    for _ in range(210):
        p2b.append(p2b[-1] * 1.001)
    for _ in range(126):
        p2b.append(p2b[-1] * 1.0065)
    for _ in range(20):
        p2b.append(p2b[-1] * 0.995)
    for _ in range(20):
        p2b.append(p2b[-1] * 1.004)
    t2b, l2b = run(p2b, "SCENARIO 2b · gain decayed below the line -> normal staging")

    p3 = [100.0]
    for _ in range(200):
        p3.append(p3[-1] * 0.999)
    for i in range(120):
        p3.append(p3[-1] * (1.01 if i % 2 else 0.99))
    t3, l3 = run(p3, "SCENARIO 3 · downtrend chop -> must never enter")

    _out("\n" + "=" * 70 + "\nMECHANISM\n" + "=" * 70)
    check("S1 entered on the valley", any(t[1] == "BUY" for t in t1))
    check("S1 fired ladder trims", sum(1 for d, m in l1 if "TRIM rung" in m) >= 2)
    check("S1 euphoria rung tagged at 2x", any("euphoria protocol" in m for d, m in l1))
    check("S1 exited on structural break", any("EXIT structural" in m for d, m in l1))
    check("S1 never went short", all(t[1] in ("BUY", "SELL") for t in t1))
    check("S2 flagged anti-parabola", any("anti-parabola" in m for d, m in l2))
    check("S2 took exactly ONE stage (starter)",
          sum(1 for d, m in l2 if "BUY stage" in m) == 1)
    check("S2b did NOT flag (below the line)",
          not any("anti-parabola" in m for d, m in l2b))
    check("S2b staged normally (>1 stage)",
          sum(1 for d, m in l2b if "BUY stage" in m) > 1)
    check("S3 never entered", not any(t[1] == "BUY" for t in t3))
    check("no standing reason repeats daily",
          max(sum(1 for d, m in log if "sources disagree" in m)
              for log in (l1, l2, l3)) <= 3)

    # Regressions for the confirmed defects. Each drives the REAL path and is
    # PAIRED WITH ITS INVERSE, so a test cannot pass merely because the setup
    # never reached the code. That pairing caught the percentage-floor bug.
    _out("\n" + "=" * 70 + "\nFIX REGRESSIONS\n" + "=" * 70)

    s = fresh(p, 300)
    BOOK["cash"] = s.floor_amount * 1.0
    st = s._st("US.TEST")
    st["close_now"] = p[298]
    s.buy_one_stage("US.TEST", "US.TEST", st, p[298], 10.0, 3)
    check("floor blocks the buy when cash is AT the floor",
          not any(t[1] == "BUY" for t in BOOK["trades"])
          and any("floor" in m for d, m in BOOK["log"]))

    s = fresh(p, 300)
    st = s._st("US.TEST")
    st["close_now"] = p[298]
    s.buy_one_stage("US.TEST", "US.TEST", st, p[298], 10.0, 3)
    check("same path DOES buy when cash is above the floor",
          any(t[1] == "BUY" for t in BOOK["trades"]))

    short = [100.0]
    for _ in range(80):
        short.append(short[-1] * 1.004)
    for _ in range(14):
        short.append(short[-1] * 0.992)
    for _ in range(4):
        short.append(short[-1] * 1.003)
    s = fresh(short, len(short) - 1)
    check("short history is unmeasurable (returns None)",
          s.six_month_gain("US.TEST", short[-2]) is None)
    st = s._st("US.TEST")
    st["close_now"] = short[-2]
    s.consider_entry("US.TEST", "US.TEST", st, short[-2], short[-3], 1.0, 2.0)
    check("unmeasurable 6m gain => STARTER ONLY (fails closed)",
          st["starter_only"] is True)

    s = fresh(p, 400, qty=100.0, cost=100.0)
    st = s._st("US.TEST")
    st.update(rungs_fired=[1], stages_taken=1, ref=p[398] / 1.10,
              ref_qty=100.0, close_now=p[398], reconciled=True)
    s.manage_position("US.TEST", "US.TEST", st, p[398], p[398] * 0.5)
    check("a fired rung stops the adder buying it back",
          not any(t[1] == "BUY" for t in BOOK["trades"]))

    s = fresh(p, 400, qty=100.0, cost=100.0)
    st = s._st("US.TEST")
    st.update(rungs_fired=[], stages_taken=1, ref=p[398] / 1.10,
              ref_qty=100.0, close_now=p[398], reconciled=True)
    s.manage_position("US.TEST", "US.TEST", st, p[398], p[398] * 0.5)
    check("with no rung fired the adder still works",
          any(t[1] == "BUY" for t in BOOK["trades"]))

    s = fresh(p, 400, qty=100.0, cost=p[398] / 2.2)
    st = s._st("US.TEST")
    st["close_now"] = p[398]
    s._reconcile("US.TEST", "US.TEST", st)
    check("restart adopts fully-staged state", st["stages_taken"] == s.stages)
    check("restart marks already-passed rungs as fired",
          1 in st["rungs_fired"] and 2 in st["rungs_fired"])

    _out("\nRESULT: " + ("all green" if allok[0] else "FAILURES ABOVE"))
    return 0 if allok[0] else 1


if __name__ == "__main__":
    sys.exit(main())
