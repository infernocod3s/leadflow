-- Worker support: atomic lead claiming for concurrent workers
-- Run after 001_initial.sql

-- Add worker tracking columns
ALTER TABLE leads ADD COLUMN IF NOT EXISTS claimed_by TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ;

-- Index for fast worker polling
CREATE INDEX IF NOT EXISTS idx_leads_claim ON leads(campaign_id, pipeline_status, claimed_by);

-- Atomic claim function: multiple workers can safely grab batches
-- Uses FOR UPDATE SKIP LOCKED to prevent duplicate processing
CREATE OR REPLACE FUNCTION claim_leads(
    p_campaign_id UUID,
    p_batch_size INT DEFAULT 50,
    p_worker_id TEXT DEFAULT 'default'
)
RETURNS SETOF leads AS $$
BEGIN
    RETURN QUERY
    UPDATE leads
    SET pipeline_status = 'in_progress',
        claimed_by = p_worker_id,
        claimed_at = now()
    WHERE id IN (
        SELECT id FROM leads
        WHERE campaign_id = p_campaign_id
        AND pipeline_status IN ('imported', 'error')
        AND claimed_by IS NULL
        ORDER BY created_at
        LIMIT p_batch_size
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *;
END;
$$ LANGUAGE plpgsql;

-- Release stale claims (workers that crashed without finishing)
CREATE OR REPLACE FUNCTION release_stale_claims(p_timeout_minutes INT DEFAULT 30)
RETURNS INT AS $$
DECLARE
    released INT;
BEGIN
    UPDATE leads
    SET pipeline_status = 'imported',
        claimed_by = NULL,
        claimed_at = NULL
    WHERE pipeline_status = 'in_progress'
    AND claimed_at < now() - (p_timeout_minutes || ' minutes')::interval;

    GET DIAGNOSTICS released = ROW_COUNT;
    RETURN released;
END;
$$ LANGUAGE plpgsql;

-- Campaign queue stats for worker monitoring
CREATE OR REPLACE FUNCTION campaign_queue_stats(p_campaign_id UUID)
RETURNS TABLE(
    status TEXT,
    count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT pipeline_status::TEXT, COUNT(*)
    FROM leads
    WHERE campaign_id = p_campaign_id
    GROUP BY pipeline_status;
END;
$$ LANGUAGE plpgsql;
