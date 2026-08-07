# ═══════════════════════════════════════════════════════════════════════════
#  THE SETTLED-BASIS LADDER
#  The Portfolio Machine's risk discipline, made mechanical and backtestable.
#
#  It encodes, in order of importance:
#    1. LAW 2 — decisions are made ONLY on closed bars. On this platform
#       `select=1` is the bar still forming; `select=2` is the last CLOSED
#       bar. Reading select=1 is exactly the INTC $91.63 -> $92.52 flip that
#       the whole constitution was written around, in platform form.
#    2. TWO-SOURCE CONFIRMATION — an entry needs the structural regime AND a
#       turn in the valley to agree. Disagreement means do nothing, and say so.
#    3. THE FLOOR — a fixed share of net assets is never deployable. Ever.
#    4. ANTI-PARABOLA — a name that doubled in six months gets starter size
#       only. Not a veto on owning it; a veto on owning much of it.
#    5. VALLEY ENTRY — buys weakness inside strength, never a breakout into
#       euphoria. ("Drawdowns are the queue, not the hazard.")
#    6. STAGED THIRDS — positions are built, never taken in one clip.
#    7. PRE-DECLARED LADDERS — exit rungs written in advance, on a calm day.
#       Each fires once; the next arms behind it.
#    8. DATED SIGNPOST — a time stop. A thesis gets a window; if it made no
#       progress in that window, it is over regardless of the story.
#    9. STRUCTURAL STOP — a settled close below the trend line is a thesis
#       break, not noise.
#
#  What it CANNOT do: research. It cannot read an order book, a capex guide,
#  or a qualification slip. It is the guard, not the analyst. Judge it on
#  drawdown and worst-trade, not on CAGR alone. See algo/README.md.
# ═══════════════════════════════════════════════════════════════════════════


