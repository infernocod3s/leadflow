-- 005: Strategy routing columns on leads
-- Stores which strategy was assigned to each lead by the strategy_routing step.

ALTER TABLE leads ADD COLUMN IF NOT EXISTS strategy_id TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS strategy_name TEXT;

CREATE INDEX IF NOT EXISTS idx_leads_strategy ON leads(campaign_id, strategy_id);
