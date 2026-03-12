"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getSupabase } from "@/lib/supabase";
import { cn } from "@/lib/utils";

const DEFAULT_EXCLUDED_DOMAINS = ["gmail.com", "yahoo.com", "hotmail.com"];

export default function NewCampaignPage() {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // Form state
  const [clientName, setClientName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugManual, setSlugManual] = useState(false);
  const [icpDescription, setIcpDescription] = useState("");
  const [targetTitles, setTargetTitles] = useState<string[]>([]);
  const [targetIndustries, setTargetIndustries] = useState<string[]>([]);
  const [excludedDomains, setExcludedDomains] = useState<string[]>(DEFAULT_EXCLUDED_DOMAINS);
  const [emailTone, setEmailTone] = useState("professional");
  const [emailCta, setEmailCta] = useState("");
  const [senderName, setSenderName] = useState("");
  const [senderCompany, setSenderCompany] = useState("");
  const [senderValueProp, setSenderValueProp] = useState("");
  const [smartleadId, setSmartleadId] = useState("");

  function generateSlug(name: string) {
    return name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
  }

  function handleClientNameChange(val: string) {
    setClientName(val);
    if (!slugManual) {
      setSlug(generateSlug(val));
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    if (!clientName.trim() || !slug.trim()) {
      setError("Client name and campaign slug are required.");
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

      // Build config JSONB
      const config: Record<string, unknown> = {};
      if (icpDescription.trim()) config.icp_description = icpDescription.trim();
      if (targetTitles.length > 0) config.target_titles = targetTitles;
      if (targetIndustries.length > 0) config.target_industries = targetIndustries;
      if (excludedDomains.length > 0) config.excluded_domains = excludedDomains;
      if (emailTone) config.email_tone = emailTone;
      if (emailCta.trim()) config.email_cta = emailCta.trim();
      if (senderName.trim()) config.sender_name = senderName.trim();
      if (senderCompany.trim()) config.sender_company = senderCompany.trim();
      if (senderValueProp.trim()) config.sender_value_prop = senderValueProp.trim();

      // Create campaign
      const { error: campErr } = await getSupabase()
        .from("campaigns")
        .insert({
          client_id: clientId,
          slug: slug.trim(),
          config,
          smartlead_campaign_id: smartleadId ? parseInt(smartleadId) : null,
        });

      if (campErr) throw campErr;

      router.push(`/campaigns/${slug.trim()}`);
    } catch (err: any) {
      setError(err.message || "Failed to create campaign");
      setSaving(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto">
      <Link href="/" className="text-sm text-gray-500 hover:text-gray-300 mb-4 block">
        &larr; Back
      </Link>
      <h1 className="text-2xl font-bold text-white mb-8">New Campaign</h1>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Basic Info */}
        <Section title="Basic Info">
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

        {/* ICP Definition */}
        <Section title="ICP Definition">
          <Field label="ICP Description">
            <textarea
              value={icpDescription}
              onChange={(e) => setIcpDescription(e.target.value)}
              placeholder="B2B SaaS companies with 50-500 employees..."
              rows={4}
              className="input"
            />
          </Field>
          <Field label="Target Titles">
            <TagInput tags={targetTitles} onChange={setTargetTitles} placeholder="VP of Marketing" />
          </Field>
          <Field label="Target Industries">
            <TagInput tags={targetIndustries} onChange={setTargetIndustries} placeholder="SaaS" />
          </Field>
          <Field label="Excluded Domains">
            <TagInput tags={excludedDomains} onChange={setExcludedDomains} placeholder="gmail.com" />
          </Field>
        </Section>

        {/* Email Settings */}
        <Section title="Email Settings">
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
          <Field label="Email CTA">
            <input
              type="text"
              value={emailCta}
              onChange={(e) => setEmailCta(e.target.value)}
              placeholder="Book a 15-minute call to see how we can help."
              className="input"
            />
          </Field>
          <Field label="Sender Name">
            <input
              type="text"
              value={senderName}
              onChange={(e) => setSenderName(e.target.value)}
              placeholder="John Smith"
              className="input"
            />
          </Field>
          <Field label="Sender Company">
            <input
              type="text"
              value={senderCompany}
              onChange={(e) => setSenderCompany(e.target.value)}
              placeholder="GrowthPal"
              className="input"
            />
          </Field>
          <Field label="Sender Value Prop">
            <textarea
              value={senderValueProp}
              onChange={(e) => setSenderValueProp(e.target.value)}
              placeholder="We help B2B SaaS companies book 30+ qualified meetings..."
              rows={3}
              className="input"
            />
          </Field>
        </Section>

        {/* Integrations */}
        <Section title="Integrations">
          <Field label="Smartlead Campaign ID">
            <input
              type="number"
              value={smartleadId}
              onChange={(e) => setSmartleadId(e.target.value)}
              placeholder="Optional — set after creating in Smartlead"
              className="input"
            />
          </Field>
        </Section>

        {error && (
          <div className="bg-red-900/30 border border-red-800 rounded-lg p-3 text-sm text-red-400">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={saving}
          className={cn(
            "w-full py-3 rounded-xl font-semibold text-white transition-colors",
            saving
              ? "bg-amber-800 cursor-not-allowed"
              : "bg-amber-600 hover:bg-amber-500"
          )}
        >
          {saving ? "Creating..." : "Create Campaign"}
        </button>
      </form>
    </div>
  );
}

// ── Reusable form components ────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4">
      <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider">{title}</h2>
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
    <div className="flex flex-wrap gap-2 p-2 bg-gray-800 border border-gray-700 rounded-lg min-h-[42px]">
      {tags.map((tag) => (
        <span
          key={tag}
          className="flex items-center gap-1 bg-gray-700 text-gray-200 px-2 py-0.5 rounded text-sm"
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
