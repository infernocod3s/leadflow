"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import Papa from "papaparse";
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

// Column mapping (mirrors growthpal/integrations/csv_handler.py)
const COLUMN_MAPPING: Record<string, string> = {
  email: "raw_email",
  "e-mail": "raw_email",
  email_address: "raw_email",
  first_name: "raw_first_name",
  firstname: "raw_first_name",
  "first name": "raw_first_name",
  last_name: "raw_last_name",
  lastname: "raw_last_name",
  "last name": "raw_last_name",
  company: "raw_company",
  company_name: "raw_company",
  organization: "raw_company",
  title: "raw_title",
  job_title: "raw_title",
  jobtitle: "raw_title",
  position: "raw_title",
  website: "raw_website",
  company_website: "raw_website",
  url: "raw_website",
  domain: "raw_website",
  linkedin: "raw_linkedin",
  linkedin_url: "raw_linkedin",
  linkedin_profile: "raw_linkedin",
  phone: "raw_phone",
  phone_number: "raw_phone",
  location: "raw_location",
  city: "raw_location",
  industry: "raw_industry",
};

const EXPORT_FIELDS = [
  "email", "first_name", "last_name", "company_name", "job_title",
  "website", "company_summary", "icp_qualified", "icp_reason",
  "title_relevant", "email_subject", "email_body",
  "strategy_id", "strategy_name", "pipeline_status",
];

