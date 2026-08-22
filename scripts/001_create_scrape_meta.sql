-- Migration: create scrape_meta table
-- Idempotent DDL to create the table used by scripts/update_scrape_status.py

CREATE TABLE IF NOT EXISTS scrape_meta (
    key TEXT PRIMARY KEY,
    value JSONB,
    updated_at TIMESTAMPTZ DEFAULT now()
);
