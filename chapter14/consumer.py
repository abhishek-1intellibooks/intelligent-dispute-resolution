"""An idempotent consumer with retries and a dead-letter queue (Listing 14.2).

`handle` is the listing. The rest of the module supplies what it needs to run
locally: a `Message` with a delivery-attempt counter, a `DeadLetterQueue`, a
`deliver` loop that redelivers with backoff, and a demonstration in which the
log delivers every event twice and one handler keeps failing.

Run:  python consumer.py
"""
import json

MAX_ATTEMPTS = 5


class Retryable(Exception):
    """A temporary failure: a timeout, a throttled provider."""


def handle(conn, message, handler, dead_letter):
    event = json.loads(message.value)
    try:
        with conn.transaction():
            first_time = conn.execute(
                "INSERT INTO processed (consumer, event_id) VALUES (%s, %s) "
                "ON CONFLICT DO NOTHING",
                (handler.name, event["event_id"])).rowcount == 1
            if not first_time:
                return "duplicate"
            handler(conn, event)       # the work, in the same transaction
        return "ok"
    except Retryable:
        raise                          # rolled back; redelivered with backoff
    except Exception as exc:
        if message.attempts >= MAX_ATTEMPTS:
            dead_letter.publish(message, reason=repr(exc))
            return "dead_lettered"
        raise


# --------------------------------------------------------------------------
# Local scaffolding
# --------------------------------------------------------------------------
from dataclasses import dataclass  # noqa: E402


@dataclass
class Message:
    value: str
    attempts: int = 1


class DeadLetterQueue:
    def __init__(self):
        self.items = []

    def publish(self, message, reason):
        self.items.append({"event": json.loads(message.value), "attempts": message.attempts,
                           "reason": reason})

    def depth(self):
        return len(self.items)


def deliver(conn, value, handler, dead_letter, backoff=None):
    """Deliver one message until it is processed, skipped or dead-lettered."""
    msg = Message(value)
    while True:
        try:
            return handle(conn, msg, handler, dead_letter)
        except Exception:
            if backoff:
                backoff(msg.attempts)
            msg.attempts += 1


class MerchantInquiry:
    """A handler that records one inquiry per case in the consumer's own table."""
    name = "inquiry"

    def __init__(self, fail_on=()):
        self.fail_on = set(fail_on)
        self.calls = 0

    def __call__(self, conn, event):
        self.calls += 1
        conn.execute("CREATE TABLE IF NOT EXISTS inquiries (case_id TEXT, event_id TEXT)")
        conn.execute("INSERT INTO inquiries VALUES (%s, %s)", (event["case_id"], event["event_id"]))
        if event["case_id"] in self.fail_on:
            raise ValueError("merchant record not found")


def demo():
    from events import Event, EventLog, LocalConnection, open_case, relay

    producer, consumer = LocalConnection(), LocalConnection()
    log = EventLog()
    for i in range(1, 6):
        open_case(producer, f"C-{i:04d}")
    relay(producer, log)
    # The relay crashed once and ran again: every event arrives twice.
    messages = list(log.messages()) * 2
    handler = MerchantInquiry(fail_on={"C-0003"})
    dlq = DeadLetterQueue()
    outcomes = [deliver(consumer, m, handler, dlq) for m in messages]
    counts = {k: outcomes.count(k) for k in sorted(set(outcomes))}
    inquiries = consumer.query("SELECT COUNT(*) FROM inquiries")[0][0]
    print(f"{len(messages)} deliveries of 5 events: {counts}")
    print(f"inquiries recorded: {inquiries} (exactly one per case that succeeded)")
    print(f"handler calls: {handler.calls} (each copy of the failing event was tried {MAX_ATTEMPTS} times, "
          f"rolled back each time, then dead-lettered)")
    print(f"dead-letter depth: {dlq.depth()}; first reason: {dlq.items[0]['reason']}")
    _ = Event  # imported for readers who extend the demo


if __name__ == "__main__":
    demo()
