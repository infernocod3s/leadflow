-- 006: Progressive batch execution support
-- Adds 'queued' status for leads held back until batch is released.
-- Worker only processes 'imported' leads, so 'queued' leads wait.

ALTER TYPE pipeline_status ADD VALUE IF NOT EXISTS 'queued' BEFORE 'imported';

ALTER TABLE leads ADD COLUMN IF NOT EXISTS batch_number INTEGER;

CREATE INDEX IF NOT EXISTS idx_leads_queued ON leads(campaign_id, pipeline_status)
    WHERE pipeline_status = 'queued';
