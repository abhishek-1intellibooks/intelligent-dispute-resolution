-- PostgreSQL 16 schema shared by the case services (each service gets its own
-- schema and credentials; the tables below are created in each one it needs).
CREATE TABLE IF NOT EXISTS cases (
    case_id  text PRIMARY KEY,
    state    text NOT NULL,
    version  integer NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS outbox (
    seq        bigserial PRIMARY KEY,
    event_id   uuid UNIQUE NOT NULL,
    case_id    text NOT NULL,
    type       text NOT NULL,
    payload    jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    sent_at    timestamptz
);
CREATE INDEX IF NOT EXISTS outbox_unsent ON outbox (seq) WHERE sent_at IS NULL;
CREATE TABLE IF NOT EXISTS processed (
    consumer  text NOT NULL,
    event_id  uuid NOT NULL,
    at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer, event_id)
);
CREATE TABLE IF NOT EXISTS clocks (
    case_id    text NOT NULL,
    clock      text NOT NULL,
    started_on date NOT NULL,
    due_on     date NOT NULL,
    stopped_at timestamptz,
    PRIMARY KEY (case_id, clock)
);
CREATE INDEX IF NOT EXISTS clocks_open ON clocks (due_on) WHERE stopped_at IS NULL;
CREATE TABLE IF NOT EXISTS case_history (
    case_id  text NOT NULL,
    event_id uuid NOT NULL,
    type     text NOT NULL,
    payload  jsonb NOT NULL,
    PRIMARY KEY (case_id, event_id)
);
