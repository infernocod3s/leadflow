-- LeadFlow Initial Schema
-- Run this in Supabase SQL Editor

-- Enum for pipeline status
CREATE TYPE pipeline_status AS ENUM (
    'imported',
    'in_progress',
    'enriched',
    'qualified',
    'disqualified',
    'email_generated',
    'pushed',
    'error'
);

-- Clients table
CREATE TABLE clients (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Campaigns table
CREATE TABLE campaigns (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    slug TEXT NOT NULL UNIQUE,
    config JSONB DEFAULT '{}',
    smartlead_campaign_id INTEGER,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Leads table — main data store
CREATE TABLE leads (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    campaign_id UUID REFERENCES campaigns(id) ON DELETE CASCADE NOT NULL,

    -- Raw fields (from CSV import)
    raw_email TEXT,
    raw_first_name TEXT,
    raw_last_name TEXT,
    raw_company TEXT,
    raw_title TEXT,
    raw_website TEXT,
    raw_linkedin TEXT,
    raw_phone TEXT,
    raw_location TEXT,
    raw_industry TEXT,
    raw_extra JSONB DEFAULT '{}',

    -- Cleaned fields (after enrichment)
    email TEXT,
    first_name TEXT,
    last_name TEXT,
    company_name TEXT,
    job_title TEXT,
    website TEXT,
    linkedin_url TEXT,
    phone TEXT,
    location TEXT,
    industry TEXT,

    -- Enrichment results
    company_summary TEXT,
    company_employee_count TEXT,
    company_funding TEXT,
    icp_qualified BOOLEAN,
    icp_reason TEXT,
    title_relevant BOOLEAN,
    title_relevance_reason TEXT,

    -- Signals (JSONB for flexibility)
    signals JSONB DEFAULT '{}',
    tech_stack JSONB DEFAULT '[]',
    funding_signal JSONB DEFAULT '{}',
    hiring_signal JSONB DEFAULT '{}',

    -- Generated email
    email_subject TEXT,
    email_body TEXT,
    email_variant TEXT,

    -- Pipeline tracking
    pipeline_status pipeline_status DEFAULT 'imported',
    current_step TEXT,
    error_message TEXT,
    smartlead_lead_id TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    enriched_at TIMESTAMPTZ,
    pushed_at TIMESTAMPTZ
);

-- Enrichment logs — every API call recorded
CREATE TABLE enrichment_logs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    lead_id UUID REFERENCES leads(id) ON DELETE CASCADE NOT NULL,
    campaign_id UUID REFERENCES campaigns(id) ON DELETE CASCADE NOT NULL,
    step_name TEXT NOT NULL,
    model TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost NUMERIC(10, 6) DEFAULT 0,
    duration_ms INTEGER DEFAULT 0,
    success BOOLEAN DEFAULT true,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Pipeline runs — track batch executions
CREATE TABLE pipeline_runs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    campaign_id UUID REFERENCES campaigns(id) ON DELETE CASCADE NOT NULL,
    started_at TIMESTAMPTZ DEFAULT now(),
    finished_at TIMESTAMPTZ,
    total_leads INTEGER DEFAULT 0,
    processed_leads INTEGER DEFAULT 0,
    qualified_leads INTEGER DEFAULT 0,
    disqualified_leads INTEGER DEFAULT 0,
    error_leads INTEGER DEFAULT 0,
    total_cost NUMERIC(10, 4) DEFAULT 0,
    config JSONB DEFAULT '{}'
);

-- Cost summaries — aggregated per campaign/step
CREATE TABLE cost_summaries (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    campaign_id UUID REFERENCES campaigns(id) ON DELETE CASCADE NOT NULL,
    step_name TEXT NOT NULL,
    total_calls INTEGER DEFAULT 0,
    total_input_tokens BIGINT DEFAULT 0,
    total_output_tokens BIGINT DEFAULT 0,
    total_cost NUMERIC(10, 4) DEFAULT 0,
    period DATE DEFAULT CURRENT_DATE,
    UNIQUE(campaign_id, step_name, period)
);

-- Indexes for performance
CREATE INDEX idx_leads_campaign_status ON leads(campaign_id, pipeline_status);
CREATE INDEX idx_leads_email ON leads(email);
CREATE INDEX idx_leads_campaign_id ON leads(campaign_id);
CREATE INDEX idx_enrichment_logs_lead ON enrichment_logs(lead_id);
CREATE INDEX idx_enrichment_logs_campaign ON enrichment_logs(campaign_id);
CREATE INDEX idx_pipeline_runs_campaign ON pipeline_runs(campaign_id);

-- Updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER leads_updated_at
    BEFORE UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER campaigns_updated_at
    BEFORE UPDATE ON campaigns
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
