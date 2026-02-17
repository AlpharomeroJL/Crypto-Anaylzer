"""Verify universe allowlist and churn tables after 3–5 refreshes. Final check for production-stable (research-grade) universe.

Interpretation:
- Allowlist: want 3+ rows like (ts1, N, universe), (ts2, N, universe), (ts3, N, universe) — stable N across refreshes.
- Churn: at latest ts_utc ideally 0–1 add and 0–1 remove (e.g. ('add', 'churn_replace', 0–1), ('remove', 'churn_replace', 0–1)) or no churn.
- Thrash: 2–4 adds and 2–4 removes every refresh → tighten max_churn_pct, raise thresholds, or increase min_persistence_refreshes.
- Old rows may show action='added'/'removed'; mixed history is fine. Optional migration: UPDATE universe_churn_log SET action='add' WHERE action='added'; (same for remove/removed).
"""
import sqlite3

conn = sqlite3.connect("dex_data.sqlite")

print("allowlist last 5 refreshes:")
print(conn.execute("""
SELECT ts_utc, COUNT(*) n, MIN(source) src
FROM universe_allowlist
GROUP BY ts_utc
ORDER BY ts_utc DESC
LIMIT 5
""").fetchall())

latest = conn.execute("SELECT MAX(ts_utc) FROM universe_churn_log").fetchone()[0]
print("latest churn ts:", latest)
print(conn.execute("""
SELECT action, reason, COUNT(*) n
FROM universe_churn_log
WHERE ts_utc = ?
GROUP BY action, reason
ORDER BY n DESC
""", (latest,)).fetchall())

conn.close()
