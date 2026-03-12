"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { getSupabase, type Lead, type Campaign } from "@/lib/supabase";
import {
  formatDate,
  formatNumber,
  formatCost,
  statusColor,
  cn,
} from "@/lib/utils";

type StepCost = {
  step_name: string;
  total_calls: number;
  total_cost: number;
  avg_duration_ms: number;
  success_count: number;
  failure_count: number;
};

export default function CampaignPage() {
  const params = useParams();
  const slug = params.slug as string;

  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [statusCounts, setStatusCounts] = useState<Record<string, number>>({});
  const [stepCosts, setStepCosts] = useState<StepCost[]>([]);
  const [totalCost, setTotalCost] = useState(0);
  const [filter, setFilter] = useState<string>("all");
  const [loading, setLoading] = useState(true);
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);

  useEffect(() => {
    loadCampaign();
    const interval = setInterval(loadCampaign, 10000);
    return () => clearInterval(interval);
  }, [slug]);

  async function loadCampaign() {
    // Fetch campaign
    const { data: cData } = await getSupabase()
      .from("campaigns")
      .select("*, clients(name)")
      .eq("slug", slug)
      .single();

    if (!cData) {
      setLoading(false);
      return;
    }
    setCampaign(cData);

    // Fetch all leads for status counts
    const { data: allLeads } = await getSupabase()
      .from("leads")
      .select("pipeline_status")
      .eq("campaign_id", cData.id);

    const counts: Record<string, number> = {};
    for (const l of allLeads || []) {
      counts[l.pipeline_status] = (counts[l.pipeline_status] || 0) + 1;
    }
    setStatusCounts(counts);

    // Fetch leads page (limit 100)
    let query = getSupabase()
      .from("leads")
      .select("*")
      .eq("campaign_id", cData.id)
      .order("created_at", { ascending: false })
      .limit(100);

    if (filter !== "all") {
      query = query.eq("pipeline_status", filter);
    }

    const { data: leadsData } = await query;
    setLeads(leadsData || []);

    // Fetch step costs
    const { data: logs } = await getSupabase()
      .from("enrichment_logs")
      .select("step_name, cost, duration_ms, success")
      .eq("campaign_id", cData.id);

    const stepMap: Record<string, StepCost> = {};
    let cost = 0;
    for (const log of logs || []) {
      if (!stepMap[log.step_name]) {
        stepMap[log.step_name] = {
          step_name: log.step_name,
          total_calls: 0,
          total_cost: 0,
          avg_duration_ms: 0,
          success_count: 0,
          failure_count: 0,
        };
      }
      const s = stepMap[log.step_name];
      s.total_calls++;
      s.total_cost += log.cost || 0;
      s.avg_duration_ms += log.duration_ms || 0;
      if (log.success) s.success_count++;
      else s.failure_count++;
      cost += log.cost || 0;
    }

    // Calculate averages
    for (const s of Object.values(stepMap)) {
      s.avg_duration_ms = s.total_calls > 0 ? s.avg_duration_ms / s.total_calls : 0;
    }

    setStepCosts(Object.values(stepMap));
    setTotalCost(cost);
    setLoading(false);
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-pulse text-gray-500">Loading campaign...</div>
      </div>
    );
  }

  if (!campaign) {
    return (
      <div className="text-center py-20">
        <p className="text-gray-500 text-lg">Campaign not found: {slug}</p>
        <Link href="/" className="text-blue-400 hover:underline mt-4 block">
          Back to dashboard
        </Link>
      </div>
    );
  }

  const totalLeads = Object.values(statusCounts).reduce((a, b) => a + b, 0);
  const statuses = [
    "imported",
    "in_progress",
    "enriched",
    "email_generated",
    "qualified",
    "disqualified",
    "pushed",
    "error",
  ];

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <Link
          href="/"
          className="text-sm text-gray-500 hover:text-gray-300 mb-2 block"
        >
          &larr; All Campaigns
        </Link>
        <h1 className="text-2xl font-bold text-white">{slug}</h1>
        <p className="text-sm text-gray-500">
          {(campaign.clients as any)?.name || "—"} &middot;{" "}
          {formatDate(campaign.created_at)}
          {campaign.smartlead_campaign_id && (
            <>
              {" "}
              &middot; Smartlead #{campaign.smartlead_campaign_id}
            </>
          )}
        </p>
      </div>

      {/* Status breakdown */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
        <button
          onClick={() => setFilter("all")}
          className={cn(
            "bg-gray-900 border rounded-xl p-3 text-left transition-colors",
            filter === "all" ? "border-blue-500" : "border-gray-800 hover:border-gray-700"
          )}
        >
          <div className="text-xs text-gray-500">All</div>
          <div className="text-lg font-bold text-white">
            {formatNumber(totalLeads)}
          </div>
        </button>
        {statuses.map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={cn(
              "bg-gray-900 border rounded-xl p-3 text-left transition-colors",
              filter === s ? "border-blue-500" : "border-gray-800 hover:border-gray-700"
            )}
          >
            <div className="text-xs text-gray-500">{s.replace("_", " ")}</div>
            <div className="text-lg font-bold text-white">
              {formatNumber(statusCounts[s] || 0)}
            </div>
          </button>
        ))}
      </div>

      {/* Cost and step breakdown */}
      {stepCosts.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Step Breakdown</h2>
            <div className="text-emerald-400 font-bold">
              {formatCost(totalCost)} total
              {totalLeads > 0 && (
                <span className="text-gray-500 font-normal text-sm ml-2">
                  ({formatCost(totalCost / totalLeads)}/lead)
                </span>
              )}
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-800">
                  <th className="pb-2 pr-4">Step</th>
                  <th className="pb-2 pr-4 text-right">Calls</th>
                  <th className="pb-2 pr-4 text-right">Success</th>
                  <th className="pb-2 pr-4 text-right">Failures</th>
                  <th className="pb-2 pr-4 text-right">Avg Time</th>
                  <th className="pb-2 text-right">Cost</th>
                </tr>
              </thead>
              <tbody>
                {stepCosts.map((s) => (
                  <tr
                    key={s.step_name}
                    className="border-b border-gray-800/50"
                  >
                    <td className="py-2 pr-4 text-white font-medium">
                      {s.step_name}
                    </td>
                    <td className="py-2 pr-4 text-right">
                      {formatNumber(s.total_calls)}
                    </td>
                    <td className="py-2 pr-4 text-right text-green-400">
                      {formatNumber(s.success_count)}
                    </td>
                    <td className="py-2 pr-4 text-right text-red-400">
                      {s.failure_count > 0 ? formatNumber(s.failure_count) : "—"}
                    </td>
                    <td className="py-2 pr-4 text-right text-gray-400">
                      {Math.round(s.avg_duration_ms)}ms
                    </td>
                    <td className="py-2 text-right text-emerald-400">
                      {formatCost(s.total_cost)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Leads table */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="p-4 border-b border-gray-800">
          <h2 className="text-lg font-semibold text-white">
            Leads{" "}
            <span className="text-sm text-gray-500 font-normal">
              (showing {leads.length}
              {filter !== "all" ? ` ${filter}` : ""})
            </span>
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-800 bg-gray-900/50">
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Company</th>
                <th className="px-4 py-3">Title</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">ICP</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((lead) => (
                <tr
                  key={lead.id}
                  onClick={() => setSelectedLead(lead)}
                  className="border-b border-gray-800/50 hover:bg-gray-800/30 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3 text-white font-medium">
                    {lead.email || lead.raw_email || "—"}
                  </td>
                  <td className="px-4 py-3">
                    {lead.first_name || lead.raw_first_name || ""}{" "}
                    {lead.last_name || lead.raw_last_name || ""}
                  </td>
                  <td className="px-4 py-3 text-gray-400">
                    {lead.company_name || lead.raw_company || "—"}
                  </td>
                  <td className="px-4 py-3 text-gray-400">
                    {lead.job_title || lead.raw_title || "—"}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={cn(
                        "px-2 py-0.5 rounded-full text-xs font-medium",
                        statusColor(lead.pipeline_status)
                      )}
                    >
                      {lead.pipeline_status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {lead.icp_qualified === true && (
                      <span className="text-green-400">Yes</span>
                    )}
                    {lead.icp_qualified === false && (
                      <span className="text-red-400">No</span>
                    )}
                    {lead.icp_qualified === null && (
                      <span className="text-gray-600">—</span>
                    )}
                  </td>
                </tr>
              ))}
              {leads.length === 0 && (
                <tr>
                  <td
                    colSpan={6}
                    className="px-4 py-12 text-center text-gray-500"
                  >
                    No leads found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Lead detail modal */}
      {selectedLead && (
        <LeadModal lead={selectedLead} onClose={() => setSelectedLead(null)} />
      )}
    </div>
  );
}

function LeadModal({ lead, onClose }: { lead: Lead; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 border border-gray-800 rounded-2xl max-w-2xl w-full max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-6 border-b border-gray-800">
          <h3 className="text-lg font-semibold text-white">
            {lead.email || lead.raw_email}
          </h3>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white transition-colors text-xl"
          >
            &times;
          </button>
        </div>
        <div className="p-6 space-y-4">
          <Section title="Contact">
            <Field label="Name" value={`${lead.first_name || lead.raw_first_name || ""} ${lead.last_name || lead.raw_last_name || ""}`} />
            <Field label="Email" value={lead.email || lead.raw_email} />
            <Field label="Company" value={lead.company_name || lead.raw_company} />
            <Field label="Title" value={lead.job_title || lead.raw_title} />
            <Field label="Website" value={lead.website} />
          </Section>

          <Section title="Qualification">
            <Field label="Status" value={lead.pipeline_status} />
            <Field
              label="ICP Qualified"
              value={
                lead.icp_qualified === null
                  ? "Pending"
                  : lead.icp_qualified
                  ? "Yes"
                  : "No"
              }
            />
            <Field label="ICP Reason" value={lead.icp_reason} />
            <Field
              label="Title Relevant"
              value={
                lead.title_relevant === null
                  ? "Pending"
                  : lead.title_relevant
                  ? "Yes"
                  : "No"
              }
            />
          </Section>

          {lead.company_summary && (
            <Section title="Company Summary">
              <p className="text-sm text-gray-300 whitespace-pre-wrap">
                {lead.company_summary}
              </p>
            </Section>
          )}

          {lead.email_body && (
            <Section title="Generated Email">
              <Field label="Subject" value={lead.email_subject} />
              <p className="text-sm text-gray-300 whitespace-pre-wrap mt-2">
                {lead.email_body}
              </p>
            </Section>
          )}

          {lead.error_message && (
            <Section title="Error">
              <p className="text-sm text-red-400">{lead.error_message}</p>
            </Section>
          )}
        </div>
      </div>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
        {title}
      </h4>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function Field({
  label,
  value,
}: {
  label: string;
  value: string | null | undefined;
}) {
  if (!value) return null;
  return (
    <div className="flex gap-3 text-sm">
      <span className="text-gray-500 w-28 shrink-0">{label}</span>
      <span className="text-gray-200">{value}</span>
    </div>
  );
}
