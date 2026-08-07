# ═══════════════════════════════════════════════════════════════════════════
#  THE SETTLED-BASIS LADDER  ·  v2.1  ·  single file
#
#  The Portfolio Machine's risk discipline, made mechanical and backtestable.
#  Everything is in here: the strategy, the documentation, and — after the
#  banner near the bottom — an offline self-test the platform never runs.
#
#  ┌─────────────────────────────────────────────────────────────────────┐
#  │ PASTE THIS WHOLE FILE INTO THE STRATEGY EDITOR.                     │
#  │ If your editor objects to anything below the "OFFLINE SELF-TEST"    │
#  │ banner, delete from that banner to the end of the file. Nothing     │
#  │ above it depends on anything below it.                              │
#  └─────────────────────────────────────────────────────────────────────┘
#
#  ── HOW TO SCHEDULE IT (this matters, and v1 got it wrong) ───────────────
#  Trigger: RUN AT A SPECIFIED TIME, ~15:50 ET, on trading days.
#  NOT on the daily bar.
#
#  Why: the manual restricts US market orders to regular trading hours, and a
#  daily-bar trigger fires AFTER the close — every order would be rejected
#  live while filling happily in the backtest. Running just before the close
#  puts execution inside RTH. It costs nothing in discipline: the DECISION
#  still reads `select=2`, the last CLOSED daily bar (yesterday's), never
#  today's forming one. Orders are limit orders, so they also work in
#  extended sessions and bound slippage.
#
#  ── WHAT THIS IS ─────────────────────────────────────────────────────────
#  The RISK DISCIPLINE of the Portfolio Machine, not its research. The
#  analyst panel's judgment — whether HBM is sold out through 2027, whether a
#  moat is technical or merely temporal — is not mechanical, so it is not
#  here. A good backtest does NOT validate the theses. It answers one
#  question: does the discipline beat buy-and-hold on the names we track?
#
#  ── THE TRANSLATION ──────────────────────────────────────────────────────
#  Every rule below already exists in the constitution or the codebase.
#  Nothing was invented to make a backtest look good.
#
#   Law 2 — settled only    -> every read uses select=2, the last CLOSED bar
#                              (select=1 is the bar still forming — the INTC
#                              $91.63->$92.52 flip, in platform form), plus a
#                              once-per-day gate so an intraday trigger cannot
#                              produce an intraday decision.
#   Two-source check        -> entry needs the structural regime AND a turning
#                              valley to agree. Disagreement logs and does
#                              nothing. It never averages the two halves.
#   The floor is sacred     -> a FIXED dollar reserve (Charter §V: "$40,000,
#                              sacred, never invested") that is never
#                              deployable, enforced against actual cash. Fixed,
#                              not a percentage — a percentage floor shrinks
#                              exactly when the book is losing.
#   Anti-parabola (§V)      -> up >=100% in six months means STARTER SIZE ONLY.
#                              It FAILS CLOSED: if history is too short to
#                              judge, you still get starter size, because
#                              "I could not check" is never permission.
#   Valley entry (§IV)      -> buys a pullback inside an intact trend. It
#                              structurally cannot buy a breakout into
#                              euphoria. "Drawdowns are the queue, not the
#                              hazard."
#   Staged thirds           -> positions are built, never taken in one clip,
#                              and adds require proof. It never averages down.
#   Pre-declared ladders    -> exit rungs written in advance, on a calm day.
#                              Rung 2 IS the euphoria protocol (2x cost).
#                              Once ANY rung fires, adding stops — otherwise
#                              the exit and entry engines fight each other.
#   Dated signpost          -> a time stop. A thesis gets a window; no
#                              progress inside it means the window closed.
#   Thesis break            -> a settled close below the long trend is a
#                              structural exit, not a wobble.
#
#  ── ONE KNOWING COMPROMISE ───────────────────────────────────────────────
#  All exit decisions use a reference cost the strategy stores ITSELF, in the
#  same backward-adjusted price space the bars live in. The broker's
#  `position_pl_ratio` is marked to the CURRENT (unsettled) price and its cost
#  is unadjusted, so using it would both break law 2 and mix two price scales.
#  In a backtest, bars are adjusted consistently and this is exactly right.
#  In LIVE trading a split or large dividend re-scales the bars but not the
#  stored reference — reset the strategy after a corporate action.
#
#  ── PARAMETERS WORTH TOUCHING FIRST ──────────────────────────────────────
#   floor_amount      40000  fixed dollars never deployed (Charter §V)
#   max_position_pct     25  max % of deployable capital in one name
#   stages                3  staged thirds — entries are built, not taken
#   trend_period        200  the structural regime line
#   pullback_pct          8  how deep a valley must be before it is an entry
#   parabola_pct        100  6-month gain that forces starter size
#   rung1/2/3_pct  50/100/200  the pre-declared exit ladder
#   horizon_days        252  the dated signpost — the window the thesis gets
#   min_progress_pct     10  what counts as progress at the end of it
#   hard_stop_pct        30  the backstop against permanent loss
#   limit_band_pct        2  how far through the price we will pay to fill
#
#  ── HOW TO JUDGE THE RESULT HONESTLY ─────────────────────────────────────
#  A good backtest on one symbol proves nothing. Three tests first:
#
#   1. CROSS-NAME. Run IDENTICAL parameters across LITE, PLTR, RKLB, ACHR,
#      CELH, SNDK, MU. If it only works on one, you fit that name's history —
#      eleven knobs will do that happily.
#   2. MEASURE WHAT PEEKING IS WORTH. Set use_settled to False (reads the
#      forming bar) and re-run. If the edge DEPENDS on that, the edge is the
#      lookahead the whole constitution exists to prevent. That switch exists
#      only to run this test.
#   3. VERSUS BUY-AND-HOLD. On a strong trending name, buy-and-hold usually
#      wins on raw return. The claim here is not more return — it is less
#      permanent-loss risk and no decision made on a rumor. Compare max
#      drawdown and worst trade, not CAGR.
#
#  If it fails all three, that is a finding worth having: the discipline costs
#  more than it saves, and better to learn it here than with the real book.
#
#  ── KNOWN LIMITATIONS, STATED UP FRONT ───────────────────────────────────
#   * Eleven parameters on a few years of data WILL overfit if tuned per
#     name. Tune once, globally, or not at all.
#   * No fundamentals. It cannot see an HBM sold-out horizon or a
#     qualification slip. It is the guard, not the analyst.
#   * Trend-following inheritance: regime filters chop badly in sideways
#     markets. Expect a string of small losses there; the time stop bounds it.
#   * The floor is simulated here, not enforced by the broker. In the real
#     book the floor is a separate account — that is the point of it.
# ═══════════════════════════════════════════════════════════════════════════


