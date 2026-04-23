-- Recreate latest_analysis + latest_signals views so they pick up event_impacts.
-- Postgres views freeze SELECT * at creation time, so adding a column to the
-- underlying table doesn't auto-propagate.
DROP VIEW IF EXISTS latest_analysis;
CREATE VIEW latest_analysis AS
SELECT DISTINCT ON (ticker) *
FROM analysis
ORDER BY ticker, created_at DESC;

DROP VIEW IF EXISTS latest_signals;
CREATE VIEW latest_signals AS
SELECT DISTINCT ON (ticker, scout) *
FROM signals
ORDER BY ticker, scout, created_at DESC;
