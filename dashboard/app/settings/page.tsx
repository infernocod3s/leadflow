"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getSupabase } from "@/lib/supabase";

type Setting = {
  key: string;
  value: string;
  updated_at: string;
};

const SETTINGS_SCHEMA = [
  {
    key: "smartlead_api_key",
    label: "Smartlead API Key",
    type: "password" as const,
    placeholder: "Enter your Smartlead API key",
  },
];

export default function SettingsPage() {
  const [values, setValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    loadSettings();
  }, []);

  async function loadSettings() {
    const { data } = await getSupabase().from("settings").select("*");
    const map: Record<string, string> = {};
    for (const s of data || []) {
      map[s.key] = s.value;
    }
    setValues(map);
    setLoading(false);
  }

  async function saveSetting(key: string) {
    setSaving(key);
    const value = values[key] || "";

    const { error } = await getSupabase()
      .from("settings")
      .upsert({ key, value, updated_at: new Date().toISOString() }, { onConflict: "key" });

    if (!error) {
      setSaved(key);
      setTimeout(() => setSaved(null), 2000);
    }
    setSaving(null);
  }

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto animate-fade-in">
        <div className="skeleton h-8 w-32 mb-8" />
        <div className="card p-6">
          <div className="skeleton h-4 w-36 mb-3" />
          <div className="flex gap-3">
            <div className="skeleton h-10 flex-1" />
            <div className="skeleton h-10 w-20 rounded-lg" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto animate-fade-in">
      <h1 className="text-2xl font-bold text-white mb-8">Settings</h1>

      <div className="space-y-6">
        {SETTINGS_SCHEMA.map((setting) => (
          <div key={setting.key} className="card p-6">
            <label className="block text-sm text-gray-300 mb-2">{setting.label}</label>
            <div className="flex gap-3">
              <input
                type={setting.type}
                value={values[setting.key] || ""}
                onChange={(e) =>
                  setValues((prev) => ({ ...prev, [setting.key]: e.target.value }))
                }
                placeholder={setting.placeholder}
                className="input flex-1"
              />
              <button
                onClick={() => saveSetting(setting.key)}
                disabled={saving === setting.key}
                className={
                  saved === setting.key
                    ? "btn bg-green-500/10 text-green-400 ring-1 ring-green-500/20"
                    : "btn-primary whitespace-nowrap"
                }
              >
                {saving === setting.key
                  ? "Saving..."
                  : saved === setting.key
                  ? "Saved!"
                  : "Save"}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
