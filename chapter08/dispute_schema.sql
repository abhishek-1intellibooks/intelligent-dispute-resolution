-- chapter08/dispute_schema.sql
-- The dispute case schema (SQLite). Source tables mirror the feeds exactly,
-- with only a load timestamp added; the case tables hold keys, indicators and
-- provenance, never copies of source facts.

-- Source tables: one per feed, landed unchanged
CREATE TABLE authorization (
  auth_id TEXT PRIMARY KEY,
  card_token TEXT NOT NULL,
  merchant_id TEXT NOT NULL,
  merchant_name TEXT,
  amount REAL NOT NULL,
  auth_code TEXT,
  authorized_at TEXT NOT NULL,
  loaded_at TEXT NOT NULL);
CREATE TABLE clearing (
  arn TEXT PRIMARY KEY,
  card_token TEXT NOT NULL,
  merchant_id TEXT NOT NULL,
  descriptor TEXT NOT NULL,
  amount REAL NOT NULL,
  auth_code TEXT,
  cleared_at TEXT NOT NULL,
  loaded_at TEXT NOT NULL);
CREATE TABLE crm_claim (
  claim_id TEXT PRIMARY KEY,
  channel TEXT NOT NULL,
  claim_received_at TEXT NOT NULL,
  card_token TEXT NOT NULL,
  claimed_amount REAL NOT NULL,
  merchant_stated TEXT,
  loaded_at TEXT NOT NULL);
CREATE TABLE merchant_order (
  order_id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL,
  auth_code TEXT,
  order_total REAL NOT NULL,
  ordered_at TEXT NOT NULL,
  shipped_at TEXT,
  delivered_at TEXT,
  delivery_status TEXT,
  loaded_at TEXT NOT NULL);

-- Case tables: one record per claim, with provenance for every link
CREATE TABLE case_record (
  case_id TEXT PRIMARY KEY,
  rail TEXT NOT NULL DEFAULT 'card',
  state TEXT NOT NULL DEFAULT 'CLAIM_RECEIVED',
  claim_id TEXT NOT NULL REFERENCES crm_claim(claim_id),
  arn TEXT REFERENCES clearing(arn),
  auth_id TEXT REFERENCES authorization(auth_id),
  order_id TEXT REFERENCES merchant_order(order_id),
  claim_received_at TEXT NOT NULL,
  completeness INTEGER NOT NULL CHECK (completeness BETWEEN 0 AND 3),
  needs_review INTEGER NOT NULL DEFAULT 0,
  duplicate_of TEXT REFERENCES case_record(case_id),
  rule_version TEXT NOT NULL);
CREATE UNIQUE INDEX one_case_per_arn ON case_record(arn)
  WHERE arn IS NOT NULL AND duplicate_of IS NULL;
CREATE TABLE case_source_link (
  case_id TEXT NOT NULL REFERENCES case_record(case_id), source TEXT NOT NULL,
  source_id TEXT, match_method TEXT NOT NULL, confidence REAL NOT NULL,
  linked_at TEXT NOT NULL, PRIMARY KEY (case_id, source));
CREATE TABLE case_event (
  case_id TEXT NOT NULL REFERENCES case_record(case_id), event_at TEXT NOT NULL,
  event_type TEXT NOT NULL, from_state TEXT, to_state TEXT, source TEXT NOT NULL);

-- A flat view for analysts: joins the case to its sources without copying facts
CREATE VIEW case_flat AS
SELECT c.case_id, c.state, c.completeness, c.needs_review, c.duplicate_of, c.rule_version,
       cl.claim_id, cl.channel, cl.claim_received_at, cl.claimed_amount, cl.merchant_stated,
       r.arn, r.descriptor, r.amount AS cleared_amount, r.cleared_at,
       a.auth_id, a.auth_code, a.authorized_at,
       o.order_id, o.shipped_at, o.delivered_at, o.delivery_status
FROM case_record c
JOIN crm_claim cl ON cl.claim_id = c.claim_id
LEFT JOIN clearing r ON r.arn = c.arn
LEFT JOIN authorization a ON a.auth_id = c.auth_id
LEFT JOIN merchant_order o ON o.order_id = c.order_id;
