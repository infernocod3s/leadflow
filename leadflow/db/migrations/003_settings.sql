-- Migration 003: Settings table for API keys and global config
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Enable RLS
ALTER TABLE settings ENABLE ROW LEVEL SECURITY;

-- Allow anon read/write (dashboard uses anon key)
DO $$ BEGIN
  DROP POLICY IF EXISTS settings_select ON settings;
  DROP POLICY IF EXISTS settings_insert ON settings;
  DROP POLICY IF EXISTS settings_update ON settings;
  DROP POLICY IF EXISTS settings_delete ON settings;
  CREATE POLICY settings_select ON settings FOR SELECT USING (true);
  CREATE POLICY settings_insert ON settings FOR INSERT WITH CHECK (true);
  CREATE POLICY settings_update ON settings FOR UPDATE USING (true);
  CREATE POLICY settings_delete ON settings FOR DELETE USING (true);
END $$;