# The platform injects StrategyBase. Offline (running this file directly to
# self-test) it does not exist, so provide a stand-in — this branch never
# executes on the platform.
try:
    StrategyBase
except NameError:
    class StrategyBase(object):
        pass


class Strategy(StrategyBase):

    # ── setup ──────────────────────────────────────────────────────────────
    def initialize(self):
        declare_strategy_type(AlgoStrategyType.SECURITY)
        self.trigger_symbols()
        self.custom_indicator()
        self.global_variables()

        # Machine-owned state, keyed by symbol code. NOTE: this is in-memory.
        # `initialize()` re-runs on every strategy restart, so a restart with
        # a live position would otherwise re-arm the ladder from rung one and
        # let the position stack past its cap. `_reconcile()` handles that.
        self.state = {}
        self.last_run_day = ""

    def trigger_symbols(self):
        self.sym1 = declare_trig_symbol()
        self.sym2 = declare_trig_symbol()
        self.sym3 = declare_trig_symbol()
        self.sym4 = declare_trig_symbol()

    def custom_indicator(self):
        pass

    def global_variables(self):
        # ── the floor and the size caps (Charter §V) ──
        # The floor is FIXED DOLLARS, not a percentage. Charter §V says
        # "$40,000, sacred, never invested" — and a percentage floor shrinks
        # precisely when the book is losing, which is when the floor is the
        # whole point. Set it to your real reserve before backtesting.
        self.floor_amount = show_variable(40000, GlobalType.INT)
        self.max_position_pct = show_variable(25, GlobalType.INT)
        self.stages = show_variable(3, GlobalType.INT)

        # ── the structural regime ──
        self.trend_period = show_variable(200, GlobalType.INT)
        self.fast_period = show_variable(50, GlobalType.INT)

        # ── the valley ──
        self.pullback_pct = show_variable(8, GlobalType.INT)
        self.high_lookback = show_variable(60, GlobalType.INT)

        # ── anti-parabola (Charter §V sizing law) ──
        self.parabola_pct = show_variable(100, GlobalType.INT)
        self.parabola_lookback = show_variable(126, GlobalType.INT)

        # ── the pre-declared exit ladder ──
        self.rung1_pct = show_variable(50, GlobalType.INT)
        self.rung1_trim = show_variable(20, GlobalType.INT)
        self.rung2_pct = show_variable(100, GlobalType.INT)   # euphoria: 2x cost
        self.rung2_trim = show_variable(25, GlobalType.INT)
        self.rung3_pct = show_variable(200, GlobalType.INT)
        self.rung3_trim = show_variable(25, GlobalType.INT)

        # ── the dated signpost and the backstop ──
        self.horizon_days = show_variable(252, GlobalType.INT)
        self.min_progress_pct = show_variable(10, GlobalType.INT)
        self.hard_stop_pct = show_variable(30, GlobalType.INT)

        # ── execution ──
        # Limit orders only: US market orders are RTH-only per the manual,
        # and a limit also caps slippage. This band is how far through the
        # reference price we are willing to pay to get filled.
        self.limit_band_pct = show_variable(2, GlobalType.INT)

        # Leave TRUE. False exists only to MEASURE what reading the forming
        # bar is worth (README test 2).
        self.use_settled = show_variable(True, GlobalType.BOOL)

    # ── helpers ────────────────────────────────────────────────────────────

    def _code(self, symbol):
        try:
            return str(get_symbol_code(symbol=symbol))
        except Exception:
            return str(symbol)

    def _dp(self, value, places=1):
        """Round to N decimals using the platform's SINGLE-ARGUMENT round().

        The platform's round(value) takes no precision argument — Python's
        two-argument form is rejected by the editor. Scale, round, unscale."""
        if value is None:
            return 0.0
        factor = 1.0
        for _ in range(places):
            factor = factor * 10.0
        return round(value * factor) / factor

    def _sel(self, offset=0):
        """Bar selector. LAW 2: settled mode starts at select=2 — at the
        recommended ~15:50 trigger, select=1 is today's STILL-FORMING bar and
        select=2 is the last closed one."""
        base = 2 if self.use_settled else 1
        return base + offset

    def _st(self, code):
        if code not in self.state:
            self.state[code] = {
                "rungs_fired": [],
                "stages_taken": 0,
                "bars_held": 0,
                "starter_only": False,
                "ref": 0.0,          # our own cost basis, in adjusted space
                "ref_qty": 0.0,      # shares behind that basis
                "close_now": 0.0,
                "last_note": "",
                "reconciled": False,
            }
        return self.state[code]

    def _symbols(self):
        out = []
        for s in (self.sym1, self.sym2, self.sym3, self.sym4):
            try:
                if s is not None and self._code(s) not in ("", "None"):
                    out.append(s)
            except Exception:
                pass
        return out

    def _reconcile(self, symbol, code, st):
        """A restart wipes in-memory state while the BROKER still holds the
        position. Adopting empty state there would re-arm the whole ladder and
        let the position stack to twice its cap. So when we find shares we did
        not record, adopt the most CONSERVATIVE consistent state: fully staged
        (no more buying) and every rung the current gain has already passed
        marked fired."""
        if st["reconciled"]:
            return
        st["reconciled"] = True
        qty = position_holding_qty(symbol=symbol)
        if not qty or qty <= 0 or st["stages_taken"] > 0:
            return

        cost = position_cost(symbol=symbol, cost_price_model=CostPriceModel.AVG)
        st["ref"] = cost if cost and cost > 0 else 0.0
        st["ref_qty"] = qty
        st["stages_taken"] = self.stages
        gain = self._gain_pct(st)
        for rung_id, level in ((1, self.rung1_pct), (2, self.rung2_pct),
                               (3, self.rung3_pct)):
            if gain >= level:
                st["rungs_fired"].append(rung_id)
        print("[reconcile] " + code + ": found " + str(qty) + " sh with no state "
              "(restart?) — adopting fully-staged, rungs " +
              str(st["rungs_fired"]) + " assumed fired. Reference is the "
              "broker's UNADJUSTED average; reset after a corporate action.")

    def _gain_pct(self, st):
        """Gain versus OUR settled reference — both sides in adjusted space,
        both from closed bars."""
        if not st["ref"] or st["ref"] <= 0:
            return 0.0
        last = st["close_now"]
        if not last or last <= 0:
            return 0.0
        return (last / st["ref"] - 1.0) * 100.0

    # ── the daily gate ─────────────────────────────────────────────────────

    def handle_data(self):
        """One decision per calendar day, on closed bars only.

        The day is stamped only AFTER at least one symbol evaluated cleanly.
        v1 stamped it first, so a single early failure — a data gap, a
        pre-market start — burned the whole day INCLUDING the exit checks."""
        today = str(device_time().date())
        if today == self.last_run_day:
            return

        any_ok = False
        for symbol in self._symbols():
            try:
                self.evaluate_one(symbol)
                any_ok = True
            except Exception as e:
                print("[error] " + self._code(symbol) + " skipped: " + str(e) +
                      " — the day is NOT consumed; exits retry on the next trigger")
        if any_ok:
            self.last_run_day = today

    # ── one name, one day ──────────────────────────────────────────────────

    def evaluate_one(self, symbol):
        code = self._code(symbol)
        st = self._st(code)

        close = bar_close(symbol=symbol, bar_type=BarType.K_DAY,
                          select=self._sel(0), session_type=THType.RTH)
        prev = bar_close(symbol=symbol, bar_type=BarType.K_DAY,
                         select=self._sel(1), session_type=THType.RTH)
        trend = ma(symbol=symbol, period=self.trend_period, bar_type=BarType.K_DAY,
                   data_type=DataType.CLOSE, select=self._sel(0),
                   session_type=THType.RTH)
        fast = ma(symbol=symbol, period=self.fast_period, bar_type=BarType.K_DAY,
                  data_type=DataType.CLOSE, select=self._sel(0),
                  session_type=THType.RTH)

        if close is None or trend is None or close <= 0 or trend <= 0:
            if st["last_note"] != "gap":
                print("[gap] " + code + ": no settled price/trend on file — no "
                      "action until there is (a declared gap, never a guess)")
                st["last_note"] = "gap"
            return
        st["close_now"] = close

        self._reconcile(symbol, code, st)

        qty = position_holding_qty(symbol=symbol)
        if qty and qty > 0:
            st["bars_held"] = st["bars_held"] + 1
            self.manage_position(symbol, code, st, close, trend)
        else:
            if st["stages_taken"] > 0:
                self.reset_episode(code, st)
            self.consider_entry(symbol, code, st, close, prev, trend, fast)

    # ── exits first: protecting capital outranks deploying it ──────────────

    def manage_position(self, symbol, code, st, close, trend):
        gain = self._gain_pct(st)

        # 1 · STRUCTURAL STOP — the structure that justified owning it is gone.
        if close < trend:
            print("[EXIT structural] " + code + ": settled close " + str(close) +
                  " < trend(" + str(self.trend_period) + ") " +
                  str(self._dp(trend, 2)) + " — thesis structure broken, full exit")
            self.sell_all(symbol, code, st, close)
            return

        # 2 · HARD STOP — the floor is sacred; one name may not be why it is
        #     touched.
        if gain <= -self.hard_stop_pct:
            print("[EXIT hard-stop] " + code + ": " + str(self._dp(gain, 1)) +
                  "% — permanent-loss backstop, full exit")
            self.sell_all(symbol, code, st, close)
            return

        # 3 · DATED SIGNPOST — the window closed without progress.
        if st["bars_held"] >= self.horizon_days and gain < self.min_progress_pct:
            print("[EXIT signpost] " + code + ": " + str(st["bars_held"]) +
                  " sessions held, only " + str(self._dp(gain, 1)) +
                  "% — the window closed without progress, exit")
            self.sell_all(symbol, code, st, close)
            return

        # 4 · THE PRE-DECLARED LADDER. Rung 2 IS the euphoria protocol (2x
        #     cost). A gap through several rungs fires all of them the same
        #     day — v1 returned after one, leaving the rest of the move
        #     unprotected.
        fired_any = False
        for rung_id, level, trim in ((1, self.rung1_pct, self.rung1_trim),
                                     (2, self.rung2_pct, self.rung2_trim),
                                     (3, self.rung3_pct, self.rung3_trim)):
            if rung_id in st["rungs_fired"]:
                continue
            if gain < level:
                continue
            sellable = self.sellable_qty(symbol)
            slice_qty = floor(sellable * trim / 100.0)
            lot = lot_size(symbol=symbol) or 1.0
            if lot > 1:
                slice_qty = floor(slice_qty / lot) * lot
            if slice_qty < 1:
                # Do NOT burn the rung: the position may grow enough to slice
                # later, and a silently-consumed rung is a broken promise.
                print("[rung " + str(rung_id) + " deferred] " + code +
                      ": slice rounds below one tradable unit — rung stays armed")
                continue
            tag = " (euphoria protocol: 2x cost)" if level >= 100 else ""
            print("[TRIM rung " + str(rung_id) + "] " + code + ": +" +
                  str(self._dp(gain, 1)) + "% >= " + str(level) + "% — selling " +
                  str(trim) + "% (" + str(slice_qty) + " sh)" + tag)
            self.submit(symbol, slice_qty, OrderSide.SELL, close)
            st["rungs_fired"].append(rung_id)
            st["ref_qty"] = max(st["ref_qty"] - slice_qty, 0.0)
            fired_any = True

        if fired_any:
            return

        # 5 · STAGED THIRDS — but never after a rung has fired. v1 would trim
        #     at +50% and buy the same shares back the next day, so the exit
        #     ladder and the entry engine fought each other.
        if st["rungs_fired"]:
            return
        self.consider_add(symbol, code, st, close, trend)

    # ── entries: two sources must agree, or nothing happens ────────────────

    def consider_entry(self, symbol, code, st, close, prev, trend, fast):
        regime_ok = (close > trend) and (fast is not None and fast > trend)

        high = self.recent_high(symbol)
        if high is None or high <= 0:
            if st["last_note"] != "nohigh":
                print("[gap] " + code + ": no lookback high — no action")
                st["last_note"] = "nohigh"
            return
        drawdown_pct = (1.0 - close / high) * 100.0
        valley_ok = (drawdown_pct >= self.pullback_pct) and \
                    (prev is not None and close > prev)

        if not (regime_ok or valley_ok):
            return

        if regime_ok != valley_ok:
            reason = ("trend intact but no valley (would be chasing)"
                      if regime_ok else
                      "valley present but structure broken (falling knife)")
            if st["last_note"] != reason:
                print("[no-trade] " + code + ": sources disagree — " + reason)
                st["last_note"] = reason
            return
        st["last_note"] = ""

        # ANTI-PARABOLA — and it FAILS CLOSED. v1 skipped the check when
        # history was too short, handing full size to exactly the recent-IPO
        # names the rule exists to police. Not being able to check is not
        # permission.
        gain6m = self.six_month_gain(symbol, close)
        if gain6m is None:
            if not st["starter_only"]:
                print("[anti-parabola] " + code + ": cannot measure a 6-month "
                      "gain (short history) — STARTER SIZE ONLY. An unmeasured "
                      "check fails closed.")
            st["starter_only"] = True
        elif gain6m >= self.parabola_pct:
            if not st["starter_only"]:
                print("[anti-parabola] " + code + ": +" + str(self._dp(gain6m, 0)) +
                      "% in ~6m — STARTER SIZE ONLY for this episode "
                      "(Charter §V sizing law + Momentum-RISK redline)")
            st["starter_only"] = True

        max_stages = 1 if st["starter_only"] else self.stages
        if st["stages_taken"] >= max_stages:
            return
        self.buy_one_stage(symbol, code, st, close, drawdown_pct, max_stages)

    def consider_add(self, symbol, code, st, close, trend):
        """Adding is still an entry: structure must hold and the name must
        have proven something since the last stage. Never averages down."""
        max_stages = 1 if st["starter_only"] else self.stages
        if st["stages_taken"] >= max_stages:
            return
        if close <= trend:
            return
        if self._gain_pct(st) < 5.0:
            return                                  # no proof yet; wait
        self.buy_one_stage(symbol, code, st, close, None, max_stages)

    # ── sizing: the floor is untouchable and the cap only clamps down ──────

    def buy_one_stage(self, symbol, code, st, close, drawdown_pct, max_stages):
        equity = net_asset(currency=Currency.USD)
        if equity is None or equity <= 0:
            print("[gap] " + code + ": no net asset value — no sizing possible")
            return

        floor_dollars = self.floor_amount * 1.0
        deployable = equity - floor_dollars
        if deployable <= 0:
            if st["last_note"] != "floor":
                print("[no-trade] " + code + ": net assets are at or below the "
                      + str(self._dp(floor_dollars, 0)) + " floor — nothing is "
                      "deployable")
                st["last_note"] = "floor"
            return
        stage_value = deployable * (self.max_position_pct / 100.0) / max_stages

        # THE FLOOR, ACTUALLY ENFORCED. v1 clamped the stage against TOTAL
        # cash — which includes the floor's dollars — so a drawdown could
        # spend the sacred reserve. Only cash ABOVE the floor is deployable.
        cash_now = total_cash(currency=Currency.USD) or 0.0
        cash_above_floor = cash_now - floor_dollars
        if cash_above_floor <= 0:
            if st["last_note"] != "floor":
                print("[no-trade] " + code + ": cash is at or below the " +
                      str(self._dp(floor_dollars, 0)) + " floor — the floor is "
                      "not a buffer to borrow from")
                st["last_note"] = "floor"
            return
        spendable = min(stage_value * 1.0, cash_above_floor * 1.0)

        # Share count uses a TRADABLE price, not an adjusted bar close: this
        # is arithmetic ("how many shares does $X buy"), not a decision.
        px = current_price(symbol=symbol, price_type=THType.RTH)
        if px is None or px <= 0:
            px = close
        qty = floor(spendable / px)
        lot = lot_size(symbol=symbol) or 1.0
        if lot > 1:
            qty = floor(qty / lot) * lot
        if qty < 1:
            print("[no-trade] " + code + ": stage size below one tradable unit")
            return

        why = ("valley -" + str(self._dp(drawdown_pct, 1)) + "% from high, turning"
               if drawdown_pct is not None else "adding on proof above reference")
        print("[BUY stage " + str(st["stages_taken"] + 1) + "/" + str(max_stages) +
              "] " + code + ": " + str(qty) + " sh @ ~" + str(self._dp(px, 2)) +
              " — " + why + (" [STARTER ONLY]" if st["starter_only"] else ""))
        self.submit(symbol, qty, OrderSide.BUY, close)

        # Our own reference cost, in the same adjusted space as the bars.
        total_ref = st["ref"] * st["ref_qty"] + close * qty
        st["ref_qty"] = st["ref_qty"] + qty
        st["ref"] = total_ref / st["ref_qty"]
        st["stages_taken"] = st["stages_taken"] + 1

    # ── execution ──────────────────────────────────────────────────────────

    def submit(self, symbol, qty, side, ref_close):
        """Limit orders only. US market orders are RTH-only per the manual, so
        a market order from a strategy that thinks in daily closes is a live
        rejection waiting to happen; the limit also bounds slippage."""
        band = self.limit_band_pct / 100.0
        px = current_price(symbol=symbol, price_type=THType.RTH)
        if px is None or px <= 0:
            px = ref_close
        if side == OrderSide.BUY:
            limit = px * (1.0 + band)
        else:
            limit = px * (1.0 - band)
        place_limit(symbol=symbol, price=self._dp(limit, 2), qty=qty, side=side,
                    time_in_force=TimeInForce.DAY)

    def sellable_qty(self, symbol):
        """Shares actually sellable — holdings minus anything frozen by a
        working order. Selling raw holdings can be rejected wholesale."""
        q = available_qty(symbol=symbol)
        if q is None or q <= 0:
            q = position_holding_qty(symbol=symbol) or 0.0
        return q

    def sell_all(self, symbol, code, st, close):
        qty = self.sellable_qty(symbol)
        if qty < 1:
            print("[exit deferred] " + code + ": nothing sellable right now "
                  "(shares frozen by a working order) — retrying next session")
            return
        self.submit(symbol, qty, OrderSide.SELL, close)
        # Reset only when the exit covered the whole position. v1 reset
        # unconditionally, so a partial or unfilled exit wiped the ladder and
        # the clock while shares were still held.
        held = position_holding_qty(symbol=symbol) or 0.0
        if qty >= held:
            self.reset_episode(code, st)

    # ── measurements, all on closed bars ───────────────────────────────────

    def recent_high(self, symbol):
        """Highest HIGH over the lookback, from closed bars."""
        high = None
        for i in range(0, self.high_lookback):
            h = bar_high(symbol=symbol, bar_type=BarType.K_DAY,
                         select=self._sel(i), session_type=THType.RTH)
            if h is not None and h > 0:
                if high is None or h > high:
                    high = h
        return high

    def six_month_gain(self, symbol, close):
        past = bar_close(symbol=symbol, bar_type=BarType.K_DAY,
                         select=self._sel(self.parabola_lookback),
                         session_type=THType.RTH)
        if past is None or past <= 0:
            return None
        return (close / past - 1.0) * 100.0

    def reset_episode(self, code, st):
        """An episode ends when the position is flat. The ladder re-arms from
        rung one for the NEXT episode."""
        st["rungs_fired"] = []
        st["stages_taken"] = 0
        st["bars_held"] = 0
        st["starter_only"] = False
        st["ref"] = 0.0
        st["ref_qty"] = 0.0
        st["last_note"] = ""


