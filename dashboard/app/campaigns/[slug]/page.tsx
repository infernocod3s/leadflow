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

// Column mapping (mirrors leadflow/integrations/csv_handler.py)
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
  "title_relevant", "email_subject", "email_body", "pipeline_status",
];

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
    "imported", "in_progress", "enriched", "email_generated",
    "qualified", "disqualified", "pushed", "error",
  ];

  return (
    <div className="space-y-8">
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
            <button onClick={() => setShowImport(true)} className="btn-secondary">
              Import CSV
            </button>
            <button onClick={handleExport} className="btn-secondary">
              Export CSV
            </button>
            <button onClick={() => setShowPush(true)} className="btn-secondary">
              Push to Smartlead
            </button>
            <button onClick={() => setShowConfig(true)} className="btn-secondary">
              Edit Config
            </button>
          </div>
        </div>
      </div>

      {/* Status breakdown */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-9 gap-3">
        <button
          onClick={() => setFilter("all")}
          className={cn(
            "bg-gray-900 border rounded-xl p-3 text-left transition-colors",
            filter === "all" ? "border-blue-500" : "border-gray-800 hover:border-gray-700"
          )}
        >
          <div className="text-xs text-gray-500">All</div>
          <div className="text-lg font-bold text-white">{formatNumber(totalLeads)}</div>
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
            <div className="text-xs text-gray-500">{s.replace(/_/g, " ")}</div>
            <div className="text-lg font-bold text-white">{formatNumber(statusCounts[s] || 0)}</div>
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
                  <tr key={s.step_name} className="border-b border-gray-800/50">
                    <td className="py-2 pr-4 text-white font-medium">{s.step_name}</td>
                    <td className="py-2 pr-4 text-right">{formatNumber(s.total_calls)}</td>
                    <td className="py-2 pr-4 text-right text-green-400">{formatNumber(s.success_count)}</td>
                    <td className="py-2 pr-4 text-right text-red-400">
                      {s.failure_count > 0 ? formatNumber(s.failure_count) : "—"}
                    </td>
                    <td className="py-2 pr-4 text-right text-gray-400">{Math.round(s.avg_duration_ms)}ms</td>
                    <td className="py-2 text-right text-emerald-400">{formatCost(s.total_cost)}</td>
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
              (showing {leads.length}{filter !== "all" ? ` ${filter}` : ""})
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
                  <td colSpan={6} className="px-4 py-12 text-center text-gray-500">
                    No leads found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modals */}
      {selectedLead && <LeadModal lead={selectedLead} onClose={() => setSelectedLead(null)} />}
      {showImport && campaign && (
        <ImportModal
          campaignId={campaign.id}
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

// ── Import CSV Modal ────────────────────────────────────────────────────────

function ImportModal({
  campaignId,
  onClose,
  onDone,
}: {
  campaignId: string;
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
          pipeline_status: "imported",
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
                "border-2 border-dashed rounded-xl p-12 text-center transition-colors",
                dragOver ? "border-blue-500 bg-blue-500/10" : "border-gray-700"
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
                        <tr className="text-gray-500 border-b border-gray-800">
                          {columns.slice(0, 6).map((col) => (
                            <th key={col} className="pb-1 pr-3 text-left">{col}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {parsed.slice(0, 5).map((row, i) => (
                          <tr key={i} className="border-b border-gray-800/50">
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
                  <div className="w-full bg-gray-800 rounded-full h-2">
                    <div
                      className="bg-blue-500 h-2 rounded-full transition-all"
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
          <div className="bg-gray-800 rounded-lg p-3 text-sm">
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
            <div className="bg-red-900/30 border border-red-800 rounded-lg p-3 text-sm text-red-400">
              {error}
            </div>
          )}

          {result ? (
            <div className="space-y-2">
              <div className="bg-green-900/30 border border-green-800 rounded-lg p-3 text-sm text-green-400">
                Pushed {result.pushed} leads to Smartlead
              </div>
              {result.errors && result.errors.length > 0 && (
                <div className="bg-red-900/30 border border-red-800 rounded-lg p-3 text-sm text-red-400">
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
            <div className="bg-red-900/30 border border-red-800 rounded-lg p-3 text-sm text-red-400">
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

function LeadModal({ lead, onClose }: { lead: Lead; onClose: () => void }) {
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
              <p className="text-sm text-red-400">{lead.error_message}</p>
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
      className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 border border-gray-800 rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}

function ModalHeader({ title, onClose }: { title: string; onClose: () => void }) {
  return (
    <div className="flex items-center justify-between p-6 border-b border-gray-800">
      <h3 className="text-lg font-semibold text-white">{title}</h3>
      <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors text-xl">
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
