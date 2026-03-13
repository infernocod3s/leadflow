import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

function getServerSupabase() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) throw new Error("Missing Supabase env vars");
  return createClient(url, key);
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { campaign_id, lead_ids } = body;

    if (!campaign_id) {
      return NextResponse.json({ error: "campaign_id is required" }, { status: 400 });
    }

    const supabase = getServerSupabase();

    let query = supabase
      .from("leads")
      .update({
        pipeline_status: "imported",
        error_message: null,
        current_step: null,
        updated_at: new Date().toISOString(),
      })
      .eq("campaign_id", campaign_id)
      .eq("pipeline_status", "error");

    // If specific lead IDs provided, only retry those
    if (lead_ids && lead_ids.length > 0) {
      query = query.in("id", lead_ids);
    }

    const { data, error, count } = await query.select("id");

    if (error) throw error;

    const retried = data?.length ?? 0;

    return NextResponse.json({
      retried,
      message: `Reset ${retried} error leads to imported — worker will pick them up`,
    });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
