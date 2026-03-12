import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const SMARTLEAD_BASE = "https://server.smartlead.ai/api/v1";

function getServerSupabase() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) throw new Error("Missing Supabase env vars");
  return createClient(url, key);
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { campaign_id, smartlead_campaign_id, limit = 500 } = body;

    if (!campaign_id || !smartlead_campaign_id) {
      return NextResponse.json(
        { error: "campaign_id and smartlead_campaign_id are required" },
        { status: 400 }
      );
    }

    // Get API key from settings table
    const supabase = getServerSupabase();
    const { data: setting } = await supabase
      .from("settings")
      .select("value")
      .eq("key", "smartlead_api_key")
      .single();

    const apiKey = setting?.value || process.env.SMARTLEAD_API_KEY;
    if (!apiKey) {
      return NextResponse.json(
        { error: "Smartlead API key not configured. Set it in Settings." },
        { status: 400 }
      );
    }

    // Fetch leads ready to push
    const { data: leads, error: fetchErr } = await supabase
      .from("leads")
      .select("id, email, first_name, last_name, company_name, email_subject, email_body, company_summary")
      .eq("campaign_id", campaign_id)
      .eq("pipeline_status", "email_generated")
      .limit(limit);

    if (fetchErr) throw fetchErr;
    if (!leads || leads.length === 0) {
      return NextResponse.json({ pushed: 0, message: "No leads ready to push" });
    }

    let pushed = 0;
    const errors: string[] = [];

    for (const lead of leads) {
      try {
        const customFields: Record<string, string> = {};
        if (lead.email_subject) customFields.email_subject = lead.email_subject;
        if (lead.email_body) customFields.email_body = lead.email_body;
        if (lead.company_summary) customFields.company_summary = lead.company_summary;

        const response = await fetch(
          `${SMARTLEAD_BASE}/campaigns/${smartlead_campaign_id}/leads?api_key=${apiKey}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              api_key: apiKey,
              lead_list: [
                {
                  email: lead.email || "",
                  first_name: lead.first_name || "",
                  last_name: lead.last_name || "",
                  company_name: lead.company_name || "",
                  ...customFields,
                },
              ],
              settings: {
                ignore_global_block_list: false,
                ignore_unsubscribe_list: false,
              },
            }),
          }
        );

        if (!response.ok) {
          const errText = await response.text();
          throw new Error(errText);
        }

        // Update lead status to pushed
        await supabase
          .from("leads")
          .update({ pipeline_status: "pushed", updated_at: new Date().toISOString() })
          .eq("id", lead.id);

        pushed++;
      } catch (err: any) {
        errors.push(`${lead.email}: ${err.message}`);
        await supabase
          .from("leads")
          .update({
            pipeline_status: "error",
            error_message: `Smartlead push: ${err.message}`,
            updated_at: new Date().toISOString(),
          })
          .eq("id", lead.id);
      }
    }

    return NextResponse.json({
      pushed,
      total: leads.length,
      errors: errors.length > 0 ? errors.slice(0, 10) : undefined,
    });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
