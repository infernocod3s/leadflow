import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let _client: SupabaseClient | null = null;

export function getSupabase(): SupabaseClient {
  if (_client) return _client;

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !key) {
    throw new Error(
      "Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY"
    );
  }

  _client = createClient(url, key);
  return _client;
}

export type Lead = {
  id: string;
  campaign_id: string;
  raw_email: string;
  raw_first_name: string;
  raw_last_name: string;
  raw_company: string;
  raw_title: string;
  email: string | null;
  first_name: string | null;
  last_name: string | null;
  company_name: string | null;
  job_title: string | null;
  website: string | null;
  company_summary: string | null;
  icp_qualified: boolean | null;
  icp_reason: string | null;
  title_relevant: boolean | null;
  signals: Record<string, unknown>;
  email_subject: string | null;
  email_body: string | null;
  strategy_id: string | null;
  strategy_name: string | null;
  batch_number: number | null;
  pipeline_status: string;
  current_step: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type Campaign = {
  id: string;
  client_id: string;
  slug: string;
  config: Record<string, unknown>;
  smartlead_campaign_id: number | null;
  created_at: string;
  updated_at: string;
  clients?: { name: string };
};

export type EnrichmentLog = {
  id: string;
  lead_id: string;
  campaign_id: string;
  step_name: string;
  model: string | null;
  input_tokens: number;
  output_tokens: number;
  cost: number;
  duration_ms: number;
  success: boolean;
  error_message: string | null;
  created_at: string;
};
