-- ═══════════════════════════════════════════════════════════════
-- CHAT HISTORY + LESSONS
-- 2026-05-15  (BUILD_PLAN_v2 Phase 1.4)
--
-- chat_history backs the Ask tab and judgment-card conversational
-- follow-ups. session_id groups messages from one conversation;
-- mode tags whether the conversation was tactical / discovery /
-- thesis. ticker is set when the conversation is about a specific
-- name (the judgment card always sets it).
--
-- lessons is the slow-growing knowledge base — typed observations
-- about what worked or didn't. The 10 seed lessons from BUILD_PLAN_v2
-- §Seed Data are inserted as system-source rows below.
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS chat_history (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id      uuid NOT NULL,
    role            text NOT NULL CHECK (role IN ('user','assistant','system')),
    content         text NOT NULL,
    mode            text CHECK (mode IN ('tactical','discovery','thesis','judgment_card') OR mode IS NULL),
    ticker          text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_session_time      ON chat_history (session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_ticker_time       ON chat_history (ticker, created_at DESC) WHERE ticker IS NOT NULL;

-- ═══════════════════════════════════════════════════════════════
-- LESSONS — the slow-growing knowledge base
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS lessons (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lesson          text NOT NULL,
    source          text,                                -- 'seed' | bet_id reference | thesis_id reference
    counter_example text,                                -- a case where this lesson didn't apply
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- Seed 10 lessons from BUILD_PLAN_v2 (idempotent)
INSERT INTO lessons (lesson, source) VALUES
    ('LLMs analyze, humans judge — keep the human in the loop for frame selection.', 'seed'),
    ('Flexibility over rules — consensus awareness is information, not a gate.',       'seed'),
    ('Two frameworks: chokepoint capture + operating leverage. Use both.',             'seed'),
    ('Trace from physical reality up, not from market commentary down.',               'seed'),
    ('Every bet is falsifiable — the falsification field is non-negotiable.',          'seed'),
    ('Rough magnitude not false precision — target ranges, not point estimates.',      'seed'),
    ('Research factual questions, never punt them to the human.',                      'seed'),
    ('Always pull ≥6 quarter revenue trajectory before assessing growth.',             'seed'),
    ('A stock can belong to multiple revolutions simultaneously.',                     'seed'),
    ('The judgment card is conversational, not a static form.',                        'seed')
ON CONFLICT DO NOTHING;
