"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getSupabase } from "@/lib/supabase";
import { formatCost, formatNumber } from "@/lib/utils";

type CampaignCost = {
  campaign_slug: string;
  total_calls: number;
  total_cost: number;
  total_input_tokens: number;
  total_output_tokens: number;
};

type StepCost = {
  step_name: string;
  total_calls: number;
  total_cost: number;
  avg_cost_per_call: number;
};

export default function CostsPage() {
  const [campaignCosts, setCampaignCosts] = useState<CampaignCost[]>([]);
  const [stepCosts, setStepCosts] = useState<StepCost[]>([]);
  const [totalCost, setTotalCost] = useState(0);
  const [totalCalls, setTotalCalls] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadCosts();
  }, []);

  async function loadCosts() {
    // Fetch all enrichment logs with campaign info
    const { data: logs } = await getSupabase()
      .from("enrichment_logs")
      .select("step_name, cost, input_tokens, output_tokens, campaign_id");

    if (!logs) {
      setLoading(false);
      return;
    }

    // Fetch campaigns for slug mapping
    const { data: campaigns } = await getSupabase()
      .from("campaigns")
      .select("id, slug");

    const campaignMap = new Map(
      (campaigns || []).map((c) => [c.id, c.slug])
    );

    // Aggregate by campaign
    const byCampaign: Record<string, CampaignCost> = {};
    const byStep: Record<string, StepCost> = {};
    let total = 0;
    let calls = 0;

    for (const log of logs) {
      const slug = campaignMap.get(log.campaign_id) || "unknown";
      total += log.cost || 0;
      calls++;

      // Campaign aggregation
      if (!byCampaign[slug]) {
        byCampaign[slug] = {
          campaign_slug: slug,
          total_calls: 0,
          total_cost: 0,
          total_input_tokens: 0,
          total_output_tokens: 0,
        };
      }
      byCampaign[slug].total_calls++;
      byCampaign[slug].total_cost += log.cost || 0;
      byCampaign[slug].total_input_tokens += log.input_tokens || 0;
      byCampaign[slug].total_output_tokens += log.output_tokens || 0;

      // Step aggregation
      if (!byStep[log.step_name]) {
        byStep[log.step_name] = {
          step_name: log.step_name,
          total_calls: 0,
          total_cost: 0,
          avg_cost_per_call: 0,
        };
      }
      byStep[log.step_name].total_calls++;
      byStep[log.step_name].total_cost += log.cost || 0;
    }

    // Calculate averages
    for (const s of Object.values(byStep)) {
      s.avg_cost_per_call = s.total_calls > 0 ? s.total_cost / s.total_calls : 0;
    }

    setCampaignCosts(
      Object.values(byCampaign).sort((a, b) => b.total_cost - a.total_cost)
    );
    setStepCosts(
      Object.values(byStep).sort((a, b) => b.total_cost - a.total_cost)
    );
    setTotalCost(total);
    setTotalCalls(calls);
    setLoading(false);
  }

  if (loading) {
    return (
      <div className="space-y-8 animate-fade-in">
        <div>
          <div className="skeleton h-8 w-40 mb-6" />
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="card p-6">
                <div className="skeleton h-3 w-20 mb-2" />
                <div className="skeleton h-8 w-24" />
              </div>
            ))}
          </div>
        </div>
        <div className="card p-6">
          <div className="skeleton h-6 w-32 mb-4" />
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="skeleton h-8 w-full mb-2" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-white mb-6">Cost Overview</h1>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="card p-6">
            <div className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">Total Spend</div>
            <div className="text-3xl font-bold text-emerald-400 tabular-nums">
              {formatCost(totalCost)}
            </div>
          </div>
          <div className="card p-6">
            <div className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">Total API Calls</div>
            <div className="text-3xl font-bold text-white tabular-nums">
              {formatNumber(totalCalls)}
            </div>
          </div>
          <div className="card p-6">
            <div className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">Avg Cost / Call</div>
            <div className="text-3xl font-bold text-white tabular-nums">
              {totalCalls > 0 ? formatCost(totalCost / totalCalls) : "$0.00"}
            </div>
          </div>
        </div>
      </div>

      {/* Cost by step */}
      <div className="card p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Cost by Step</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b border-gray-800/40">
              <th className="table-header pb-2 pr-4">Step</th>
              <th className="table-header pb-2 pr-4 text-right">Calls</th>
              <th className="table-header pb-2 pr-4 text-right">Total Cost</th>
              <th className="table-header pb-2 pr-4 text-right">Avg / Call</th>
              <th className="table-header pb-2 text-right">% of Total</th>
            </tr>
          </thead>
          <tbody>
            {stepCosts.map((s) => (
              <tr key={s.step_name} className="table-row">
                <td className="py-2 pr-4 text-white font-medium">
                  {s.step_name}
                </td>
                <td className="py-2 pr-4 text-right tabular-nums">
                  {formatNumber(s.total_calls)}
                </td>
                <td className="py-2 pr-4 text-right text-emerald-400 tabular-nums">
                  {formatCost(s.total_cost)}
                </td>
                <td className="py-2 pr-4 text-right text-gray-400 tabular-nums">
                  {formatCost(s.avg_cost_per_call)}
                </td>
                <td className="py-2 text-right text-gray-400 tabular-nums">
                  {totalCost > 0
                    ? `${((s.total_cost / totalCost) * 100).toFixed(1)}%`
                    : "0%"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Cost by campaign */}
      <div className="card p-6">
        <h2 className="text-lg font-semibold text-white mb-4">
          Cost by Campaign
        </h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b border-gray-800/40">
              <th className="table-header pb-2 pr-4">Campaign</th>
              <th className="table-header pb-2 pr-4 text-right">API Calls</th>
              <th className="table-header pb-2 pr-4 text-right">Tokens In</th>
              <th className="table-header pb-2 pr-4 text-right">Tokens Out</th>
              <th className="table-header pb-2 text-right">Cost</th>
            </tr>
          </thead>
          <tbody>
            {campaignCosts.map((c) => (
              <tr
                key={c.campaign_slug}
                className="table-row"
              >
                <td className="py-2 pr-4">
                  <Link
                    href={`/campaigns/${c.campaign_slug}`}
                    className="text-amber-400/80 hover:text-amber-400 font-medium transition-colors"
                  >
                    {c.campaign_slug}
                  </Link>
                </td>
                <td className="py-2 pr-4 text-right tabular-nums">
                  {formatNumber(c.total_calls)}
                </td>
                <td className="py-2 pr-4 text-right text-gray-400 tabular-nums">
                  {formatNumber(c.total_input_tokens)}
                </td>
                <td className="py-2 pr-4 text-right text-gray-400 tabular-nums">
                  {formatNumber(c.total_output_tokens)}
                </td>
                <td className="py-2 text-right text-emerald-400 tabular-nums">
                  {formatCost(c.total_cost)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