# ═══════════════════════════════════════════════════════════════════════════
#  OFFLINE SELF-TEST — DELETE FROM HERE DOWN IF YOUR EDITOR OBJECTS
#
#  The platform never runs any of this: `__name__` is the module's name when
#  the broker loads a strategy, not "__main__". Nothing above this banner
#  depends on anything below it, so deleting this section leaves a complete,
#  working strategy.
#
#  What it is for: platform strategies cannot be unit-tested — the API only
#  exists inside the broker's runtime. So this stubs that API, feeds synthetic
#  price paths, and asserts the strategy's DECISIONS. Run it after any edit:
#
#      python3 settled_basis_ladder.py
#      python3 settled_basis_ladder.py /path/to/Algo_Manual.md   # + API check
#
#  The second form also checks every platform call against the manual's
#  documented signature — arity, keyword names, and int-where-float-is-
#  required. That check exists because v1 shipped with seven editor errors:
#  this platform's round() takes ONE argument and min() type-checks for float.
#  Verifying that a function NAME exists proves nothing about how it is called.
#
#  It proves MECHANISM, never profitability: the paths are synthetic and the
#  fills are frictionless. Judge the strategy on a real backtest; judge this
#  on whether every constitutional rule still fires when it should.
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import ast
    import datetime
    import math
    import re
    import sys

    # ── stub the platform API ──────────────────────────────────────────────
    class _Enum(object):
        def __init__(self, *names):
            for n in names:
                setattr(self, n, n)

    AlgoStrategyType = _Enum("SECURITY")
    BarType = _Enum("K_DAY", "K_60M")
    DataType = _Enum("CLOSE", "OPEN", "HIGH", "LOW")
    THType = _Enum("RTH", "ETH", "ALL")
    OrderSide = _Enum("BUY", "SELL")
    TimeInForce = _Enum("DAY", "GTC")
    CostPriceModel = _Enum("AVG", "DILUTED")
    Currency = _Enum("USD", "HKD")
    GlobalType = _Enum("INT", "FLOAT", "BOOL")

    BOOK = {"prices": [], "day": 0, "qty": 0.0, "cost": 0.0, "cash": 100000.0,
            "log": [], "trades": []}

    def declare_strategy_type(t):
        pass

    def show_variable(v, t=None):
        return v

    def declare_trig_symbol():
        return "US.TEST"

    def get_symbol_code(symbol=None):
        return symbol

    def floor(v):
        return math.floor(v)

    def device_time():
        return datetime.datetime(2020, 1, 1) + datetime.timedelta(days=BOOK["day"])

    def _series():
        return BOOK["prices"][:BOOK["day"] + 1]

    def bar_close(symbol=None, bar_type=None, select=2, session_type=None):
        s = _series()
        if len(s) < select:
            return None
        return s[-select]

    def bar_high(symbol=None, bar_type=None, select=2, session_type=None):
        return bar_close(symbol=symbol, select=select)   # no intrabar range here

    def ma(symbol=None, period=5, bar_type=None, data_type=None, select=2,
           session_type=None):
        s = _series()
        if len(s) < select + period - 1:
            return None
        window = s[-(select + period - 1):len(s) - select + 1]
        return sum(window) / len(window)

    def current_price(symbol=None, price_type=None):
        return _series()[-2]

    def position_holding_qty(symbol=None):
        return BOOK["qty"]

    def available_qty(symbol=None):
        return BOOK["qty"]

    def position_cost(symbol=None, cost_price_model=None):
        return BOOK["cost"]

    def net_asset(currency=None):
        return BOOK["cash"] + BOOK["qty"] * _series()[-2]

    def total_cash(currency=None):
        return BOOK["cash"]

    def lot_size(symbol=None):
        return 1

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
                BOOK["qty"] = 0.0
                BOOK["cost"] = 0.0
        BOOK["trades"].append((BOOK["day"], side, qty, round(px * 100.0) / 100.0))
        return "SIMORDER"

    _out = print

    def print(*a, **k):                                   # noqa: A001
        msg = " ".join(str(x) for x in a)
        BOOK["log"].append((BOOK["day"], msg))
        _out("  day", BOOK["day"], "|", msg)

    # ── scenarios ──────────────────────────────────────────────────────────
    def run(prices, label):
        BOOK.update(prices=prices, day=0, qty=0.0, cost=0.0, cash=100000.0,
                    log=[], trades=[])
        s = Strategy()
        s.initialize()
        s.sym1 = "US.TEST"
        s.sym2 = None
        s.sym3 = None
        s.sym4 = None
        _out("\n" + "=" * 70 + "\n" + label + "\n" + "=" * 70)
        for d in range(len(prices)):
            BOOK["day"] = d
            s.handle_data()
        _out("  -> trades:", len(BOOK["trades"]), "| final qty:", BOOK["qty"])
        return BOOK["trades"], BOOK["log"]

    def fresh(prices, day, qty=0.0, cost=0.0, cash=100000.0):
        BOOK.update(prices=prices, day=day, qty=qty, cost=cost, cash=cash,
                    log=[], trades=[])
        s = Strategy()
        s.initialize()
        s.sym1 = "US.TEST"
        s.sym2 = None
        s.sym3 = None
        s.sym4 = None
        return s

    allok = True

    def check(name, ok):
        global allok
        _out(("  PASS  " if ok else "  FAIL  ") + name)
        allok = allok and bool(ok)
        return ok

    p = [100.0]
    for _i in range(260):
        p.append(p[-1] * 1.002)                 # long base uptrend
    for _i in range(25):
        p.append(p[-1] * 0.995)                 # ~12% valley
    for _i in range(15):
        p.append(p[-1] * 1.004)                 # turn
    for _i in range(200):
        p.append(p[-1] * 1.008)                 # the run (>200%)
    for _i in range(80):
        p.append(p[-1] * 0.985)                 # structural break
    t1, l1 = run(p, "SCENARIO 1 · valley entry -> ladder -> structural exit")

    p2 = [100.0]
    for _i in range(210):
        p2.append(p2[-1] * 1.0005)
    for _i in range(126):
        p2.append(p2[-1] * 1.010)               # ~3.5x in six months
    for _i in range(18):
        p2.append(p2[-1] * 0.994)
    for _i in range(20):
        p2.append(p2[-1] * 1.004)
    t2, l2 = run(p2, "SCENARIO 2 · parabolic name -> anti-parabola starter size")

    p2b = [100.0]
    for _i in range(210):
        p2b.append(p2b[-1] * 1.001)
    for _i in range(126):
        p2b.append(p2b[-1] * 1.0065)            # decays under the line by entry
    for _i in range(20):
        p2b.append(p2b[-1] * 0.995)
    for _i in range(20):
        p2b.append(p2b[-1] * 1.004)
    t2b, l2b = run(p2b, "SCENARIO 2b · gain decayed below the line -> normal staging")

    p3 = [100.0]
    for _i in range(200):
        p3.append(p3[-1] * 0.999)
    for _i in range(120):
        p3.append(p3[-1] * (1.01 if _i % 2 else 0.99))
    t3, l3 = run(p3, "SCENARIO 3 · downtrend chop -> must never enter")

    _out("\n" + "=" * 70 + "\nMECHANISM\n" + "=" * 70)
    check("S1 entered on the valley", any(t[1] == "BUY" for t in t1))
    check("S1 fired ladder trims",
          sum(1 for d, m in l1 if "TRIM rung" in m) >= 2)
    check("S1 euphoria rung tagged at 2x",
          any("euphoria protocol" in m for d, m in l1))
    check("S1 exited on structural break",
          any("EXIT structural" in m for d, m in l1))
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
          max([sum(1 for d, m in log if "sources disagree" in m)
               for log in (l1, l2, l3)]) <= 3)

    # ── regressions for the confirmed defects. Each drives the REAL path and
    #    is PAIRED WITH ITS INVERSE, so a test cannot pass merely because the
    #    setup never reached the code under test. That pairing is what caught
    #    the percentage-floor bug.
    _out("\n" + "=" * 70 + "\nFIX REGRESSIONS\n" + "=" * 70)

    s = fresh(p, 300)
    BOOK["cash"] = s.floor_amount * 1.0                   # cash IS the floor
    st = s._st("US.TEST")
    st["close_now"] = p[298]
    s.buy_one_stage("US.TEST", "US.TEST", st, p[298], 10.0, 3)
    check("floor blocks the buy when cash is AT the floor",
          not any(t[1] == "BUY" for t in BOOK["trades"])
          and any("floor" in m for d, m in BOOK["log"]))

    s = fresh(p, 300, cash=100000.0)
    st = s._st("US.TEST")
    st["close_now"] = p[298]
    s.buy_one_stage("US.TEST", "US.TEST", st, p[298], 10.0, 3)
    check("same path DOES buy when cash is above the floor",
          any(t[1] == "BUY" for t in BOOK["trades"]))

    short = [100.0]
    for _i in range(80):
        short.append(short[-1] * 1.004)
    for _i in range(14):
        short.append(short[-1] * 0.992)
    for _i in range(4):
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

    s = fresh(p, 400, qty=100.0, cost=p[398] / 2.2)       # sitting on >100%
    st = s._st("US.TEST")
    st["close_now"] = p[398]
    s._reconcile("US.TEST", "US.TEST", st)
    check("restart adopts fully-staged state", st["stages_taken"] == s.stages)
    check("restart marks already-passed rungs as fired",
          1 in st["rungs_fired"] and 2 in st["rungs_fired"])

    # ── optional: check every platform call against the manual ─────────────
    STRICT_FLOAT = ("min", "max", "abs", "floor", "ceil", "round", "power",
                    "mod", "integer_division", "rate_ratio", "math_log")
    PY_BUILTINS = ("range", "len", "str", "int", "float", "bool", "list",
                   "dict", "set", "tuple", "sorted", "sum", "enumerate", "zip",
                   "getattr", "isinstance", "super", "Exception", "type",
                   "repr", "Contract", "print", "open", "check", "run",
                   "fresh", "Strategy")

    def parse_manual(text):
        api = {}
        for m in re.finditer(r"^## ([a-z_][a-z0-9_]*)\s*$", text, re.M):
            name = m.group(1)
            section = text[m.end(): m.end() + 2500]
            sig = re.search(r"```\s*\n\s*" + re.escape(name) + r"\((.*?)\)\s*\n```",
                            section, re.S)
            if not sig:
                api.setdefault(name, {"params": None, "varargs": False})
                continue
            raw = sig.group(1).strip()
            params, varargs = [], False
            if raw:
                for part in re.split(r",(?![^\[\]{}()]*\))", raw):
                    part = part.strip()
                    if not part:
                        continue
                    if part.startswith("*"):
                        varargs = True
                        continue
                    params.append(part.split("=")[0].strip())
            api[name] = {"params": params, "varargs": varargs}
        ident = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
        for block in re.findall(r"```(.*?)```", text, re.S):
            for line in block.splitlines():
                m2 = re.match(r"^\s*(?:[\w.]+\s*=\s*)?([a-z_][a-z0-9_]*)\((.*)\)\s*$",
                              line)
                if not m2:
                    continue
                name, raw = m2.group(1), m2.group(2).strip()
                if name in api:
                    continue
                params, ok = [], True
                if raw:
                    for part in raw.split(","):
                        pn = part.split("=")[0].strip()
                        if not ident.match(pn):
                            ok = False
                            break
                        params.append(pn)
                if ok:
                    api[name] = {"params": params, "varargs": False}
        return api

    def check_calls(source, api):
        tree = ast.parse(source)
        local = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef):
                local.add(n.name)
        bad = []
        tainted = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.BoolOp):
                for v in node.value.values:
                    if isinstance(v, ast.Constant) and isinstance(v.value, int) \
                            and not isinstance(v.value, bool):
                        for tgt in node.targets:
                            if isinstance(tgt, ast.Name):
                                tainted[tgt.id] = node.lineno
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Attribute) or not isinstance(node.func, ast.Name):
                continue
            name = node.func.id
            if name in PY_BUILTINS or name in local:
                continue
            spec = api.get(name)
            if spec is None:
                bad.append("L" + str(node.lineno) + ": " + name +
                           "() is not documented in the manual")
                continue
            if name in STRICT_FLOAT:
                for i, arg in enumerate(node.args, 1):
                    for sub in ast.walk(arg):
                        if isinstance(sub, ast.Constant) and isinstance(sub.value, int) \
                                and not isinstance(sub.value, bool):
                            bad.append("L" + str(node.lineno) + ": " + name +
                                       "() arg " + str(i) + " carries int literal " +
                                       str(sub.value) + " — needs float")
                            break
                    if isinstance(arg, ast.Name) and arg.id in tainted:
                        bad.append("L" + str(node.lineno) + ": " + name + "() arg " +
                                   str(i) + " is '" + arg.id + "', made int on L" +
                                   str(tainted[arg.id]) + " — needs float")
            params = spec.get("params")
            if params is None:
                continue
            if not spec.get("varargs") and len(node.args) > len(params):
                bad.append("L" + str(node.lineno) + ": " + name + "() got " +
                           str(len(node.args)) + " positional args, manual documents " +
                           str(len(params)))
            for kw in node.keywords:
                if kw.arg and kw.arg not in params:
                    bad.append("L" + str(node.lineno) + ": " + name +
                               "() has no parameter '" + kw.arg + "'")
        return bad

    if len(sys.argv) > 1:
        _out("\n" + "=" * 70 + "\nAPI SIGNATURE CHECK vs MANUAL\n" + "=" * 70)
        try:
            manual_text = open(sys.argv[1], encoding="utf-8").read()
            own_source = open(__file__, encoding="utf-8").read()
            # Only the strategy matters: the self-test below the banner is
            # never executed by the platform.
            own_source = own_source.split("#  OFFLINE SELF-TEST")[0]
            issues = check_calls(own_source, parse_manual(manual_text))
            if issues:
                for b in issues:
                    _out("  " + b)
                allok = False
            else:
                _out("  clean — every call matches the manual's signature")
        except Exception as e:
            _out("  could not run the API check: " + str(e))
    else:
        _out("\n(pass the Algo_Manual.md path as an argument to also check "
             "every call against the manual's signatures)")

    _out("\nRESULT: " + ("all green" if allok else "FAILURES ABOVE"))
    sys.exit(0 if allok else 1)
