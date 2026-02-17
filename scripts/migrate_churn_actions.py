"""One-off: normalize universe_churn_log action from added/removed to add/remove."""
import sqlite3

conn = sqlite3.connect("dex_data.sqlite")
conn.execute("UPDATE universe_churn_log SET action='add' WHERE action='added'")
conn.execute("UPDATE universe_churn_log SET action='remove' WHERE action='removed'")
conn.commit()
conn.close()
print("Done.")
