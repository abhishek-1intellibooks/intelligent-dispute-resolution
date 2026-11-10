"""The event envelope and the transactional outbox (Listing 14.1).

`Event` and `transition` are the listing. The code is written against a
psycopg-style connection (``conn.transaction()``, ``%s`` placeholders), as for
PostgreSQL 16. So that the chapter runs without a database server, this module
also provides `LocalConnection`, a thin adapter over the standard library's
sqlite3 with the same two methods, the schema, an outbox relay and an
in-memory, case-partitioned event log.

Run:  python events.py
"""
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class Event:
    type: str                         # e.g. "evidence.scored"
    case_id: str
    data: dict
    producer: str
    schema_version: int = 1
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())


class StaleState(Exception):
    pass


def transition(conn, case_id, expected, new_state, event):
    """Change the case state and record its event in ONE transaction."""
    with conn.transaction():
        changed = conn.execute(
            "UPDATE cases SET state = %s, version = version + 1 "
            "WHERE case_id = %s AND state = %s",
            (new_state, case_id, expected)).rowcount
        if changed != 1:
            raise StaleState(f"{case_id} is no longer {expected}")
        conn.execute(
            "INSERT INTO outbox (event_id, case_id, type, payload) "
            "VALUES (%s, %s, %s, %s)",
            (event.event_id, case_id, event.type, json.dumps(asdict(event))))


# --------------------------------------------------------------------------
# Local stand-ins so the patterns run without PostgreSQL or Kafka.
# --------------------------------------------------------------------------
import sqlite3  # noqa: E402
import zlib  # noqa: E402
from collections import defaultdict  # noqa: E402
from contextlib import contextmanager  # noqa: E402

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    state   TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS outbox (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id   TEXT UNIQUE NOT NULL,
    case_id    TEXT NOT NULL,
    type       TEXT NOT NULL,
    payload    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at    TEXT
);
CREATE TABLE IF NOT EXISTS processed (
    consumer TEXT NOT NULL,
    event_id TEXT NOT NULL,
    PRIMARY KEY (consumer, event_id)
);
"""


class LocalConnection:
    """sqlite3 behind the two methods the listings use.

    ``transaction()`` opens a transaction (a savepoint when nested) that commits
    on success and rolls back on any exception; ``execute()`` accepts ``%s``
    placeholders and returns a cursor with ``rowcount``.
    """

    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.db.executescript(SCHEMA)
        self._depth = 0

    @contextmanager
    def transaction(self):
        name = f"sp{self._depth}"
        self.db.execute("BEGIN" if self._depth == 0 else f"SAVEPOINT {name}")
        self._depth += 1
        try:
            yield self
        except BaseException:
            self._depth -= 1
            self.db.execute("ROLLBACK" if self._depth == 0 else f"ROLLBACK TO {name}")
            if self._depth:
                self.db.execute(f"RELEASE {name}")
            raise
        else:
            self._depth -= 1
            self.db.execute("COMMIT" if self._depth == 0 else f"RELEASE {name}")

    def execute(self, sql, params=()):
        return self.db.execute(sql.replace("%s", "?"), params)

    def query(self, sql, params=()):
        return self.execute(sql, params).fetchall()


class EventLog:
    """An in-memory, partitioned log: events of one case keep their order."""

    def __init__(self, partitions=6):
        self.partitions = [[] for _ in range(partitions)]

    def partition_for(self, case_id):
        return zlib.crc32(case_id.encode()) % len(self.partitions)

    def publish(self, key, value):
        self.partitions[self.partition_for(key)].append(value)

    def messages(self):
        for p in self.partitions:
            yield from p


def relay(conn, log, fail_after=None):
    """Publish unsent outbox rows in order, then mark each sent.

    If the process dies between publishing and marking (simulated with
    ``fail_after``), the row is published again on the next run: delivery is
    at least once, which is why consumers must be idempotent.
    """
    rows = conn.query("SELECT seq, event_id, case_id, payload FROM outbox "
                      "WHERE sent_at IS NULL ORDER BY seq")
    published = 0
    for seq, event_id, case_id, payload in rows:
        log.publish(case_id, payload)
        published += 1
        if fail_after is not None and published > fail_after:
            raise ConnectionError("relay crashed before marking the event sent")
        conn.execute("UPDATE outbox SET sent_at = CURRENT_TIMESTAMP WHERE seq = %s", (seq,))
    return published


def open_case(conn, case_id, state="RECEIVED"):
    with conn.transaction():
        conn.execute("INSERT INTO cases (case_id, state) VALUES (%s, %s)", (case_id, state))
        ev = Event("claim.received", case_id, {"state": state}, producer="intake")
        conn.execute("INSERT INTO outbox (event_id, case_id, type, payload) VALUES (%s, %s, %s, %s)",
                     (ev.event_id, case_id, ev.type, json.dumps(asdict(ev))))
    return ev


def demo():
    conn = LocalConnection()
    log = EventLog()
    open_case(conn, "C-2025-118204")
    transition(conn, "C-2025-118204", "RECEIVED", "INVESTIGATING",
               Event("case.state_changed", "C-2025-118204",
                     {"from": "RECEIVED", "to": "INVESTIGATING"}, producer="case"))
    # A second service acting on a stale view of the case changes nothing.
    try:
        transition(conn, "C-2025-118204", "RECEIVED", "CLOSED",
                   Event("case.state_changed", "C-2025-118204",
                         {"from": "RECEIVED", "to": "CLOSED"}, producer="agent"))
    except StaleState as exc:
        print("StaleState:", exc)
    state, version = conn.query("SELECT state, version FROM cases")[0]
    n_outbox = conn.query("SELECT COUNT(*) FROM outbox")[0][0]
    print(f"case state {state}, version {version}; outbox rows {n_outbox} (no row for the stale attempt)")
    # The relay crashes after publishing one event, then runs again.
    try:
        relay(conn, log, fail_after=0)
    except ConnectionError as exc:
        print("relay:", exc)
    relay(conn, log)
    types = [json.loads(m)["type"] for m in log.messages()]
    print(f"published {len(types)} messages for 2 events (one duplicate): {types}")


if __name__ == "__main__":
    demo()
