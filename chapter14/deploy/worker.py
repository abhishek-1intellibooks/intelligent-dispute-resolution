"""Container entrypoint for the case services of Table 14.2.

One image per service, one process per replica. ROLE selects what it does:

  ROLE=consumer  consume TOPICS as consumer group GROUP, and for each message run
                 HANDLER (``module:function``, see handlers.py) through
                 consumer.handle: idempotent, retried with backoff, dead-lettered
                 to <topic>.dlq after MAX_ATTEMPTS.
  ROLE=relay     publish the service's outbox to the event log, keyed by case id
                 so that one case's events stay in order (Listing 14.1).

Environment: DATABASE_URL (PostgreSQL), KAFKA_BOOTSTRAP (default events:9092).
Requires psycopg 3 and confluent-kafka (requirements-worker.txt); both are
imported lazily so that the module can be inspected without them.
"""
import importlib
import json
import os
import time

from consumer import MAX_ATTEMPTS, Retryable, handle


class KafkaMessage:
    def __init__(self, raw, attempts=1):
        self.raw, self.value, self.attempts = raw, raw.value(), attempts


class DeadLetter:
    def __init__(self, producer):
        self.producer = producer

    def publish(self, message, reason):
        topic = f"{message.raw.topic()}.dlq"
        self.producer.produce(topic, key=message.raw.key(), value=message.value,
                              headers={"reason": reason, "attempts": str(message.attempts)})
        self.producer.flush()


def load_handler(spec):
    module, func = spec.split(":")
    handler = getattr(importlib.import_module(module), func)
    if not hasattr(handler, "name"):
        handler.name = os.environ.get("GROUP", func)
    return handler


def connect():
    import psycopg  # lazy: only inside the container
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)


def run_consumer():
    from confluent_kafka import Consumer, Producer  # lazy
    bootstrap = os.environ.get("KAFKA_BOOTSTRAP", "events:9092")
    consumer = Consumer({"bootstrap.servers": bootstrap, "group.id": os.environ["GROUP"],
                         "enable.auto.commit": False, "auto.offset.reset": "earliest"})
    consumer.subscribe(os.environ["TOPICS"].split(","))
    dead_letter = DeadLetter(Producer({"bootstrap.servers": bootstrap}))
    handler = load_handler(os.environ["HANDLER"])
    conn = connect()
    while True:
        raw = consumer.poll(1.0)
        if raw is None or raw.error():
            continue
        message = KafkaMessage(raw)
        while True:
            try:
                handle(conn, message, handler, dead_letter)
                break
            except Retryable:
                time.sleep(min(2 ** message.attempts, 60))      # backoff, then redeliver
            except Exception:
                if message.attempts >= MAX_ATTEMPTS:
                    break
                time.sleep(min(2 ** message.attempts, 60))
            message.attempts += 1
        consumer.commit(raw)


def run_relay(poll_seconds=0.2):
    from confluent_kafka import Producer  # lazy
    producer = Producer({"bootstrap.servers": os.environ.get("KAFKA_BOOTSTRAP", "events:9092"),
                         "enable.idempotence": True})
    conn = connect()
    while True:
        rows = conn.execute("SELECT seq, case_id, type, payload FROM outbox "
                            "WHERE sent_at IS NULL ORDER BY seq LIMIT 500").fetchall()
        for seq, case_id, type_, payload in rows:
            producer.produce(type_, key=case_id, value=payload)
            producer.flush()                       # published before it is marked sent
            conn.execute("UPDATE outbox SET sent_at = now() WHERE seq = %s", (seq,))
        if not rows:
            time.sleep(poll_seconds)


if __name__ == "__main__":
    role = os.environ.get("ROLE", "consumer")
    print(json.dumps({"role": role, "handler": os.environ.get("HANDLER")}))
    run_relay() if role == "relay" else run_consumer()
