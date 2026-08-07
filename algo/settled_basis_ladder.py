# ═══════════════════════════════════════════════════════════════════════════
#  THE SETTLED-BASIS LADDER  ·  v2.4  ·  7 symbols
#
#  The Portfolio Machine's risk discipline, made mechanical and backtestable.
#  One file to paste: every rule, every parameter and the whole rationale are
#  documented in this header, so there is one place to keep current.
#
#  ┌─────────────────────────────────────────────────────────────────────┐
#  │ PASTE THIS WHOLE FILE INTO THE STRATEGY EDITOR.                     │
#  │                                                                     │
#  │ The editor allows NO top-level code — only the strategy class and   │
#  │ comments. So this file is exactly that: documentation, then the     │
#  │ class. The offline test harness lives in algo/dryrun_sim.py, which  │
#  │ never gets pasted anywhere.                                         │
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
#   floor_amount      40000  fixed reserve never deployed (Charter §V).
#                            DENOMINATED IN USD — the strategy values the
#                            book with Currency.USD throughout. If the
#                            backtest's Initial Capital is set in HKD, this
#                            number is still USD: 1,000,000 HKD is roughly
#                            128,000 USD, so a 40,000 floor is ~31% of it.
#                            Set it to the reserve you actually intend.
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
        # Dollars committed during the CURRENT pass. total_cash() does not
        # drop until an order fills, so with several symbols evaluated in one
        # pass each would size against the same untouched cash and the book
        # could commit far more than it holds. Reset every pass.
        self.committed = 0.0

    def trigger_symbols(self):
        # ONE SLOT PER SYMBOL YOU INTEND TO TEST — no more.
        #
        # The backtest dialog will NOT enable "Next" while any declared slot
        # is empty, so a spare slot is not free: it blocks the run. To change
        # the count, edit BOTH this list and the one in _symbols() below, or
        # a slot is declared and never evaluated. The platform allows 50.
        self.sym1 = declare_trig_symbol()
        self.sym2 = declare_trig_symbol()
        self.sym3 = declare_trig_symbol()
        self.sym4 = declare_trig_symbol()
        self.sym5 = declare_trig_symbol()
        self.sym6 = declare_trig_symbol()
        self.sym7 = declare_trig_symbol()

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
        for s in (self.sym1, self.sym2, self.sym3, self.sym4,
                  self.sym5, self.sym6, self.sym7):
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
        self.committed = 0.0
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
        # Subtract what earlier symbols already committed in this same pass:
        # limit orders do not reduce total_cash until they fill.
        cash_above_floor = cash_now - floor_dollars - self.committed
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
        self.committed = self.committed + qty * px

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
        """Highest HIGH over the lookback, from closed bars.

        COST: one call per bar of `high_lookback`, per FLAT symbol, per day
        (a held symbol never runs this). With a large basket that adds up —
        `high_lookback` is the knob if a backtest feels slow.

        Deliberately NOT bar_custom: that aggregates on a FIXED GRID, so it
        answers "the high of a 60-day block" rather than "the high of the last
        60 bars". It would be one call instead of sixty and quietly change
        what a valley means."""
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
