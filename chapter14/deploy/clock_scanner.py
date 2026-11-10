"""Clock scanner, run every minute by the clock-scanner CronJob (Chapter 14).

Deadlines are data: this job reads the clocks table, finds open clocks due
within two business days, and emits clock.at_risk for each, through the
outbox like any other state change. A restart or a release loses nothing,
because nothing is held in memory between runs.
"""
import os
from datetime import date

from handlers import add_business_days, emit

AT_RISK_BUSINESS_DAYS = 2


def scan(conn, today=None):
    today = today or date.today()
    horizon = add_business_days(today, AT_RISK_BUSINESS_DAYS)
    with conn.transaction():
        rows = conn.execute(
            "SELECT case_id, clock, due_on FROM clocks "
            "WHERE stopped_at IS NULL AND due_on <= %s", (horizon,)).fetchall()
        for case_id, clock, due_on in rows:
            emit(conn, case_id, "clock.at_risk", {"clock": clock, "due_on": str(due_on)}, "case")
    return len(rows)


if __name__ == "__main__":
    import psycopg  # lazy: only inside the container
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        print({"at_risk": scan(conn)})