const BATCH_SIZES = [10, 20, 50, 100];

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

  // Modal states
  const [showImport, setShowImport] = useState(false);
  const [showPush, setShowPush] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [retrying, setRetrying] = useState(false);

  const loadCampaign = useCallback(async () => {
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

    const { data: allLeads } = await getSupabase()
      .from("leads")
      .select("pipeline_status")
      .eq("campaign_id", cData.id);

    const counts: Record<string, number> = {};
    for (const l of allLeads || []) {
      counts[l.pipeline_status] = (counts[l.pipeline_status] || 0) + 1;
    }
    setStatusCounts(counts);

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

    for (const s of Object.values(stepMap)) {
      s.avg_duration_ms = s.total_calls > 0 ? s.avg_duration_ms / s.total_calls : 0;
    }

    setStepCosts(Object.values(stepMap));
    setTotalCost(cost);
    setLoading(false);
  }, [slug, filter]);

  useEffect(() => {
    loadCampaign();
    const interval = setInterval(loadCampaign, 10000);
    return () => clearInterval(interval);
  }, [loadCampaign]);

  async function handleExport() {
    if (!campaign) return;
    const { data } = await getSupabase()
      .from("leads")
      .select("*")
      .eq("campaign_id", campaign.id)
      .in("pipeline_status", ["enriched", "qualified", "email_generated", "pushed"]);

    if (!data || data.length === 0) {
      alert("No enriched leads to export.");
      return;
    }

    const rows = data.map((lead) => {
      const row: Record<string, string> = {};
      for (const field of EXPORT_FIELDS) {
        const val = (lead as any)[field];
        row[field] = val === null || val === undefined ? "" : String(val);
      }
      return row;
    });

    const csv = Papa.unparse(rows, { columns: EXPORT_FIELDS });
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${slug}-leads.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function handleRetryErrors() {
    if (!campaign) return;
    setRetrying(true);
    try {
      const res = await fetch("/api/retry-errors", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ campaign_id: campaign.id }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      loadCampaign();
    } catch (err: any) {
      alert(`Retry failed: ${err.message}`);
    }
    setRetrying(false);
  }

  if (loading) {
    return (
      <div className="space-y-8 animate-fade-in">
        <div>
          <div className="skeleton h-4 w-28 mb-3" />
          <div className="flex items-center justify-between">
            <div>
              <div className="skeleton h-7 w-48 mb-2" />
              <div className="skeleton h-4 w-64" />
            </div>
            <div className="flex gap-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="skeleton h-9 w-24 rounded-lg" />
              ))}
            </div>
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-9 gap-3">
          {Array.from({ length: 9 }).map((_, i) => (
            <div key={i} className="card p-3">
              <div className="skeleton h-3 w-12 mb-2" />
              <div className="skeleton h-5 w-8" />
            </div>
          ))}
        </div>
        <div className="card p-6">
          <div className="skeleton h-5 w-32 mb-4" />
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="skeleton h-8 w-full mb-2" />
          ))}
        </div>
      </div>
    );
  }

  if (!campaign) {
    return (
      <div className="text-center py-20 animate-fade-in">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gray-800/60 mb-4">
          <svg className="w-8 h-8 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
          </svg>
        </div>
        <p className="text-gray-300 text-lg mb-1">Campaign not found</p>
        <p className="text-gray-500 text-sm mb-6">No campaign matching &ldquo;{slug}&rdquo; exists.</p>
        <Link href="/" className="btn-secondary">
          &larr; Back to dashboard
        </Link>
      </div>
    );
  }

  const totalLeads = Object.values(statusCounts).reduce((a, b) => a + b, 0);
  const statuses = [
    "queued", "imported", "in_progress", "enriched", "email_generated",
    "qualified", "disqualified", "pushed", "error",
  ];

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Header */}
      <div>
        <Link href="/" className="text-sm text-gray-500 hover:text-gray-300 mb-2 block">
          &larr; All Campaigns
        </Link>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">{slug}</h1>
            <p className="text-sm text-gray-500">
              {(campaign.clients as any)?.name || "—"} &middot; {formatDate(campaign.created_at)}
              {campaign.smartlead_campaign_id && (
                <> &middot; Smartlead #{campaign.smartlead_campaign_id}</>
              )}
            </p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => setShowImport(true)} className="btn-secondary text-xs">
              Import CSV
            </button>
            <button onClick={handleExport} className="btn-secondary text-xs">
              Export CSV
            </button>
            <button onClick={() => setShowPush(true)} className="btn-secondary text-xs">
              Push to Smartlead
            </button>
            {(statusCounts["error"] || 0) > 0 && (
              <button
                onClick={handleRetryErrors}
                disabled={retrying}
                className="btn-secondary text-xs text-red-400 border-red-500/20 hover:border-red-500/40"
              >
                {retrying ? "Retrying..." : `Retry ${statusCounts["error"]} Errors`}
              </button>
            )}
            <button onClick={() => setShowConfig(true)} className="btn-secondary text-xs">
              Config
            </button>
          </div>
        </div>
      </div>

      {/* Status breakdown */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-9 gap-3">
        <button
          onClick={() => setFilter("all")}
          className={cn(
            "card p-3 text-left transition-all duration-200",
            filter === "all"
              ? "border-amber-500/60 bg-amber-500/5 shadow-glow-gold-sm"
              : "hover:border-gray-700/60"
          )}
        >
          <div className="text-[10px] text-gray-500 uppercase tracking-wider">All</div>
          <div className="text-lg font-bold text-white tabular-nums">{formatNumber(totalLeads)}</div>
        </button>
        {statuses.map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={cn(
              "card p-3 text-left transition-all duration-200",
              filter === s
                ? "border-amber-500/60 bg-amber-500/5 shadow-glow-gold-sm"
                : "hover:border-gray-700/60"
            )}
          >
            <div className="text-[10px] text-gray-500 uppercase tracking-wider">{s.replace(/_/g, " ")}</div>
            <div className="text-lg font-bold text-white tabular-nums">{formatNumber(statusCounts[s] || 0)}</div>
          </button>
        ))}
      </div>

      {/* Progressive Execution Panel */}
      {campaign.config && (campaign.config as any).progressive_batch?.enabled && (
        <ProgressivePanel
          campaign={campaign}
          statusCounts={statusCounts}
          totalLeads={totalLeads}
          onRefresh={loadCampaign}
        />
      )}

      {/* Strategy Distribution */}
      {campaign.config && (campaign.config as any).strategy_routing?.strategies?.length > 0 && (
        <StrategyDistribution campaignId={campaign.id} />
      )}

      {/* Cost and step breakdown */}
      {stepCosts.length > 0 && (
        <div className="card p-6">
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
                <tr className="text-left border-b border-gray-800/40">
                  <th className="table-header pb-2 pr-4">Step</th>
                  <th className="table-header pb-2 pr-4 text-right">Calls</th>
                  <th className="table-header pb-2 pr-4 text-right">Success</th>
                  <th className="table-header pb-2 pr-4 text-right">Failures</th>
                  <th className="table-header pb-2 pr-4 text-right">Avg Time</th>
                  <th className="table-header pb-2 text-right">Cost</th>
                </tr>
              </thead>
              <tbody>
                {stepCosts.map((s) => (
                  <tr key={s.step_name} className="table-row">
                    <td className="py-2 pr-4 text-white font-medium">{s.step_name}</td>
                    <td className="py-2 pr-4 text-right tabular-nums">{formatNumber(s.total_calls)}</td>
                    <td className="py-2 pr-4 text-right text-green-400 tabular-nums">{formatNumber(s.success_count)}</td>
                    <td className="py-2 pr-4 text-right text-red-400 tabular-nums">
                      {s.failure_count > 0 ? formatNumber(s.failure_count) : "—"}
                    </td>
                    <td className="py-2 pr-4 text-right text-gray-400 tabular-nums">{Math.round(s.avg_duration_ms)}ms</td>
                    <td className="py-2 text-right text-emerald-400 tabular-nums">{formatCost(s.total_cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Leads table */}
      <div className="card overflow-hidden">
        <div className="p-4 border-b border-gray-800/40">
          <h2 className="text-lg font-semibold text-white">
            Leads{" "}
            <span className="text-sm text-gray-500 font-normal">
              (showing {leads.length}{filter !== "all" ? ` ${filter}` : ""})
            </span>
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b border-gray-800/40 bg-gray-900/50">
                <th className="table-header px-4 py-3">Email</th>
                <th className="table-header px-4 py-3">Name</th>
                <th className="table-header px-4 py-3">Company</th>
                <th className="table-header px-4 py-3">Title</th>
                <th className="table-header px-4 py-3">Strategy</th>
                <th className="table-header px-4 py-3">Status</th>
                <th className="table-header px-4 py-3">ICP</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((lead) => (
                <tr
                  key={lead.id}
                  onClick={() => setSelectedLead(lead)}
                  className="table-row cursor-pointer group"
                >
                  <td className="px-4 py-3 text-white font-medium group-hover:text-amber-400/90 transition-colors">
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
                  <td className="px-4 py-3 text-xs text-gray-400">
                    {(lead as any).strategy_name || (lead as any).strategy_id || "—"}
                  </td>
                  <td className="px-4 py-3">
                    <span className={cn("px-2 py-0.5 rounded-full text-xs font-medium", statusColor(lead.pipeline_status))}>
                      {lead.pipeline_status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {lead.icp_qualified === true && <span className="text-green-400">Yes</span>}
                    {lead.icp_qualified === false && <span className="text-red-400">No</span>}
                    {lead.icp_qualified === null && <span className="text-gray-600">—</span>}
                  </td>
                </tr>
              ))}
              {leads.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-gray-500">
                    {filter !== "all"
                      ? `No leads with status "${filter.replace(/_/g, " ")}". Try selecting a different filter.`
                      : "No leads found. Import a CSV to get started."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modals */}
      {selectedLead && <LeadModal lead={selectedLead} onClose={() => setSelectedLead(null)} onRetry={loadCampaign} />}
      {showImport && campaign && (
        <ImportModal
          campaignId={campaign.id}
          progressiveMode={!!(campaign.config as any)?.progressive_batch?.enabled}
          onClose={() => setShowImport(false)}
          onDone={() => { setShowImport(false); loadCampaign(); }}
        />
      )}
      {showPush && campaign && (
        <PushModal
          campaign={campaign}
          readyCount={statusCounts["email_generated"] || 0}
          onClose={() => setShowPush(false)}
          onDone={() => { setShowPush(false); loadCampaign(); }}
        />
      )}
      {showConfig && campaign && (
        <ConfigModal
          campaign={campaign}
          onClose={() => setShowConfig(false)}
          onSaved={() => { setShowConfig(false); loadCampaign(); }}
        />
      )}
    </div>
  );
}

// ── Progressive Execution Panel ──────────────────────────────────────────────

function ProgressivePanel({
  campaign,
  statusCounts,
  totalLeads,
  onRefresh,
}: {
  campaign: Campaign;
  statusCounts: Record<string, number>;
  totalLeads: number;
  onRefresh: () => void;
}) {
  const [releasing, setReleasing] = useState(false);
  const [result, setResult] = useState<{ released: number; message: string } | null>(null);

  const queuedCount = statusCounts["queued"] || 0;
  const releasedCount = totalLeads - queuedCount;
  const batchConfig = (campaign.config as any)?.progressive_batch;
  const batchSizes: number[] = batchConfig?.batch_sizes || BATCH_SIZES;

  // Determine which batch we're on based on cumulative releases
  let currentBatchIndex = 0;
  let cumulative = 0;
  for (let i = 0; i < batchSizes.length; i++) {
    cumulative += batchSizes[i];
    if (releasedCount < cumulative) {
      currentBatchIndex = i;
      break;
    }
    if (i === batchSizes.length - 1) {
      currentBatchIndex = batchSizes.length; // Past all defined batches
    }
  }

  const allBatchesDone = currentBatchIndex >= batchSizes.length;
  const nextBatchSize = allBatchesDone ? queuedCount : batchSizes[currentBatchIndex] - (releasedCount - (currentBatchIndex > 0 ? batchSizes.slice(0, currentBatchIndex).reduce((a, b) => a + b, 0) : 0));
  const effectiveNextBatch = allBatchesDone ? queuedCount : Math.min(batchSizes[currentBatchIndex], queuedCount);

  // Processing stats
  const inProgress = statusCounts["in_progress"] || 0;
  const processed = (statusCounts["enriched"] || 0) + (statusCounts["email_generated"] || 0) +
    (statusCounts["qualified"] || 0) + (statusCounts["disqualified"] || 0) +
    (statusCounts["pushed"] || 0) + (statusCounts["error"] || 0);
  const isProcessing = inProgress > 0;

  async function releaseBatch(size: number) {
    setReleasing(true);
    setResult(null);
    try {
      const res = await fetch("/api/release-batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          campaign_id: campaign.id,
          batch_size: size,
          batch_number: currentBatchIndex + 1,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      setResult(data);
      onRefresh();
    } catch (err: any) {
      setResult({ released: 0, message: err.message });
    }
    setReleasing(false);
  }

  async function releaseAll() {
    await releaseBatch(queuedCount);
  }

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-semibold text-white">Progressive Execution</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Review results at each stage before scaling up
          </p>
        </div>
        {isProcessing && (
          <div className="flex items-center gap-2 text-xs text-amber-400">
            <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
            Processing {inProgress} leads...
          </div>
        )}
      </div>

      {/* Batch stages visualization */}
      <div className="flex items-center gap-1 mb-4 overflow-x-auto pb-1">
        {batchSizes.map((size, i) => {
          const cumulativeUpTo = batchSizes.slice(0, i + 1).reduce((a, b) => a + b, 0);
          const isDone = releasedCount >= cumulativeUpTo;
          const isCurrent = !isDone && (i === 0 || releasedCount >= batchSizes.slice(0, i).reduce((a, b) => a + b, 0));
          return (
            <div key={i} className="flex items-center gap-1">
              <div
                className={cn(
                  "px-3 py-1.5 rounded-lg text-xs font-mono transition-all",
                  isDone
                    ? "bg-green-500/10 text-green-400 border border-green-500/20"
                    : isCurrent
                    ? "bg-amber-500/10 text-amber-400 border border-amber-500/30 shadow-glow-gold-sm"
                    : "bg-gray-800/40 text-gray-500 border border-gray-800/40"
                )}
              >
                {isDone && <span className="mr-1">&#10003;</span>}
                {size}
              </div>
              {i < batchSizes.length - 1 && (
                <svg className="w-3 h-3 text-gray-700 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              )}
            </div>
          );
        })}
        <svg className="w-3 h-3 text-gray-700 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        <div
          className={cn(
            "px-3 py-1.5 rounded-lg text-xs font-mono transition-all",
            queuedCount === 0 && totalLeads > 0
              ? "bg-green-500/10 text-green-400 border border-green-500/20"
              : allBatchesDone && queuedCount > 0
              ? "bg-amber-500/10 text-amber-400 border border-amber-500/30"
              : "bg-gray-800/40 text-gray-500 border border-gray-800/40"
          )}
        >
          {queuedCount === 0 && totalLeads > 0 ? "✓ " : ""}All
        </div>
      </div>

      {/* Progress bar */}
      <div className="mb-4">
        <div className="flex justify-between text-xs text-gray-500 mb-1">
          <span>{releasedCount} released</span>
          <span>{queuedCount} queued</span>
        </div>
        <div className="w-full bg-gray-800/50 rounded-full h-1.5">
          <div
            className="bg-gradient-to-r from-amber-600 to-amber-400 h-1.5 rounded-full transition-all duration-500"
            style={{ width: `${totalLeads > 0 ? (releasedCount / totalLeads) * 100 : 0}%` }}
          />
        </div>
      </div>

      {/* Actions */}
      {result && (
        <div className={cn(
          "rounded-lg p-3 text-sm mb-3",
          result.released > 0
            ? "bg-green-500/10 border border-green-500/20 text-green-400"
            : "bg-red-500/10 border border-red-500/20 text-red-400"
        )}>
          {result.message}
        </div>
      )}

      {queuedCount > 0 ? (
        <div className="flex gap-2">
          {!allBatchesDone ? (
            <button
              onClick={() => releaseBatch(effectiveNextBatch)}
              disabled={releasing || isProcessing}
              className="btn-primary text-sm"
            >
              {releasing
                ? "Releasing..."
                : isProcessing
                ? "Wait for processing..."
                : `Run Next Batch (${effectiveNextBatch} leads)`}
            </button>
          ) : (
            <button
              onClick={releaseAll}
              disabled={releasing || isProcessing}
              className="btn-primary text-sm"
            >
              {releasing
                ? "Releasing..."
                : isProcessing
                ? "Wait for processing..."
                : `Run All Remaining (${queuedCount} leads)`}
            </button>
          )}
          {!allBatchesDone && queuedCount > effectiveNextBatch && (
            <button
              onClick={releaseAll}
              disabled={releasing || isProcessing}
              className="btn-secondary text-sm"
            >
              Skip to All ({queuedCount})
            </button>
          )}
        </div>
      ) : totalLeads > 0 ? (
        <div className="text-sm text-green-400">
          All leads released and processed. Review results below.
        </div>
      ) : (
        <div className="text-sm text-gray-500">
          Import leads to get started. They&apos;ll be queued for progressive execution.
        </div>
      )}
    </div>
  );
}

// ── Strategy Distribution ───────────────────────────────────────────────────

function StrategyDistribution({ campaignId }: { campaignId: string }) {
  const [distribution, setDistribution] = useState<Record<string, number>>({});
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    async function load() {
      const { data } = await getSupabase()
        .from("leads")
        .select("strategy_id, strategy_name")
        .eq("campaign_id", campaignId)
        .not("strategy_id", "is", null);

      if (!data || data.length === 0) {
        setLoaded(true);
        return;
      }

      const counts: Record<string, number> = {};
      for (const lead of data) {
        const label = lead.strategy_name || lead.strategy_id || "unknown";
        counts[label] = (counts[label] || 0) + 1;
      }
      setDistribution(counts);
      setLoaded(true);
    }
    load();
  }, [campaignId]);

  if (!loaded || Object.keys(distribution).length === 0) return null;

  const total = Object.values(distribution).reduce((a, b) => a + b, 0);
  const colors = [
    "bg-blue-400", "bg-emerald-400", "bg-purple-400", "bg-orange-400",
    "bg-pink-400", "bg-cyan-400", "bg-yellow-400",
  ];

  return (
    <div className="card p-6">
      <h2 className="text-sm font-semibold text-white mb-3">Strategy Distribution</h2>
      <div className="w-full bg-gray-800/50 rounded-full h-3 flex overflow-hidden mb-3">
        {Object.entries(distribution).map(([name, count], i) => (
          <div
            key={name}
            className={cn("h-3 transition-all duration-500", colors[i % colors.length])}
            style={{ width: `${(count / total) * 100}%` }}
            title={`${name}: ${count}`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {Object.entries(distribution).map(([name, count], i) => (
          <div key={name} className="flex items-center gap-1.5 text-xs">
            <div className={cn("w-2 h-2 rounded-full", colors[i % colors.length])} />
            <span className="text-gray-300">{name}</span>
            <span className="text-gray-500">{count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Import CSV Modal ────────────────────────────────────────────────────────

function ImportModal({
  campaignId,
  progressiveMode,
  onClose,
  onDone,
}: {
  campaignId: string;
  progressiveMode?: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [parsed, setParsed] = useState<Record<string, string>[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [importing, setImporting] = useState(false);
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [dragOver, setDragOver] = useState(false);

  const targetFields = [
    { value: "", label: "Skip" },
    { value: "raw_email", label: "Email" },
    { value: "raw_first_name", label: "First Name" },
    { value: "raw_last_name", label: "Last Name" },
    { value: "raw_company", label: "Company" },
    { value: "raw_title", label: "Job Title" },
    { value: "raw_website", label: "Website" },
    { value: "raw_linkedin", label: "LinkedIn" },
    { value: "raw_phone", label: "Phone" },
    { value: "raw_location", label: "Location" },
    { value: "raw_industry", label: "Industry" },
  ];

  function handleFile(f: File) {
    setFile(f);
    Papa.parse(f, {
      header: true,
      skipEmptyLines: true,
      complete: (result) => {
        const data = result.data as Record<string, string>[];
        setParsed(data);
        const cols = result.meta.fields || [];
        setColumns(cols);

        // Auto-map columns
        const autoMap: Record<string, string> = {};
        for (const col of cols) {
          const normalized = col.trim().toLowerCase().replace(/\s+/g, "_");
          const mapped = COLUMN_MAPPING[normalized];
          if (mapped) autoMap[col] = mapped;
        }
        setMapping(autoMap);
      },
    });
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f && f.name.endsWith(".csv")) handleFile(f);
  }

  const validRows = parsed.filter((row) => {
    const emailCol = Object.entries(mapping).find(([, v]) => v === "raw_email")?.[0];
    return emailCol && row[emailCol]?.trim();
  });

  async function handleImport() {
    if (validRows.length === 0) return;
    setImporting(true);
    setProgress({ done: 0, total: validRows.length });

    const BATCH_SIZE = 500;
    let done = 0;

    for (let i = 0; i < validRows.length; i += BATCH_SIZE) {
      const batch = validRows.slice(i, i + BATCH_SIZE);
      const leads = batch.map((row) => {
        const lead: Record<string, string> = {
          campaign_id: campaignId,
          pipeline_status: progressiveMode ? "queued" : "imported",
        };
        for (const [csvCol, dbField] of Object.entries(mapping)) {
          if (dbField && row[csvCol]?.trim()) {
            lead[dbField] = row[csvCol].trim();
          }
        }
        // Copy raw email to email for lookups
        if (lead.raw_email) lead.email = lead.raw_email;
        return lead;
      });

      await getSupabase().from("leads").insert(leads);
      done += batch.length;
      setProgress({ done, total: validRows.length });
    }

    onDone();
  }

  return (
    <ModalOverlay onClose={onClose}>
      <div className="max-w-3xl w-full">
        <ModalHeader title="Import Leads from CSV" onClose={onClose} />
        <div className="p-6 space-y-6">
          {!file ? (
            <div
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              className={cn(
                "border-2 border-dashed rounded-xl p-12 text-center transition-all duration-200",
                dragOver ? "border-amber-500 bg-amber-500/5 shadow-glow-gold" : "border-gray-700"
              )}
            >
              <p className="text-gray-400 mb-3">Drag & drop a CSV file here, or</p>
              <label className="btn-primary cursor-pointer inline-block">
                Browse Files
                <input
                  type="file"
                  accept=".csv"
                  className="hidden"
                  onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                />
              </label>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-white font-medium">{file.name}</p>
                  <p className="text-sm text-gray-500">
                    {parsed.length} rows &middot; {validRows.length} with email
                  </p>
                </div>
                <button onClick={() => { setFile(null); setParsed([]); setColumns([]); setMapping({}); }} className="text-sm text-gray-500 hover:text-white">
                  Change file
                </button>
              </div>

              {/* Column mapping */}
              <div>
                <h3 className="text-sm font-medium text-gray-400 mb-3">Column Mapping</h3>
                <div className="grid grid-cols-2 gap-2">
                  {columns.map((col) => (
                    <div key={col} className="flex items-center gap-2">
                      <span className="text-sm text-gray-300 w-1/2 truncate" title={col}>{col}</span>
                      <select
                        value={mapping[col] || ""}
                        onChange={(e) => setMapping((m) => ({ ...m, [col]: e.target.value }))}
                        className="input flex-1 text-xs"
                      >
                        {targetFields.map((f) => (
                          <option key={f.value} value={f.value}>{f.label}</option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>
              </div>

              {/* Preview */}
              {parsed.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-gray-400 mb-2">Preview (first 5 rows)</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-gray-800/40">
                          {columns.slice(0, 6).map((col) => (
                            <th key={col} className="table-header pb-1 pr-3 text-left">{col}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {parsed.slice(0, 5).map((row, i) => (
                          <tr key={i} className="table-row">
                            {columns.slice(0, 6).map((col) => (
                              <td key={col} className="py-1 pr-3 text-gray-300 max-w-[150px] truncate">{row[col]}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Import button */}
              {importing ? (
                <div>
                  <div className="flex justify-between text-sm text-gray-400 mb-1">
                    <span>Importing...</span>
                    <span>{progress.done} / {progress.total}</span>
                  </div>
                  <div className="w-full bg-gray-800/50 rounded-full h-1.5">
                    <div
                      className="bg-gradient-to-r from-amber-600 to-amber-400 h-1.5 rounded-full transition-all duration-500"
                      style={{ width: `${progress.total > 0 ? (progress.done / progress.total) * 100 : 0}%` }}
                    />
                  </div>
                </div>
              ) : (
                <button
                  onClick={handleImport}
                  disabled={validRows.length === 0}
                  className="btn-primary w-full py-3"
                >
                  Import {validRows.length} leads
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </ModalOverlay>
  );
}

// ── Push to Smartlead Modal ─────────────────────────────────────────────────

function PushModal({
  campaign,
  readyCount,
  onClose,
  onDone,
}: {
  campaign: Campaign;
  readyCount: number;
  onClose: () => void;
  onDone: () => void;
}) {
  const [smartleadId, setSmartleadId] = useState(
    campaign.smartlead_campaign_id?.toString() || ""
  );
  const [limit, setLimit] = useState("500");
  const [pushing, setPushing] = useState(false);
  const [result, setResult] = useState<{ pushed: number; errors?: string[] } | null>(null);
  const [error, setError] = useState("");

  async function handlePush() {
    if (!smartleadId) {
      setError("Smartlead campaign ID is required");
      return;
    }
    setPushing(true);
    setError("");

    try {
      const res = await fetch("/api/push-smartlead", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          campaign_id: campaign.id,
          smartlead_campaign_id: parseInt(smartleadId),
          limit: parseInt(limit),
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      setResult(data);

      // Update campaign smartlead_campaign_id if changed
      if (parseInt(smartleadId) !== campaign.smartlead_campaign_id) {
        await getSupabase()
          .from("campaigns")
          .update({ smartlead_campaign_id: parseInt(smartleadId) })
          .eq("id", campaign.id);
      }
    } catch (err: any) {
      setError(err.message);
    }
    setPushing(false);
  }

  return (
    <ModalOverlay onClose={onClose}>
      <div className="max-w-md w-full">
        <ModalHeader title="Push to Smartlead" onClose={onClose} />
        <div className="p-6 space-y-4">
          <div className="bg-gray-800/60 rounded-lg p-3 text-sm">
            <span className="text-gray-400">Leads ready to push: </span>
            <span className="text-white font-bold">{readyCount}</span>
            <span className="text-gray-500 ml-1">(status: email_generated)</span>
          </div>

          <div>
            <label className="block text-sm text-gray-300 mb-1">Smartlead Campaign ID</label>
            <input
              type="number"
              value={smartleadId}
              onChange={(e) => setSmartleadId(e.target.value)}
              placeholder="e.g. 12345"
              className="input"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-300 mb-1">Limit</label>
            <input
              type="number"
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
              className="input"
            />
          </div>

          {error && (
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-sm text-red-400">
              {error}
            </div>
          )}

          {result ? (
            <div className="space-y-2">
              <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-3 text-sm text-green-400">
                Pushed {result.pushed} leads to Smartlead
              </div>
              {result.errors && result.errors.length > 0 && (
                <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-sm text-red-400">
                  <p className="font-medium mb-1">{result.errors.length} errors:</p>
                  {result.errors.map((e, i) => <p key={i} className="text-xs">{e}</p>)}
                </div>
              )}
              <button onClick={onDone} className="btn-primary w-full">Done</button>
            </div>
          ) : (
            <button
              onClick={handlePush}
              disabled={pushing || readyCount === 0}
              className="btn-primary w-full"
            >
              {pushing ? "Pushing..." : `Push ${Math.min(readyCount, parseInt(limit) || 500)} leads`}
            </button>
          )}
        </div>
      </div>
    </ModalOverlay>
  );
}

// ── Config Editor Modal ─────────────────────────────────────────────────────

function ConfigModal({
  campaign,
  onClose,
  onSaved,
}: {
  campaign: Campaign;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [configJson, setConfigJson] = useState(
    JSON.stringify(campaign.config || {}, null, 2)
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSave() {
    setError("");
    try {
      const config = JSON.parse(configJson);
      setSaving(true);
      const { error: err } = await getSupabase()
        .from("campaigns")
        .update({ config, updated_at: new Date().toISOString() })
        .eq("id", campaign.id);
      if (err) throw err;
      onSaved();
    } catch (err: any) {
      setError(err.message || "Invalid JSON");
      setSaving(false);
    }
  }

  return (
    <ModalOverlay onClose={onClose}>
      <div className="max-w-2xl w-full">
        <ModalHeader title="Edit Campaign Config" onClose={onClose} />
        <div className="p-6 space-y-4">
          <p className="text-sm text-gray-500">
            Edit the campaign configuration JSON. This controls ICP definition, email settings, and pipeline behavior.
          </p>
          <textarea
            value={configJson}
            onChange={(e) => setConfigJson(e.target.value)}
            rows={20}
            className="input font-mono text-xs"
            spellCheck={false}
          />
          {error && (
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-sm text-red-400">
              {error}
            </div>
          )}
          <div className="flex gap-3 justify-end">
            <button onClick={onClose} className="btn-secondary">Cancel</button>
            <button onClick={handleSave} disabled={saving} className="btn-primary">
              {saving ? "Saving..." : "Save Config"}
            </button>
          </div>
        </div>
      </div>
    </ModalOverlay>
  );
}

// ── Lead Detail Modal ───────────────────────────────────────────────────────

function LeadModal({ lead, onClose, onRetry }: { lead: Lead; onClose: () => void; onRetry?: () => void }) {
  const [retryingLead, setRetryingLead] = useState(false);

  async function handleRetryLead() {
    setRetryingLead(true);
    try {
      const res = await fetch("/api/retry-errors", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ campaign_id: lead.campaign_id, lead_ids: [lead.id] }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      onRetry?.();
      onClose();
    } catch (err: any) {
      alert(`Retry failed: ${err.message}`);
    }
    setRetryingLead(false);
  }

  return (
    <ModalOverlay onClose={onClose}>
      <div className="max-w-2xl w-full max-h-[85vh] overflow-y-auto">
        <ModalHeader title={lead.email || lead.raw_email || "Lead"} onClose={onClose} />
        <div className="p-6 space-y-4">
          <Section title="Contact">
            <DetailField label="Name" value={`${lead.first_name || lead.raw_first_name || ""} ${lead.last_name || lead.raw_last_name || ""}`} />
            <DetailField label="Email" value={lead.email || lead.raw_email} />
            <DetailField label="Company" value={lead.company_name || lead.raw_company} />
            <DetailField label="Title" value={lead.job_title || lead.raw_title} />
            <DetailField label="Website" value={lead.website} />
          </Section>

          <Section title="Qualification">
            <DetailField label="Status" value={lead.pipeline_status} />
            <DetailField
              label="ICP Qualified"
              value={lead.icp_qualified === null ? "Pending" : lead.icp_qualified ? "Yes" : "No"}
            />
            <DetailField label="ICP Reason" value={lead.icp_reason} />
            <DetailField
              label="Title Relevant"
              value={lead.title_relevant === null ? "Pending" : lead.title_relevant ? "Yes" : "No"}
            />
            <DetailField label="Strategy" value={(lead as any).strategy_name || (lead as any).strategy_id} />
          </Section>

          {lead.company_summary && (
            <Section title="Company Summary">
              <p className="text-sm text-gray-300 whitespace-pre-wrap">{lead.company_summary}</p>
            </Section>
          )}

          {lead.email_body && (
            <Section title="Generated Email">
              <DetailField label="Subject" value={lead.email_subject} />
              <p className="text-sm text-gray-300 whitespace-pre-wrap mt-2">{lead.email_body}</p>
            </Section>
          )}

          {lead.error_message && (
            <Section title="Error">
              <p className="text-sm text-red-400 mb-3">{lead.error_message}</p>
              <button
                onClick={handleRetryLead}
                disabled={retryingLead}
                className="btn-primary text-xs"
              >
                {retryingLead ? "Retrying..." : "Retry This Lead"}
              </button>
            </Section>
          )}
        </div>
      </div>
    </ModalOverlay>
  );
}

// ── Shared Components ───────────────────────────────────────────────────────

function ModalOverlay({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  return (
    <div
      className="fixed inset-0 bg-black/70 backdrop-blur-md z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 border border-gray-800/60 rounded-2xl shadow-2xl animate-scale-in"
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}

function ModalHeader({ title, onClose }: { title: string; onClose: () => void }) {
  return (
    <div className="flex items-center justify-between p-6 border-b border-gray-800/40">
      <h3 className="text-lg font-semibold text-white">{title}</h3>
      <button onClick={onClose} className="text-gray-500 hover:text-white hover:bg-gray-800/60 transition-all rounded-lg w-8 h-8 flex items-center justify-center text-xl">
        &times;
      </button>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">{title}</h4>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function DetailField({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <div className="flex gap-3 text-sm">
      <span className="text-gray-500 w-28 shrink-0">{label}</span>
      <span className="text-gray-200">{value}</span>
    </div>
  );
}
