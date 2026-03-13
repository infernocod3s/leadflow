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
    const { campaign_id, batch_size, batch_number } = body;

    if (!campaign_id || !batch_size) {
      return NextResponse.json(
        { error: "campaign_id and batch_size are required" },
        { status: 400 }
      );
    }

    const supabase = getServerSupabase();

    // Get N queued leads (oldest first)
    const { data: queuedLeads, error: fetchErr } = await supabase
      .from("leads")
      .select("id")
      .eq("campaign_id", campaign_id)
      .eq("pipeline_status", "queued")
      .order("created_at", { ascending: true })
      .limit(batch_size);

    if (fetchErr) throw fetchErr;
    if (!queuedLeads || queuedLeads.length === 0) {
      return NextResponse.json({ released: 0, message: "No queued leads remaining" });
    }

    const ids = queuedLeads.map((l) => l.id);

    // Move them from queued → imported (worker will pick them up)
    const { error: updateErr } = await supabase
      .from("leads")
      .update({
        pipeline_status: "imported",
        batch_number: batch_number ?? null,
        updated_at: new Date().toISOString(),
      })
      .in("id", ids);

    if (updateErr) throw updateErr;

    return NextResponse.json({
      released: ids.length,
      batch_number: batch_number ?? null,
      message: `Released ${ids.length} leads for processing`,
    });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
