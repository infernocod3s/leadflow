"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getSupabase } from "@/lib/supabase";
import { cn } from "@/lib/utils";

const DEFAULT_EXCLUDED_DOMAINS = ["gmail.com", "yahoo.com", "hotmail.com"];

const BATCH_SIZES = [10, 20, 50, 100];

const SIGNAL_FIELDS = [
  { value: "hiring_signal.roles", label: "Hiring — Roles" },
  { value: "hiring_signal.count", label: "Hiring — Count" },
  { value: "hiring_signal.departments", label: "Hiring — Departments" },
  { value: "funding_signal.stage", label: "Funding — Stage" },
  { value: "funding_signal.amount", label: "Funding — Amount" },
  { value: "tech_stack", label: "Tech Stack" },
  { value: "industry", label: "Industry" },
  { value: "company_employee_count", label: "Employee Count" },
  { value: "company_summary", label: "Company Summary" },
];

const OPERATORS = [
  { value: "not_empty", label: "Has data", needsValue: false },
  { value: "empty", label: "Is empty", needsValue: false },
  { value: "eq", label: "Equals", needsValue: true },
  { value: "neq", label: "Not equals", needsValue: true },
  { value: "contains", label: "Contains", needsValue: true },
  { value: "contains_any", label: "Contains any of", needsValue: true },
  { value: "gt", label: ">", needsValue: true },
  { value: "gte", label: ">=", needsValue: true },
  { value: "lt", label: "<", needsValue: true },
  { value: "lte", label: "<=", needsValue: true },
  { value: "in", label: "In list", needsValue: true },
];

type Condition = {
  field: string;
  operator: string;
  value?: string;
};

type Strategy = {
  id: string;
  name: string;
  type: "signal" | "fallback";
  priority?: number;
  conditions: Condition[];
  email_prompt: string;
  campaign_name: string;
};

const STEPS = ["Company", "Targeting", "Strategies", "Review"];

