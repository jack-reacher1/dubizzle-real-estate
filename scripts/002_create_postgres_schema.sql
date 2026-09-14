CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS listings (
    ad_id TEXT PRIMARY KEY,
    ad_url TEXT,
    listing_type TEXT NOT NULL,
    property_type TEXT,
    title TEXT,
    price TEXT,
    area_sqm TEXT,
    bedrooms TEXT,
    bathrooms TEXT,
    completion_status TEXT,
    payment_method TEXT,
    ownership TEXT,
    furnished TEXT,
    location_text TEXT,
    compound TEXT,
    location_link TEXT,
    amenities TEXT,
    description_full TEXT,
    phone_in_description TEXT,
    posted_at TEXT,
    updated_at TEXT,
    scraped_at TEXT,
    days_since_updated INTEGER,
    is_verified_business BOOLEAN NOT NULL DEFAULT false,
    is_agency BOOLEAN NOT NULL DEFAULT false,
    agency_name TEXT,
    has_broker_code_pattern BOOLEAN NOT NULL DEFAULT false,
    seller_repeat_count INTEGER NOT NULL DEFAULT 0,
    seller_id TEXT,
    seller_name TEXT,
    first_seen_date TEXT NOT NULL,
    last_seen_date TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    lead_status TEXT NOT NULL DEFAULT 'new' CHECK (lead_status IN ('new', 'contacted')),
    source TEXT NOT NULL DEFAULT 'dubizzle',
    source_id TEXT,
    source_url TEXT,
    collection_run_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at_db TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE listings ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'dubizzle';
ALTER TABLE listings ADD COLUMN IF NOT EXISTS source_id TEXT;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS source_url TEXT;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS collection_run_id UUID;
UPDATE listings SET source = 'dubizzle', source_id = ad_id, source_url = ad_url WHERE source IS NULL OR source = '';
CREATE UNIQUE INDEX IF NOT EXISTS listings_source_source_id_idx ON listings (source, source_id);

ALTER TABLE listings ADD COLUMN IF NOT EXISTS lead_status TEXT;
UPDATE listings SET lead_status = 'new' WHERE lead_status IS NULL;
ALTER TABLE listings ALTER COLUMN lead_status SET DEFAULT 'new';
ALTER TABLE listings ALTER COLUMN lead_status SET NOT NULL;
ALTER TABLE listings DROP CONSTRAINT IF EXISTS listings_lead_status_check;
ALTER TABLE listings ADD CONSTRAINT listings_lead_status_check
    CHECK (lead_status IN ('new', 'contacted'));

CREATE INDEX IF NOT EXISTS listings_active_updated_idx ON listings (is_active, updated_at DESC);
CREATE INDEX IF NOT EXISTS listings_seller_idx ON listings (seller_id);
CREATE INDEX IF NOT EXISTS listings_compound_idx ON listings (compound);

CREATE TABLE IF NOT EXISTS sellers (
    seller_id TEXT PRIMARY KEY,
    seller_name TEXT,
    profile_url TEXT,
    active_ads_count INTEGER,
    active_ads_count_source TEXT,
    classification TEXT,
    checked_at TIMESTAMPTZ,
    blocklist_permanent BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS sellers_eligibility_idx
    ON sellers (classification, blocklist_permanent, checked_at);

CREATE TABLE IF NOT EXISTS scrape_meta (
    key TEXT PRIMARY KEY,
    value JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO app_config (key, value) VALUES
    ('freshness_days', '14'),
    ('owner_recheck_days', '30')
ON CONFLICT (key) DO NOTHING;

CREATE TABLE IF NOT EXISTS scrape_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL DEFAULT 'dubizzle',
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    scraped_listings INTEGER NOT NULL DEFAULT 0,
    business_listings INTEGER NOT NULL DEFAULT 0,
    sellers_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);

ALTER TABLE scrape_runs ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'dubizzle';

CREATE INDEX IF NOT EXISTS scrape_runs_started_idx ON scrape_runs (started_at DESC);

CREATE OR REPLACE VIEW business_listings AS
SELECT l.ad_id, l.ad_url, l.listing_type, l.title, l.price, l.area_sqm,
       l.bedrooms, l.bathrooms, l.property_type, l.completion_status,
       l.payment_method, l.furnished, l.location_text, l.compound,
       l.description_full, l.posted_at, l.updated_at, l.days_since_updated,
    l.lead_status,
       COALESCE(s.seller_name, l.seller_name) AS seller_name,
       s.active_ads_count, true AS likely_owner
FROM listings l
JOIN sellers s ON s.seller_id = l.seller_id
WHERE l.is_active
  AND NOT l.is_agency
  AND NOT s.blocklist_permanent
  AND s.classification = 'owner'
  AND s.checked_at >= now() - (
      (SELECT value::int FROM app_config WHERE key = 'owner_recheck_days') * interval '1 day'
  )
  AND (l.days_since_updated IS NULL OR l.days_since_updated <= (
      SELECT value::int FROM app_config WHERE key = 'freshness_days'
  ));