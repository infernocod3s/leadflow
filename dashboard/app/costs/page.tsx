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
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-pulse text-gray-500">Loading costs...</div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white mb-6">Cost Overview</h1>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            <div className="text-xs text-gray-500 mb-1">Total Spend</div>
            <div className="text-3xl font-bold text-emerald-400">
              {formatCost(totalCost)}
            </div>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            <div className="text-xs text-gray-500 mb-1">Total API Calls</div>
            <div className="text-3xl font-bold text-white">
              {formatNumber(totalCalls)}
            </div>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            <div className="text-xs text-gray-500 mb-1">Avg Cost / Call</div>
            <div className="text-3xl font-bold text-white">
              {totalCalls > 0 ? formatCost(totalCost / totalCalls) : "$0.00"}
            </div>
          </div>
        </div>
      </div>

      {/* Cost by step */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Cost by Step</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b border-gray-800">
              <th className="pb-2 pr-4">Step</th>
              <th className="pb-2 pr-4 text-right">Calls</th>
              <th className="pb-2 pr-4 text-right">Total Cost</th>
              <th className="pb-2 pr-4 text-right">Avg / Call</th>
              <th className="pb-2 text-right">% of Total</th>
            </tr>
          </thead>
          <tbody>
            {stepCosts.map((s) => (
              <tr key={s.step_name} className="border-b border-gray-800/50">
                <td className="py-2 pr-4 text-white font-medium">
                  {s.step_name}
                </td>
                <td className="py-2 pr-4 text-right">
                  {formatNumber(s.total_calls)}
                </td>
                <td className="py-2 pr-4 text-right text-emerald-400">
                  {formatCost(s.total_cost)}
                </td>
                <td className="py-2 pr-4 text-right text-gray-400">
                  {formatCost(s.avg_cost_per_call)}
                </td>
                <td className="py-2 text-right text-gray-400">
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
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white mb-4">
          Cost by Campaign
        </h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b border-gray-800">
              <th className="pb-2 pr-4">Campaign</th>
              <th className="pb-2 pr-4 text-right">API Calls</th>
              <th className="pb-2 pr-4 text-right">Tokens In</th>
              <th className="pb-2 pr-4 text-right">Tokens Out</th>
              <th className="pb-2 text-right">Cost</th>
            </tr>
          </thead>
          <tbody>
            {campaignCosts.map((c) => (
              <tr
                key={c.campaign_slug}
                className="border-b border-gray-800/50"
              >
                <td className="py-2 pr-4">
                  <Link
                    href={`/campaigns/${c.campaign_slug}`}
                    className="text-blue-400 hover:underline font-medium"
                  >
                    {c.campaign_slug}
                  </Link>
                </td>
                <td className="py-2 pr-4 text-right">
                  {formatNumber(c.total_calls)}
                </td>
                <td className="py-2 pr-4 text-right text-gray-400">
                  {formatNumber(c.total_input_tokens)}
                </td>
                <td className="py-2 pr-4 text-right text-gray-400">
                  {formatNumber(c.total_output_tokens)}
                </td>
                <td className="py-2 text-right text-emerald-400">
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