export default function NewCampaignPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // Step 1: Company Info
  const [clientName, setClientName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugManual, setSlugManual] = useState(false);
  const [senderName, setSenderName] = useState("");
  const [senderCompany, setSenderCompany] = useState("");
  const [senderValueProp, setSenderValueProp] = useState("");
  const [emailCta, setEmailCta] = useState("");
  const [emailTone, setEmailTone] = useState("professional");

  // Step 2: Targeting
  const [icpDescription, setIcpDescription] = useState("");
  const [targetTitles, setTargetTitles] = useState<string[]>([]);
  const [targetIndustries, setTargetIndustries] = useState<string[]>([]);
  const [excludedDomains, setExcludedDomains] = useState<string[]>(DEFAULT_EXCLUDED_DOMAINS);

  // Step 3: Strategies
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [routingMode, setRoutingMode] = useState<"testing" | "optimization">("testing");
  const [progressiveMode, setProgressiveMode] = useState(true);


  function generateSlug(name: string) {
    return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  }

  function handleClientNameChange(val: string) {
    setClientName(val);
    if (!slugManual) setSlug(generateSlug(val));
  }

  function addStrategy(type: "signal" | "fallback") {
    const id = `${type}-${Date.now()}`;
    setStrategies((s) => [
      ...s,
      {
        id,
        name: "",
        type,
        conditions: type === "signal" ? [{ field: "", operator: "not_empty" }] : [],
        email_prompt: "",
        campaign_name: "",
      },
    ]);
  }

  function updateStrategy(index: number, updates: Partial<Strategy>) {
    setStrategies((s) => s.map((st, i) => (i === index ? { ...st, ...updates } : st)));
  }

  function removeStrategy(index: number) {
    setStrategies((s) => s.filter((_, i) => i !== index));
  }

  function moveStrategy(index: number, direction: -1 | 1) {
    setStrategies((s) => {
      const arr = [...s];
      const target = index + direction;
      if (target < 0 || target >= arr.length) return arr;
      [arr[index], arr[target]] = [arr[target], arr[index]];
      return arr;
    });
  }

  function addCondition(strategyIndex: number) {
    setStrategies((s) =>
      s.map((st, i) =>
        i === strategyIndex
          ? { ...st, conditions: [...st.conditions, { field: "", operator: "not_empty" }] }
          : st
      )
    );
  }

  function updateCondition(strategyIndex: number, condIndex: number, updates: Partial<Condition>) {
    setStrategies((s) =>
      s.map((st, i) =>
        i === strategyIndex
          ? {
              ...st,
              conditions: st.conditions.map((c, j) => (j === condIndex ? { ...c, ...updates } : c)),
            }
          : st
      )
    );
  }

  function removeCondition(strategyIndex: number, condIndex: number) {
    setStrategies((s) =>
      s.map((st, i) =>
        i === strategyIndex
          ? { ...st, conditions: st.conditions.filter((_, j) => j !== condIndex) }
          : st
      )
    );
  }

  function canAdvance(): boolean {
    if (step === 0) return !!(clientName.trim() && slug.trim() && senderName.trim() && senderCompany.trim());
    if (step === 1) return !!icpDescription.trim();
    return true;
  }

  async function handleSubmit() {
    setError("");
    if (!clientName.trim() || !slug.trim()) {
      setError("Client name and slug are required.");
      return;
    }

    setSaving(true);
    try {
      // Get or create client
      const { data: existingClient } = await getSupabase()
        .from("clients")
        .select("id")
        .eq("name", clientName.trim())
        .single();

      let clientId: string;
      if (existingClient) {
        clientId = existingClient.id;
      } else {
        const { data: newClient, error: clientErr } = await getSupabase()
          .from("clients")
          .insert({ name: clientName.trim() })
          .select("id")
          .single();
        if (clientErr) throw clientErr;
        clientId = newClient!.id;
      }

      // Build config
      const config: Record<string, unknown> = {
        sender_name: senderName.trim(),
        sender_company: senderCompany.trim(),
        sender_value_prop: senderValueProp.trim(),
        email_cta: emailCta.trim(),
        email_tone: emailTone,
        icp_description: icpDescription.trim(),
      };
      if (targetTitles.length > 0) config.target_titles = targetTitles;
      if (targetIndustries.length > 0) config.target_industries = targetIndustries;
      if (excludedDomains.length > 0) config.excluded_domains = excludedDomains;

      // Strategy routing config
      if (strategies.length > 0) {
        const signalStrategies = strategies.filter((s) => s.type === "signal");
        const fallbackStrategies = strategies.filter((s) => s.type === "fallback");

        config.strategy_routing = {
          mode: routingMode,
          strategies: [
            ...signalStrategies.map((s, i) => ({
              id: s.id,
              name: s.name || s.id,
              type: "signal",
              priority: i + 1,
              conditions: s.conditions.filter((c) => c.field),
              campaign_name: s.campaign_name || s.name || s.id,
              email_prompt: s.email_prompt,
            })),
            ...fallbackStrategies.map((s) => ({
              id: s.id,
              name: s.name || s.id,
              type: "fallback",
              campaign_name: s.campaign_name || s.name || s.id,
              email_prompt: s.email_prompt,
            })),
          ],
        };
      }

      // Progressive batch config
      if (progressiveMode) {
        config.progressive_batch = {
          enabled: true,
          batch_sizes: BATCH_SIZES,
        };
      }

      // Create campaign
      const { error: campErr } = await getSupabase().from("campaigns").insert({
        client_id: clientId,
        slug: slug.trim(),
        config,
      });

      if (campErr) throw campErr;
      router.push(`/campaigns/${slug.trim()}`);
    } catch (err: any) {
      setError(err.message || "Failed to create campaign");
      setSaving(false);
    }
  }

  const signalStrategies = strategies.filter((s) => s.type === "signal");
  const fallbackStrategies = strategies.filter((s) => s.type === "fallback");

  return (
    <div className="max-w-3xl mx-auto animate-fade-in">
      <Link href="/" className="text-sm text-gray-500 hover:text-gray-300 mb-4 block">
        &larr; Back
      </Link>

      {/* Step indicator */}
      <div className="flex items-center gap-2 mb-8">
        {STEPS.map((label, i) => (
          <div key={label} className="flex items-center gap-2">
            <button
              onClick={() => i < step && setStep(i)}
              className={cn(
                "flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-all",
                i === step
                  ? "bg-amber-600 text-white shadow-glow-gold-sm"
                  : i < step
                  ? "bg-amber-600/20 text-amber-400 hover:bg-amber-600/30 cursor-pointer"
                  : "bg-gray-800/60 text-gray-500"
              )}
            >
              <span
                className={cn(
                  "w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold",
                  i < step ? "bg-amber-500 text-black" : "bg-gray-700 text-gray-400",
                  i === step && "bg-white text-amber-700"
                )}
              >
                {i < step ? "✓" : i + 1}
              </span>
              {label}
            </button>
            {i < STEPS.length - 1 && <div className="w-8 h-px bg-gray-800" />}
          </div>
        ))}
      </div>

      {/* Step 1: Company Info */}
      {step === 0 && (
        <div className="space-y-6">
          <div>
            <h1 className="text-2xl font-bold text-white">Your Company</h1>
            <p className="text-sm text-gray-500 mt-1">Who is sending these emails?</p>
          </div>

          <Section title="Campaign">
            <Field label="Client Name" required>
              <input
                type="text"
                value={clientName}
                onChange={(e) => handleClientNameChange(e.target.value)}
                placeholder="Acme Corp"
                className="input"
              />
            </Field>
            <Field label="Campaign Slug" required>
              <input
                type="text"
                value={slug}
                onChange={(e) => { setSlug(e.target.value); setSlugManual(true); }}
                placeholder="acme-q1-2026"
                className="input"
              />
              <p className="text-xs text-gray-600 mt-1">URL-friendly identifier</p>
            </Field>
          </Section>

          <Section title="Sender">
            <div className="grid grid-cols-2 gap-4">
              <Field label="Your Name" required>
                <input
                  type="text"
                  value={senderName}
                  onChange={(e) => setSenderName(e.target.value)}
                  placeholder="John Smith"
                  className="input"
                />
              </Field>
              <Field label="Company Name" required>
                <input
                  type="text"
                  value={senderCompany}
                  onChange={(e) => setSenderCompany(e.target.value)}
                  placeholder="GrowthPal"
                  className="input"
                />
              </Field>
            </div>
            <Field label="Value Proposition">
              <textarea
                value={senderValueProp}
                onChange={(e) => setSenderValueProp(e.target.value)}
                placeholder="We help B2B SaaS companies book 30+ qualified meetings per month through AI-powered cold outreach..."
                rows={3}
                className="input"
              />
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Call to Action">
                <input
                  type="text"
                  value={emailCta}
                  onChange={(e) => setEmailCta(e.target.value)}
                  placeholder="Book a 15-minute call"
                  className="input"
                />
              </Field>
              <Field label="Email Tone">
                <select
                  value={emailTone}
                  onChange={(e) => setEmailTone(e.target.value)}
                  className="input"
                >
                  <option value="professional">Professional</option>
                  <option value="casual">Casual</option>
                  <option value="bold">Bold</option>
                </select>
              </Field>
            </div>
          </Section>
        </div>
      )}

      {/* Step 2: Targeting */}
      {step === 1 && (
        <div className="space-y-6">
          <div>
            <h1 className="text-2xl font-bold text-white">Who Are You Targeting?</h1>
            <p className="text-sm text-gray-500 mt-1">Define your ideal customer profile for qualification</p>
          </div>

          <Section title="Ideal Customer Profile">
            <Field label="ICP Description" required>
              <textarea
                value={icpDescription}
                onChange={(e) => setIcpDescription(e.target.value)}
                placeholder="B2B SaaS companies with 50-500 employees in the US. They should have a marketing team and be actively investing in growth. Revenue between $5M-$100M ARR..."
                rows={5}
                className="input"
              />
              <p className="text-xs text-gray-500 mt-1">Be specific. This is used by AI to qualify/disqualify leads.</p>
            </Field>
          </Section>

          <Section title="Filters">
            <Field label="Target Job Titles">
              <TagInput tags={targetTitles} onChange={setTargetTitles} placeholder="VP of Marketing, Head of Growth" />
              <p className="text-xs text-gray-500 mt-1">Press Enter or comma to add</p>
            </Field>
            <Field label="Target Industries">
              <TagInput tags={targetIndustries} onChange={setTargetIndustries} placeholder="SaaS, Fintech" />
            </Field>
            <Field label="Excluded Domains">
              <TagInput tags={excludedDomains} onChange={setExcludedDomains} placeholder="gmail.com" />
            </Field>
          </Section>
        </div>
      )}

      {/* Step 3: Strategies */}
      {step === 2 && (
        <div className="space-y-6">
          <div>
            <h1 className="text-2xl font-bold text-white">Email Strategies</h1>
            <p className="text-sm text-gray-500 mt-1">
              Signal strategies trigger when lead data matches conditions. Fallbacks are for leads without matching signals.
            </p>
          </div>

          {/* Signal Strategies */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <div>
                <h2 className="text-sm font-semibold text-white">Signal Strategies</h2>
                <p className="text-xs text-gray-500">Checked in priority order — first match wins</p>
              </div>
              <button
                type="button"
                onClick={() => addStrategy("signal")}
                className="btn-secondary text-xs"
              >
                + Add Signal Strategy
              </button>
            </div>

            {signalStrategies.length === 0 ? (
              <div className="card p-6 text-center">
                <p className="text-sm text-gray-500">No signal strategies yet.</p>
                <p className="text-xs text-gray-600 mt-1">Add one to route leads based on hiring, funding, or tech signals.</p>
              </div>
            ) : (
              <div className="space-y-4">
                {strategies.map(
                  (strategy, idx) =>
                    strategy.type === "signal" && (
                      <StrategyCard
                        key={strategy.id}
                        strategy={strategy}
                        index={idx}
                        onUpdate={(u) => updateStrategy(idx, u)}
                        onRemove={() => removeStrategy(idx)}
                        onMoveUp={() => moveStrategy(idx, -1)}
                        onMoveDown={() => moveStrategy(idx, 1)}
                        onAddCondition={() => addCondition(idx)}
                        onUpdateCondition={(ci, u) => updateCondition(idx, ci, u)}
                        onRemoveCondition={(ci) => removeCondition(idx, ci)}
                      />
                    )
                )}
              </div>
            )}
          </div>

          {/* Fallback Strategies */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <div>
                <h2 className="text-sm font-semibold text-white">Fallback Strategies</h2>
                <p className="text-xs text-gray-500">
                  For leads that don&apos;t match any signal. Distributed randomly
                  {routingMode === "optimization" ? " (80/20 winner)" : " (equal split)"}.
                </p>
              </div>
              <button
                type="button"
                onClick={() => addStrategy("fallback")}
                className="btn-secondary text-xs"
              >
                + Add Fallback
              </button>
            </div>

            {fallbackStrategies.length === 0 ? (
              <div className="card p-6 text-center">
                <p className="text-sm text-gray-500">No fallback strategies yet.</p>
                <p className="text-xs text-gray-600 mt-1">Add at least one for leads without matching signals.</p>
              </div>
            ) : (
              <div className="space-y-4">
                {strategies.map(
                  (strategy, idx) =>
                    strategy.type === "fallback" && (
                      <StrategyCard
                        key={strategy.id}
                        strategy={strategy}
                        index={idx}
                        onUpdate={(u) => updateStrategy(idx, u)}
                        onRemove={() => removeStrategy(idx)}
                        onAddCondition={() => {}}
                        onUpdateCondition={() => {}}
                        onRemoveCondition={() => {}}
                      />
                    )
                )}
              </div>
            )}
          </div>

          {/* Routing Mode */}
          {fallbackStrategies.length > 1 && (
            <Section title="Fallback Distribution">
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => setRoutingMode("testing")}
                  className={cn(
                    "flex-1 p-3 rounded-lg border text-sm text-left transition-all",
                    routingMode === "testing"
                      ? "border-amber-500/60 bg-amber-500/5"
                      : "border-gray-700/50 bg-gray-800/30 hover:border-gray-600"
                  )}
                >
                  <div className="font-medium text-white mb-0.5">A/B Testing</div>
                  <div className="text-xs text-gray-400">Equal random split between all fallbacks</div>
                </button>
                <button
                  type="button"
                  onClick={() => setRoutingMode("optimization")}
                  className={cn(
                    "flex-1 p-3 rounded-lg border text-sm text-left transition-all",
                    routingMode === "optimization"
                      ? "border-amber-500/60 bg-amber-500/5"
                      : "border-gray-700/50 bg-gray-800/30 hover:border-gray-600"
                  )}
                >
                  <div className="font-medium text-white mb-0.5">Optimization</div>
                  <div className="text-xs text-gray-400">80% to winner, 20% testing others</div>
                </button>
              </div>
            </Section>
          )}

          {/* Progressive Mode */}
          <Section title="Execution Mode">
            <button
              type="button"
              onClick={() => setProgressiveMode(!progressiveMode)}
              className={cn(
                "w-full p-4 rounded-lg border text-left transition-all",
                progressiveMode
                  ? "border-amber-500/60 bg-amber-500/5"
                  : "border-gray-700/50 bg-gray-800/30 hover:border-gray-600"
              )}
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium text-white text-sm">Progressive Batching</div>
                  <div className="text-xs text-gray-400 mt-0.5">
                    Run 10 leads first, review, then 20, 50, 100, then all. Iterate before scaling.
                  </div>
                </div>
                <div
                  className={cn(
                    "w-10 h-6 rounded-full transition-all flex items-center px-0.5",
                    progressiveMode ? "bg-amber-600" : "bg-gray-700"
                  )}
                >
                  <div
                    className={cn(
                      "w-5 h-5 rounded-full bg-white transition-all shadow-sm",
                      progressiveMode ? "translate-x-4" : "translate-x-0"
                    )}
                  />
                </div>
              </div>
              {progressiveMode && (
                <div className="flex items-center gap-2 mt-3 pt-3 border-t border-gray-800/40">
                  {BATCH_SIZES.map((size, i) => (
                    <div key={size} className="flex items-center gap-2">
                      <div className="px-2.5 py-1 rounded-md bg-gray-800/60 text-xs font-mono text-amber-400">
                        {size}
                      </div>
                      {i < BATCH_SIZES.length - 1 && (
                        <svg className="w-3 h-3 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                      )}
                    </div>
                  ))}
                  <svg className="w-3 h-3 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                  <div className="px-2.5 py-1 rounded-md bg-gray-800/60 text-xs font-mono text-green-400">
                    All
                  </div>
                </div>
              )}
            </button>
          </Section>
        </div>
      )}

      {/* Step 4: Review */}
      {step === 3 && (
        <div className="space-y-6">
          <div>
            <h1 className="text-2xl font-bold text-white">Review & Create</h1>
            <p className="text-sm text-gray-500 mt-1">Everything looks good? Let&apos;s launch this campaign.</p>
          </div>

          <Section title="Campaign">
            <ReviewRow label="Client" value={clientName} />
            <ReviewRow label="Slug" value={slug} />
            <ReviewRow label="Sender" value={`${senderName} at ${senderCompany}`} />
            {senderValueProp && <ReviewRow label="Value Prop" value={senderValueProp} />}
            {emailCta && <ReviewRow label="CTA" value={emailCta} />}
            <ReviewRow label="Tone" value={emailTone} />
          </Section>

          <Section title="Targeting">
            <ReviewRow label="ICP" value={icpDescription.slice(0, 150) + (icpDescription.length > 150 ? "..." : "")} />
            {targetTitles.length > 0 && <ReviewRow label="Titles" value={targetTitles.join(", ")} />}
            {targetIndustries.length > 0 && <ReviewRow label="Industries" value={targetIndustries.join(", ")} />}
          </Section>

          {strategies.length > 0 && (
            <Section title={`Strategies (${strategies.length})`}>
              {signalStrategies.map((s) => (
                <div key={s.id} className="flex items-center gap-2 text-sm py-1">
                  <span className="w-2 h-2 rounded-full bg-blue-400" />
                  <span className="text-gray-300">{s.name || s.id}</span>
                  <span className="text-gray-600">— {s.conditions.length} condition{s.conditions.length !== 1 ? "s" : ""}</span>
                  {s.campaign_name && <span className="text-gray-600">— {s.campaign_name}</span>}
                </div>
              ))}
              {fallbackStrategies.map((s) => (
                <div key={s.id} className="flex items-center gap-2 text-sm py-1">
                  <span className="w-2 h-2 rounded-full bg-gray-400" />
                  <span className="text-gray-300">{s.name || s.id}</span>
                  <span className="text-gray-600">— fallback</span>
                  {s.campaign_name && <span className="text-gray-600">— {s.campaign_name}</span>}
                </div>
              ))}
              <div className="text-xs text-gray-500 mt-1">
                Mode: {routingMode === "testing" ? "A/B Testing (equal split)" : "Optimization (80/20)"}
              </div>
            </Section>
          )}

          <Section title="Execution">
            <ReviewRow label="Mode" value={progressiveMode ? "Progressive Batching (10 → 20 → 50 → 100 → All)" : "Process all leads immediately"} />
          </Section>

        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-sm text-red-400 mt-6">
          {error}
        </div>
      )}

      {/* Navigation */}
      <div className="flex justify-between mt-8 pb-12">
        <button
          type="button"
          onClick={() => setStep(Math.max(0, step - 1))}
          className={cn("btn-secondary", step === 0 && "invisible")}
        >
          &larr; Back
        </button>

        {step < STEPS.length - 1 ? (
          <button
            type="button"
            onClick={() => setStep(step + 1)}
            disabled={!canAdvance()}
            className="btn-primary px-8"
          >
            Continue &rarr;
          </button>
        ) : (
          <button
            type="button"
            onClick={handleSubmit}
            disabled={saving}
            className={cn(
              "px-8 py-2.5 rounded-xl font-semibold text-white transition-all duration-200",
              saving
                ? "bg-amber-800 cursor-not-allowed"
                : "bg-gradient-to-r from-amber-600 to-amber-500 hover:shadow-glow-gold active:scale-[0.99]"
            )}
          >
            {saving ? "Creating..." : "Create Campaign"}
          </button>
        )}
      </div>
    </div>
  );
}

// ── Strategy Card ────────────────────────────────────────────────────────────

function StrategyCard({
  strategy,
  index,
  onUpdate,
  onRemove,
  onMoveUp,
  onMoveDown,
  onAddCondition,
  onUpdateCondition,
  onRemoveCondition,
}: {
  strategy: Strategy;
  index: number;
  onUpdate: (u: Partial<Strategy>) => void;
  onRemove: () => void;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
  onAddCondition: () => void;
  onUpdateCondition: (ci: number, u: Partial<Condition>) => void;
  onRemoveCondition: (ci: number) => void;
}) {
  return (
    <div className="card p-4 space-y-3">
      <div className="flex items-center gap-2">
        {strategy.type === "signal" && onMoveUp && onMoveDown && (
          <div className="flex flex-col gap-0.5">
            <button type="button" onClick={onMoveUp} className="text-gray-500 hover:text-white text-xs leading-none">
              ▲
            </button>
            <button type="button" onClick={onMoveDown} className="text-gray-500 hover:text-white text-xs leading-none">
              ▼
            </button>
          </div>
        )}
        <input
          type="text"
          value={strategy.name}
          onChange={(e) => onUpdate({ name: e.target.value })}
          placeholder={strategy.type === "signal" ? "e.g. Hiring Signal" : "e.g. Case Study Angle"}
          className="input flex-1 text-sm font-medium"
        />
        <input
          type="text"
          value={strategy.campaign_name}
          onChange={(e) => onUpdate({ campaign_name: e.target.value })}
          placeholder="Campaign name"
          className="input w-44 text-xs"
        />
        <button
          type="button"
          onClick={onRemove}
          className="text-gray-500 hover:text-red-400 px-2 py-1 text-sm transition-colors"
        >
          Remove
        </button>
      </div>

      {/* Conditions (signal only) */}
      {strategy.type === "signal" && (
        <div className="space-y-2">
          <div className="text-xs text-gray-500 font-medium">Conditions (all must match)</div>
          {strategy.conditions.map((cond, ci) => (
            <div key={ci} className="flex items-center gap-2">
              <select
                value={cond.field}
                onChange={(e) => onUpdateCondition(ci, { field: e.target.value })}
                className="input text-xs flex-1"
              >
                <option value="">Select field...</option>
                {SIGNAL_FIELDS.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
                <option value="__custom">Custom field path...</option>
              </select>
              {cond.field === "__custom" && (
                <input
                  type="text"
                  placeholder="field.path"
                  className="input text-xs w-32"
                  onChange={(e) => onUpdateCondition(ci, { field: e.target.value })}
                />
              )}
              <select
                value={cond.operator}
                onChange={(e) => onUpdateCondition(ci, { operator: e.target.value })}
                className="input text-xs w-32"
              >
                {OPERATORS.map((op) => (
                  <option key={op.value} value={op.value}>
                    {op.label}
                  </option>
                ))}
              </select>
              {OPERATORS.find((op) => op.value === cond.operator)?.needsValue && (
                <input
                  type="text"
                  value={cond.value || ""}
                  onChange={(e) => onUpdateCondition(ci, { value: e.target.value })}
                  placeholder="Value"
                  className="input text-xs flex-1"
                />
              )}
              <button
                type="button"
                onClick={() => onRemoveCondition(ci)}
                className="text-gray-600 hover:text-red-400 text-sm px-1 transition-colors"
              >
                &times;
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={onAddCondition}
            className="text-xs text-amber-500/80 hover:text-amber-400 transition-colors"
          >
            + Add condition
          </button>
        </div>
      )}

      {/* Email Prompt */}
      <div>
        <div className="text-xs text-gray-500 font-medium mb-1">
          Email Prompt
          <span className="text-gray-600 font-normal ml-1">
            Use {"{{field_name}}"} for lead data
          </span>
        </div>
        <textarea
          value={strategy.email_prompt}
          onChange={(e) => onUpdate({ email_prompt: e.target.value })}
          placeholder={
            strategy.type === "signal"
              ? "Write a cold email leading with {{company_name}}'s hiring activity.\nHiring data: {{hiring_signal}}\n..."
              : "Write a cold email leading with a relevant case study for {{industry}} companies..."
          }
          rows={4}
          className="input font-mono text-xs"
        />
      </div>
    </div>
  );
}

// ── Reusable Components ──────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card p-6 space-y-4">
      <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest pb-3 border-b border-gray-800/40">
        {title}
      </h2>
      {children}
    </div>
  );
}

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm text-gray-300 mb-1">
        {label}
        {required && <span className="text-red-400 ml-1">*</span>}
      </label>
      {children}
    </div>
  );
}

function TagInput({
  tags,
  onChange,
  placeholder,
}: {
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder: string;
}) {
  const [input, setInput] = useState("");

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if ((e.key === "Enter" || e.key === ",") && input.trim()) {
      e.preventDefault();
      if (!tags.includes(input.trim())) {
        onChange([...tags, input.trim()]);
      }
      setInput("");
    }
    if (e.key === "Backspace" && !input && tags.length > 0) {
      onChange(tags.slice(0, -1));
    }
  }

  return (
    <div className="flex flex-wrap gap-2 p-2 bg-gray-800/60 border border-gray-700/50 rounded-lg min-h-[42px]">
      {tags.map((tag) => (
        <span
          key={tag}
          className="flex items-center gap-1 bg-gray-700/50 text-gray-200 px-2 py-0.5 rounded-md text-xs ring-1 ring-gray-600/30"
        >
          {tag}
          <button
            type="button"
            onClick={() => onChange(tags.filter((t) => t !== tag))}
            className="text-gray-400 hover:text-white"
          >
            &times;
          </button>
        </span>
      ))}
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={tags.length === 0 ? placeholder : ""}
        className="bg-transparent outline-none text-sm text-gray-200 flex-1 min-w-[120px]"
      />
    </div>
  );
}

function ReviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-3 text-sm py-1">
      <span className="text-gray-500 w-24 shrink-0">{label}</span>
      <span className="text-gray-200">{value}</span>
    </div>
  );
}
