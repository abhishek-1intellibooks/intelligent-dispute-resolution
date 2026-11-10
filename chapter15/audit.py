"""A hash-chained, tamper-evident audit log (Listing 15.4).

AuditLog and verify are the listing. MemoryStore and WriteOnceCheckpoints are
local stand-ins for the database table and the write-once object storage that
hold the records and the checkpoints in production.
"""
import hashlib
import json

GENESIS = "0" * 64


def _digest(prev, record):
    body = json.dumps(record, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev + body).encode()).hexdigest()


class AuditLog:
    def __init__(self, store, checkpoints, every=10_000):
        self.store, self.checkpoints, self.every = store, checkpoints, every
        self.prev, self.count = store.last_hash() or GENESIS, store.count()

    def append(self, record):
        h = _digest(self.prev, record)
        self.store.write({"seq": self.count, "record": record,
                          "prev": self.prev, "hash": h})
        self.prev, self.count = h, self.count + 1
        if self.count % self.every == 0:            # anchor outside the database
            self.checkpoints.put(self.count, h)     # write-once object storage
        return h


def verify(entries, checkpoints=None):
    """Return the position of the first broken record, or None."""
    prev = GENESIS
    for i, e in enumerate(entries):
        if e["prev"] != prev or _digest(prev, e["record"]) != e["hash"]:
            return i
        if checkpoints and checkpoints.get(i + 1) not in (None, e["hash"]):
            return i
        prev = e["hash"]
    return None


class MemoryStore:
    """The audit table: an append-only list of entries."""

    def __init__(self):
        self.entries = []

    def write(self, entry):
        self.entries.append(entry)

    def last_hash(self):
        return self.entries[-1]["hash"] if self.entries else None

    def count(self):
        return len(self.entries)


class WriteOnceCheckpoints(dict):
    """Checkpoints that cannot be overwritten, like object-lock storage."""

    def put(self, count, h):
        if count in self:
            raise PermissionError(f"checkpoint {count} is write-once")
        self[count] = h

    def __bool__(self):          # an empty checkpoint store still counts as present
        return True
