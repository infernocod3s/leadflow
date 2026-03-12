"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createSupabaseBrowser } from "@/lib/supabase-server";

export default function NavAuth() {
  const [email, setEmail] = useState<string | null>(null);
  const router = useRouter();
  const supabase = createSupabaseBrowser();

  useEffect(() => {
    supabase.auth.getUser().then(({ data: { user } }) => {
      setEmail(user?.email ?? null);
    });
  }, [supabase]);

  if (!email) return null;

  async function handleSignOut() {
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  }

  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="text-gray-500 hidden sm:inline">{email}</span>
      <button
        onClick={handleSignOut}
        className="text-gray-400 hover:text-white transition-colors"
      >
        Sign out
      </button>
    </div>
  );
}
