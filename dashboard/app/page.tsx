"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { supabase, type Campaign } from "@/lib/supabase";
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
    const { data: campaignsData } = await supabase
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
      const { data: leads } = await supabase
        .from("leads")
        .select("pipeline_status")
        .eq("campaign_id", c.id);

      const counts: Record<string, number> = {};
      let total = 0;
      for (const l of leads || []) {
        counts[l.pipeline_status] = (counts[l.pipeline_status] || 0) + 1;
        total++;
      }

      const { data: costData } = await supabase
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
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-pulse text-gray-500">Loading dashboard...</div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
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
          <div className="text-center py-20 text-gray-500">
            <p className="text-lg">No campaigns yet</p>
            <p className="text-sm mt-2">
              Import leads with:{" "}
              <code className="bg-gray-800 px-2 py-1 rounded">
                leadflow import -f leads.csv -c my-campaign
              </code>
            </p>
          </div>
        ) : (
          <div className="grid gap-4">
            {campaigns.map((c) => (
              <Link
                key={c.id}
                href={`/campaigns/${c.slug}`}
                className="block bg-gray-900 border border-gray-800 rounded-xl p-6 hover:border-gray-700 transition-colors"
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
                    <div className="text-2xl font-bold text-white">
                      {formatNumber(c.total_leads)}
                    </div>
                    <div className="text-xs text-gray-500">leads</div>
                  </div>
                </div>

                {/* Pipeline progress bar */}
                <div className="flex h-2 rounded-full overflow-hidden bg-gray-800">
                  {c.total_leads > 0 && (
                    <>
                      <div
                        className="bg-green-500"
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
                        className="bg-indigo-500"
                        style={{
                          width: `${
                            ((c.lead_counts["pushed"] || 0) / c.total_leads) *
                            100
                          }%`,
                        }}
                      />
                      <div
                        className="bg-orange-500"
                        style={{
                          width: `${
                            ((c.lead_counts["disqualified"] || 0) /
                              c.total_leads) *
                            100
                          }%`,
                        }}
                      />
                      <div
                        className="bg-blue-500"
                        style={{
                          width: `${
                            ((c.lead_counts["in_progress"] || 0) /
                              c.total_leads) *
                            100
                          }%`,
                        }}
                      />
                      <div
                        className="bg-red-500"
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
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className={`text-xl font-bold ${color}`}>{value}</div>
    </div>
  );
}
