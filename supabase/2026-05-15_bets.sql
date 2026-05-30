-- ═══════════════════════════════════════════════════════════════
-- BETS + NOTIFICATIONS + EVENT LOG
-- 2026-05-15  (BUILD_PLAN_v2 Phase 1.3)
--
-- A `bet` is a recorded human judgment with falsification condition.
-- It is the unit that lets the system tell whether the methodology
-- is producing useful decisions over time. T+30/60/90 checkpoints
-- are written by a daily cron.
--
-- Notifications are auto-generated from judgment-card conversation
-- and from cron-scanned conditions (price, catalyst, thesis-break).
--
-- Event log is the system-wide audit trail. Every analysis run,
-- bet creation, notification fire, kill check, and checkpoint
-- writes an event_log row. This is the data source for the
-- Logs tab in the new frontend.
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS bets (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ticker              text NOT NULL,
    socratic_id         bigint REFERENCES socratic_analyses(id) ON DELETE SET NULL,

    -- Entry
    entry_price         double precision NOT NULL,
    entry_date          timestamptz NOT NULL DEFAULT now(),

    -- Targets / sizing
    target_low          double precision,
    target_high         double precision,
    downside_price      double precision,

    -- Default placeholder is 5% per user_position_sizing_discipline,
    -- but UI may write anything the user types.
    position_pct        double precision NOT NULL DEFAULT 5.0,

    -- Decision payload
    judgment_text       text,                            -- what the user typed in the card
    falsification       text NOT NULL,                   -- required; non-empty
    judgment_mode       text CHECK (judgment_mode IN ('quick_select','custom','conversational') OR judgment_mode IS NULL),

    -- Lifecycle
    status              text NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','settled_win','settled_loss','cancelled')),

    -- T+ checkpoints (filled by checkpoint_check cron)
    t30_date            date,
    t30_price           double precision,
    t60_date            date,
    t60_price           double precision,
    t90_date            date,
    t90_price           double precision,
    settled_at          timestamptz,
    settled_reason      text,                            -- 'reached_target' | 'hit_downside' | 'kill_triggered' | 't90_lapse'

    created_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (length(falsification) > 0)
);

CREATE INDEX IF NOT EXISTS idx_bets_ticker            ON bets (ticker);
CREATE INDEX IF NOT EXISTS idx_bets_status            ON bets (status);
CREATE INDEX IF NOT EXISTS idx_bets_entry_date        ON bets (entry_date);
CREATE INDEX IF NOT EXISTS idx_bets_socratic          ON bets (socratic_id);

-- Now that bets exists, link model_accuracy.bet_id to it.
-- (NOT NULL is intentional — model_accuracy rows only exist for settled bets.)
ALTER TABLE model_accuracy
    ADD CONSTRAINT fk_model_accuracy_bet
    FOREIGN KEY (bet_id) REFERENCES bets(id) ON DELETE CASCADE;

-- ═══════════════════════════════════════════════════════════════
-- NOTIFICATIONS — auto-generated from judgment card + cron evals
-- 2026-05-15
--
-- Five notification types per BUILD_PLAN_v2 §4.9:
--   price_alert | catalyst | thesis_break | checkpoint | opportunity
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS notifications (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bet_id              bigint REFERENCES bets(id) ON DELETE CASCADE,
    ticker              text NOT NULL,
    type                text NOT NULL CHECK (type IN
                        ('price_alert','catalyst','thesis_break','checkpoint','opportunity')),

    -- Condition that fires this notification.
    -- price_alert:   {"op":"<="|">=", "price": number}
    -- catalyst:      {"event":"earnings","date":"2026-08-14"}
    -- thesis_break:  {"event":"competitor_announcement","keywords":["KLA","3D metrology"]}
    -- checkpoint:    {"t":30|60|90, "date":"2026-06-14"}
    -- opportunity:   {"pullback_pct": number, "no_fundamental_change": true}
    trigger_condition   jsonb NOT NULL,

    message             text NOT NULL,                   -- pre-rendered text
    severity            text NOT NULL DEFAULT 'info'
                        CHECK (severity IN ('urgent','check_in','info')),

    -- Lifecycle
    is_triggered        boolean NOT NULL DEFAULT false,
    triggered_at        timestamptz,
    is_dismissed        boolean NOT NULL DEFAULT false,
    dismissed_at        timestamptz,
    dismiss_reason      text,                            -- 'acted_on' | 'irrelevant' | 'manual'

    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notif_ticker           ON notifications (ticker);
CREATE INDEX IF NOT EXISTS idx_notif_pending          ON notifications (is_triggered, is_dismissed)
    WHERE is_triggered = false AND is_dismissed = false;
CREATE INDEX IF NOT EXISTS idx_notif_bet              ON notifications (bet_id);

-- ═══════════════════════════════════════════════════════════════
-- EVENT LOG — system-wide audit trail (Logs tab data source)
-- 2026-05-15
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS event_log (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type          text NOT NULL,                   -- 'analysis_run','bet_created','notification_triggered','scout_completed','checkpoint_recorded','kill_check_fired',...
    ticker              text,                            -- nullable; some events are system-wide
    details             jsonb DEFAULT '{}'::jsonb,
    severity            text NOT NULL DEFAULT 'info'
                        CHECK (severity IN ('debug','info','warn','error')),
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_event_type_time        ON event_log (event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_event_ticker_time      ON event_log (ticker, created_at DESC) WHERE ticker IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_event_severity         ON event_log (severity, created_at DESC) WHERE severity IN ('warn','error');