class Strategy(StrategyBase):

    # ── setup ──────────────────────────────────────────────────────────────
    def initialize(self):
        declare_strategy_type(AlgoStrategyType.SECURITY)
        self.trigger_symbols()
        self.custom_indicator()
        self.global_variables()

        # Machine-owned state. Keyed by symbol code so several names can run
        # under one strategy without their ladders colliding.
        self.state = {}
        self.last_run_day = ""

    def trigger_symbols(self):
        # Slot 1 is required; 2-4 are optional. Unconfigured slots are skipped
        # loudly rather than crashing the run.
        self.sym1 = declare_trig_symbol()
        self.sym2 = declare_trig_symbol()
        self.sym3 = declare_trig_symbol()
        self.sym4 = declare_trig_symbol()

    def custom_indicator(self):
        pass

    def global_variables(self):
        # ── the floor and the size caps (Charter §V) ──
        self.floor_pct = show_variable(20, GlobalType.INT)          # % never deployed
        self.max_position_pct = show_variable(25, GlobalType.INT)   # % of deployable, per name
        self.stages = show_variable(3, GlobalType.INT)              # staged thirds

        # ── the structural regime (is the thesis intact?) ──
        self.trend_period = show_variable(200, GlobalType.INT)
        self.fast_period = show_variable(50, GlobalType.INT)

        # ── the valley (entry only into weakness within strength) ──
        self.pullback_pct = show_variable(8, GlobalType.INT)        # min drop from recent high
        self.high_lookback = show_variable(60, GlobalType.INT)      # bars defining "recent high"

        # ── anti-parabola (Charter §V sizing law) ──
        self.parabola_pct = show_variable(100, GlobalType.INT)      # 6-month gain -> starter only
        self.parabola_lookback = show_variable(126, GlobalType.INT) # ~6 months of sessions

        # ── the pre-declared exit ladder ──
        self.rung1_pct = show_variable(50, GlobalType.INT)
        self.rung1_trim = show_variable(20, GlobalType.INT)
        self.rung2_pct = show_variable(100, GlobalType.INT)         # the euphoria protocol: 2x cost
        self.rung2_trim = show_variable(25, GlobalType.INT)
        self.rung3_pct = show_variable(200, GlobalType.INT)
        self.rung3_trim = show_variable(25, GlobalType.INT)

        # ── the dated signpost (time stop) and the backstop ──
        self.horizon_days = show_variable(252, GlobalType.INT)
        self.min_progress_pct = show_variable(10, GlobalType.INT)
        self.hard_stop_pct = show_variable(30, GlobalType.INT)

        # ── law 2 switch: leave TRUE. False exists only so a backtest can
        #    MEASURE what peeking at unsettled prices is worth (README test 2).
        self.use_settled = show_variable(True, GlobalType.BOOL)

    # ── helpers ────────────────────────────────────────────────────────────

    def _code(self, symbol):
        try:
            return str(get_symbol_code(symbol=symbol))
        except Exception:
            return str(symbol)

    def _sel(self, offset=0):
        """Bar selector. offset=0 is the reference bar.

        LAW 2 IN ONE LINE: settled mode starts at select=2, the last CLOSED
        bar. select=1 is the bar still forming — a price that can still move
        before it becomes a fact. Every flip incident this system remembers
        came from treating a select=1 number as a select=2 number.
        """
        base = 2 if self.use_settled else 1
        return base + offset

    def _dp(self, value, places=1):
        """Round to N decimals using the platform's SINGLE-ARGUMENT round().

        The platform's round(value) takes no precision argument — Python's
        two-argument form is rejected by the editor. Scale, round, unscale.
        Kept as one helper so every log line formats the same way and a future
        edit cannot reintroduce round(x, 2) by habit.
        """
        if value is None:
            return 0.0
        factor = 1.0
        for _ in range(places):
            factor = factor * 10.0
        return round(value * factor) / factor

    def _st(self, code):
        if code not in self.state:
            self.state[code] = {
                "rungs_fired": [],   # which pre-declared rungs already trimmed
                "stages_taken": 0,   # how many thirds are in
                "bars_held": 0,      # the dated-signpost clock
                "starter_only": False,
                "last_note": "",     # de-dupe the daily no-trade reason
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

    # ── the daily gate ─────────────────────────────────────────────────────

    def handle_data(self):
        """One decision per calendar day, on closed bars only.

        The guard below means the strategy behaves identically whether it is
        triggered on daily bars, hourly bars, or every N seconds: it decides
        once a day, on settled data. An intraday trigger cannot make it act
        on an intraday number — which is the entire law-2 discipline.
        """
        today = str(device_time().date())
        if today == self.last_run_day:
            return
        self.last_run_day = today

        for symbol in self._symbols():
            try:
                self.evaluate_one(symbol)
            except Exception as e:
                print("[error] " + self._code(symbol) + " skipped: " + str(e))

    # ── one name, one day ──────────────────────────────────────────────────

    def evaluate_one(self, symbol):
        code = self._code(symbol)
        st = self._st(code)

        close = bar_close(symbol=symbol, bar_type=BarType.K_DAY,
                          select=self._sel(0), session_type=THType.RTH)
        prev = bar_close(symbol=symbol, bar_type=BarType.K_DAY,
                         select=self._sel(1), session_type=THType.RTH)
        trend = ma(symbol=symbol, period=self.trend_period, bar_type=BarType.K_DAY,
                   data_type=DataType.CLOSE, select=self._sel(0), session_type=THType.RTH)
        fast = ma(symbol=symbol, period=self.fast_period, bar_type=BarType.K_DAY,
                  data_type=DataType.CLOSE, select=self._sel(0), session_type=THType.RTH)

        if close is None or trend is None or close <= 0 or trend <= 0:
            if st["last_note"] != "gap":
                print("[gap] " + code + ": no settled price/trend on file — no "
                      "action until there is (a declared gap, never a guess)")
                st["last_note"] = "gap"
            return

        qty = position_holding_qty(symbol=symbol)
        if qty and qty > 0:
            st["bars_held"] = st["bars_held"] + 1
            self.manage_position(symbol, code, st, close, trend)
        else:
            if st["stages_taken"] > 0:      # flat again: the episode is closed
                self.reset_episode(code, st)
            self.consider_entry(symbol, code, st, close, prev, trend, fast)

    # ── exits come first: protecting capital outranks deploying it ─────────

    def manage_position(self, symbol, code, st, close, trend):
        qty = position_holding_qty(symbol=symbol)
        pl = position_pl_ratio(symbol=symbol, cost_price_model=CostPriceModel.AVG)
        pl_pct = (pl or 0.0) * 100.0

        # 1 · STRUCTURAL STOP — a settled close below the trend is a thesis
        #     break. Not a wobble, not noise: the structure that justified
        #     owning it is gone.
        if close < trend:
            print("[EXIT structural] " + code + ": settled close " + str(close) +
                  " < trend(" + str(self.trend_period) + ") " + str(self._dp(trend, 2)) +
                  " — thesis structure broken, full exit")
            place_market(symbol=symbol, qty=qty, side=OrderSide.SELL,
                         time_in_force=TimeInForce.DAY)
            self.reset_episode(code, st)
            return

        # 2 · HARD STOP — the backstop against permanent loss. The floor is
        #     sacred; a single name may not be the reason it is touched.
        if pl_pct <= -self.hard_stop_pct:
            print("[EXIT hard-stop] " + code + ": " + str(self._dp(pl_pct, 1)) +
                  "% — permanent-loss backstop, full exit")
            place_market(symbol=symbol, qty=qty, side=OrderSide.SELL,
                         time_in_force=TimeInForce.DAY)
            self.reset_episode(code, st)
            return

        # 3 · DATED SIGNPOST — the thesis got a window and did nothing with
        #     it. A position that has not worked in a year is not "early";
        #     it is an opinion being funded by hope. (rules.adjudicate_signposts)
        if st["bars_held"] >= self.horizon_days and pl_pct < self.min_progress_pct:
            print("[EXIT signpost] " + code + ": " + str(st["bars_held"]) +
                  " sessions held, only " + str(self._dp(pl_pct, 1)) +
                  "% — the window closed without progress, exit")
            place_market(symbol=symbol, qty=qty, side=OrderSide.SELL,
                         time_in_force=TimeInForce.DAY)
            self.reset_episode(code, st)
            return

        # 4 · THE PRE-DECLARED LADDER — every rung was written on a calm day,
        #     in advance. Rung 2 IS the euphoria protocol (2x cost). The
        #     strategy climbs the ladder; it never invents a rung.
        rungs = [(1, self.rung1_pct, self.rung1_trim),
                 (2, self.rung2_pct, self.rung2_trim),
                 (3, self.rung3_pct, self.rung3_trim)]
        for rung_id, level, trim in rungs:
            if rung_id in st["rungs_fired"]:
                continue
            if pl_pct >= level:
                slice_qty = floor(qty * trim / 100.0)
                if slice_qty >= 1:
                    tag = " (euphoria protocol: 2x cost)" if level >= 100 else ""
                    print("[TRIM rung " + str(rung_id) + "] " + code + ": +" +
                          str(self._dp(pl_pct, 1)) + "% >= " + str(level) + "% — selling " +
                          str(trim) + "% (" + str(slice_qty) + " sh)" + tag)
                    place_market(symbol=symbol, qty=slice_qty, side=OrderSide.SELL,
                                 time_in_force=TimeInForce.DAY)
                    st["rungs_fired"].append(rung_id)
                    return          # one action per name per day
                else:
                    st["rungs_fired"].append(rung_id)   # position too small to slice

        # 5 · STAGED THIRDS — add only while the structure holds and the name
        #     has proven something since the last stage.
        self.consider_add(symbol, code, st, close, trend)

    # ── entries: two sources must agree, or nothing happens ────────────────

    def consider_entry(self, symbol, code, st, close, prev, trend, fast):
        # SOURCE 1 — structural regime. Is there a trend worth joining?
        regime_ok = (close > trend) and (fast is not None and fast > trend)

        # SOURCE 2 — the valley and its turn. We buy weakness INSIDE strength,
        #     never a breakout into euphoria (CONSTITUTION §IV: drawdowns are
        #     the queue, not the hazard).
        high = self.recent_high(symbol)
        if high is None or high <= 0:
            print("[gap] " + code + ": no lookback high — no action")
            return
        drawdown_pct = (1.0 - close / high) * 100.0
        deep_enough = drawdown_pct >= self.pullback_pct
        turning = prev is not None and close > prev
        valley_ok = deep_enough and turning

        if not (regime_ok or valley_ok):
            return                                  # quiet: nothing to say

        # LAW 3 IN SPIRIT — the two sources disagree. Flag it, never average
        # it, never act on the half that agrees with what you'd like to do.
        if regime_ok != valley_ok:
            reason = ("trend intact but no valley (would be chasing)"
                      if regime_ok else
                      "valley present but structure broken (falling knife)")
            # Say it once per state change, not once per day: an unchanged
            # standing reason repeated 200 times buries the decisions that
            # matter. Silence is a violation; repetition is camouflage.
            if st["last_note"] != reason:
                print("[no-trade] " + code + ": sources disagree — " + reason)
                st["last_note"] = reason
            return
        st["last_note"] = ""

        # ANTI-PARABOLA (Charter §V) — this does not forbid owning a name that
        # doubled. It forbids owning MUCH of it. Starter size, permanently,
        # for this episode.
        gain6m = self.six_month_gain(symbol, close)
        if gain6m is not None and gain6m >= self.parabola_pct:
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
        """Adding to a winner is still an entry decision: the structure must
        hold, and the name must have moved up since the last stage. Averaging
        DOWN is not in this strategy — that is how a small mistake becomes
        the reason the floor gets touched."""
        max_stages = 1 if st["starter_only"] else self.stages
        if st["stages_taken"] >= max_stages:
            return
        if close <= trend:
            return
        cost = position_cost(symbol=symbol, cost_price_model=CostPriceModel.AVG)
        if cost is None or cost <= 0 or close <= cost * 1.05:
            return                                  # no proof yet; wait
        self.buy_one_stage(symbol, code, st, close, None, max_stages)

    # ── sizing: the floor is untouchable and the cap only clamps down ──────

    def buy_one_stage(self, symbol, code, st, close, drawdown_pct, max_stages):
        equity = net_asset(currency=Currency.USD)
        if equity is None or equity <= 0:
            print("[gap] " + code + ": no net asset value — no sizing possible")
            return

        # THE FLOOR (Charter §V): sacred, never deployed, not a buffer to be
        # borrowed from on a good idea.
        deployable = equity * (1.0 - self.floor_pct / 100.0)
        full_target = deployable * (self.max_position_pct / 100.0)
        stage_value = full_target / max_stages

        cash_available = total_cash(currency=Currency.USD) or 0.0
        spendable = min(stage_value, cash_available * 1.0)   # both args float (platform type-checks)
        if spendable <= 0:
            print("[no-trade] " + code + ": floor and cash leave nothing "
                  "deployable — the floor is not a buffer")
            return

        qty = floor(spendable / close)
        lot = lot_size(symbol=symbol) or 1.0
        if lot > 1:
            qty = floor(qty / lot) * lot
        if qty < 1:
            print("[no-trade] " + code + ": stage size below one tradable unit")
            return

        why = ("valley -" + str(self._dp(drawdown_pct, 1)) + "% from high, turning"
               if drawdown_pct is not None else "adding on proof above cost")
        print("[BUY stage " + str(st["stages_taken"] + 1) + "/" + str(max_stages) +
              "] " + code + ": " + str(qty) + " sh @ ~" + str(close) +
              " — " + why + (" [STARTER ONLY]" if st["starter_only"] else ""))
        place_market(symbol=symbol, qty=qty, side=OrderSide.BUY,
                     time_in_force=TimeInForce.DAY)
        st["stages_taken"] = st["stages_taken"] + 1

    # ── measurements, all on closed bars ───────────────────────────────────

    def recent_high(self, symbol):
        high = None
        for i in range(0, self.high_lookback):
            c = bar_close(symbol=symbol, bar_type=BarType.K_DAY,
                          select=self._sel(i), session_type=THType.RTH)
            if c is not None and c > 0:
                if high is None or c > high:
                    high = c
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
        rung one for the NEXT episode — exactly how the euphoria protocol is
        reset by archiving its consult."""
        st["rungs_fired"] = []
        st["stages_taken"] = 0
        st["bars_held"] = 0
        st["starter_only"] = False
        st["last_note"] = ""
