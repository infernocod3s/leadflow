-- Migration 004: Company cache for 5-layer research cascade
-- Stores structured company data keyed by domain to avoid redundant research

CREATE TABLE IF NOT EXISTS company_cache (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    domain TEXT NOT NULL UNIQUE,
    company_name TEXT,
    description TEXT,
    industry TEXT,
    employee_count TEXT,
    funding TEXT,
    products JSONB DEFAULT '[]',
    target_market TEXT,
    tech_stack JSONB DEFAULT '[]',
    email_provider TEXT,
    cms TEXT,
    hosting TEXT,
    signals JSONB DEFAULT '[]',
    funding_signal JSONB DEFAULT '{}',
    hiring_signal JSONB DEFAULT '{}',
    social_links JSONB DEFAULT '{}',
    json_ld_data JSONB DEFAULT '{}',
    resolved_by TEXT NOT NULL,
    data_quality_score FLOAT DEFAULT 0.0,
    layer_costs JSONB DEFAULT '{}',
    company_info_at TIMESTAMPTZ DEFAULT now(),
    signals_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_cache_domain ON company_cache(domain);

-- Track which research layer resolved each enrichment
ALTER TABLE enrichment_logs ADD COLUMN IF NOT EXISTS research_layer TEXT;

-- Auto-update updated_at on company_cache changes
CREATE OR REPLACE FUNCTION update_company_cache_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_company_cache_updated_at ON company_cache;
CREATE TRIGGER trg_company_cache_updated_at
    BEFORE UPDATE ON company_cache
    FOR EACH ROW
    EXECUTE FUNCTION update_company_cache_updated_at();
