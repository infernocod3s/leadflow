"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getSupabase, type Campaign } from "@/lib/supabase";
import { formatDate, formatNumber, formatCost } from "@/lib/utils";

type CampaignWithStats = Campaign & {
  lead_counts: Record<string, number>;
  total_leads: number;
  total_cost: number;
};

export default function DashboardPage() {
  const [campaigns, setCampaigns] = useState<CampaignWithStats[]>([]);
  const [globalStats, setGlobalStats] = useState({
    total: 0,
    qualified: 0,
    disqualified: 0,
    pushed: 0,
    errors: 0,
    totalCost: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDashboard();
    // Refresh every 10 seconds
    const interval = setInterval(loadDashboard, 10000);
    return () => clearInterval(interval);
  }, []);

  async function loadDashboard() {
    // Fetch campaigns
    const { data: campaignsData } = await getSupabase()
      .from("campaigns")
      .select("*, clients(name)")
      .order("created_at", { ascending: false });

    if (!campaignsData) {
      setLoading(false);
      return;
    }

    // Fetch lead stats per campaign
    const enriched: CampaignWithStats[] = [];
    let gTotal = 0,
      gQualified = 0,
      gDisqualified = 0,
      gPushed = 0,
      gErrors = 0,
      gCost = 0;

    for (const c of campaignsData) {
      const { data: leads } = await getSupabase()
        .from("leads")
        .select("pipeline_status")
        .eq("campaign_id", c.id);

      const counts: Record<string, number> = {};
      let total = 0;
      for (const l of leads || []) {
        counts[l.pipeline_status] = (counts[l.pipeline_status] || 0) + 1;
        total++;
      }

      const { data: costData } = await getSupabase()
        .from("enrichment_logs")
        .select("cost")
        .eq("campaign_id", c.id);

      const totalCost = (costData || []).reduce(
        (sum, r) => sum + (r.cost || 0),
        0
      );

      gTotal += total;
      gQualified +=
        (counts["enriched"] || 0) + (counts["email_generated"] || 0);
      gDisqualified += counts["disqualified"] || 0;
      gPushed += counts["pushed"] || 0;
      gErrors += counts["error"] || 0;
      gCost += totalCost;

      enriched.push({
        ...c,
        lead_counts: counts,
        total_leads: total,
        total_cost: totalCost,
      });
    }

    setCampaigns(enriched);
    setGlobalStats({
      total: gTotal,
      qualified: gQualified,
      disqualified: gDisqualified,
      pushed: gPushed,
      errors: gErrors,
      totalCost: gCost,
    });
    setLoading(false);
  }

  if (loading) {
    return (
      <div className="space-y-8 animate-fade-in">
        <div>
          <div className="skeleton h-8 w-40 mb-6" />
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="card p-4">
                <div className="skeleton h-3 w-16 mb-2" />
                <div className="skeleton h-6 w-20" />
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="skeleton h-6 w-32 mb-4" />
          <div className="grid gap-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="card p-6">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <div className="skeleton h-5 w-40 mb-2" />
                    <div className="skeleton h-3 w-56" />
                  </div>
                  <div className="skeleton h-8 w-12" />
                </div>
                <div className="skeleton h-1.5 w-full rounded-full" />
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Global stats */}
      <div>
        <h1 className="text-2xl font-bold text-white mb-6">Dashboard</h1>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <StatCard label="Total Leads" value={formatNumber(globalStats.total)} />
          <StatCard
            label="Qualified"
            value={formatNumber(globalStats.qualified)}
            color="text-green-400"
          />
          <StatCard
            label="Disqualified"
            value={formatNumber(globalStats.disqualified)}
            color="text-orange-400"
          />
          <StatCard
            label="Pushed"
            value={formatNumber(globalStats.pushed)}
            color="text-indigo-400"
          />
          <StatCard
            label="Errors"
            value={formatNumber(globalStats.errors)}
            color="text-red-400"
          />
          <StatCard
            label="Total Cost"
            value={formatCost(globalStats.totalCost)}
            color="text-emerald-400"
          />
        </div>
      </div>

      {/* Campaign list */}
      <div>
        <h2 className="text-lg font-semibold text-white mb-4">Campaigns</h2>
        {campaigns.length === 0 ? (
          <div className="card text-center py-20 px-6">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-amber-500/10 mb-4">
              <svg className="w-8 h-8 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
            </div>
            <p className="text-lg text-gray-300 mb-2">No campaigns yet</p>
            <p className="text-sm text-gray-500 mb-6">
              Get started by creating your first campaign or importing leads via CLI.
            </p>
            <div className="flex items-center justify-center gap-4">
              <Link href="/campaigns/new" className="btn-primary py-2.5">
                Create Campaign
              </Link>
              <code className="bg-gray-800/60 border border-gray-700/40 px-3 py-2 rounded-lg text-sm text-gray-400">
                growthpal import -f leads.csv -c my-campaign
              </code>
            </div>
          </div>
        ) : (
          <div className="grid gap-4">
            {campaigns.map((c) => (
              <Link
                key={c.id}
                href={`/campaigns/${c.slug}`}
                className="block card-hover p-6"
              >
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h3 className="text-white font-semibold text-lg">
                      {c.slug}
                    </h3>
                    <p className="text-sm text-gray-500">
                      {(c.clients as any)?.name || "—"} &middot;{" "}
                      {formatDate(c.created_at)}
                    </p>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-bold text-white tabular-nums">
                      {formatNumber(c.total_leads)}
                    </div>
                    <div className="text-xs text-gray-500">leads</div>
                  </div>
                </div>

                {/* Pipeline progress bar */}
                <div className="flex h-1.5 rounded-full overflow-hidden bg-gray-800/50">
                  {c.total_leads > 0 && (
                    <>
                      <div
                        className="bg-green-500 transition-all duration-500"
                        style={{
                          width: `${
                            (((c.lead_counts["enriched"] || 0) +
                              (c.lead_counts["email_generated"] || 0)) /
                              c.total_leads) *
                            100
                          }%`,
                        }}
                      />
                      <div
                        className="bg-indigo-500 transition-all duration-500"
                        style={{
                          width: `${
                            ((c.lead_counts["pushed"] || 0) / c.total_leads) *
                            100
                          }%`,
                        }}
                      />
                      <div
                        className="bg-orange-500 transition-all duration-500"
                        style={{
                          width: `${
                            ((c.lead_counts["disqualified"] || 0) /
                              c.total_leads) *
                            100
                          }%`,
                        }}
                      />
                      <div
                        className="bg-blue-500 transition-all duration-500"
                        style={{
                          width: `${
                            ((c.lead_counts["in_progress"] || 0) /
                              c.total_leads) *
                            100
                          }%`,
                        }}
                      />
                      <div
                        className="bg-red-500 transition-all duration-500"
                        style={{
                          width: `${
                            ((c.lead_counts["error"] || 0) / c.total_leads) *
                            100
                          }%`,
                        }}
                      />
                    </>
                  )}
                </div>

                <div className="flex gap-4 mt-3 text-xs text-gray-500">
                  <span>
                    <span className="text-green-400">
                      {(c.lead_counts["enriched"] || 0) +
                        (c.lead_counts["email_generated"] || 0)}
                    </span>{" "}
                    qualified
                  </span>
                  <span>
                    <span className="text-orange-400">
                      {c.lead_counts["disqualified"] || 0}
                    </span>{" "}
                    disqualified
                  </span>
                  <span>
                    <span className="text-indigo-400">
                      {c.lead_counts["pushed"] || 0}
                    </span>{" "}
                    pushed
                  </span>
                  {c.total_cost > 0 && (
                    <span className="ml-auto text-emerald-400">
                      {formatCost(c.total_cost)}
                    </span>
                  )}
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  color = "text-white",
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div className="card p-4">
      <div className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-xl font-bold tabular-nums ${color}`}>{value}</div>
    </div>
  );
}
