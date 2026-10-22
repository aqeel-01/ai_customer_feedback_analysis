-- schema.sql
-- Single source of truth for the feedback analyzer SQLite schema.

CREATE TABLE IF NOT EXISTS tickets (
    ticket_id TEXT PRIMARY KEY,
    raw_message TEXT NOT NULL,
    source_file TEXT,
    processing_status TEXT NOT NULL,
    ignore_reason TEXT,
    created_at TEXT,
    processed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(processing_status);

CREATE TABLE IF NOT EXISTS analysis_results (
    ticket_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    priority TEXT NOT NULL,
    sentiment TEXT NOT NULL,
    product_feature TEXT,
    suggested_reply TEXT NOT NULL,
    model_name TEXT,
    analyzed_at TEXT NOT NULL,
    FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id) ON DELETE CASCADE
);
