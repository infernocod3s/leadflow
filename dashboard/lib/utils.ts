export function cn(...classes: (string | boolean | undefined | null)[]) {
  return classes.filter(Boolean).join(" ");
}

export function formatCost(cost: number): string {
  if (cost < 0.01) return `$${cost.toFixed(4)}`;
  return `$${cost.toFixed(2)}`;
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat().format(n);
}

export function formatDate(date: string): string {
  return new Date(date).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function statusColor(status: string): string {
  const colors: Record<string, string> = {
    imported: "bg-gray-500/10 text-gray-400 ring-1 ring-gray-500/20",
    in_progress: "bg-blue-500/10 text-blue-400 ring-1 ring-blue-500/20",
    enriched: "bg-green-500/10 text-green-400 ring-1 ring-green-500/20",
    qualified: "bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/20",
    disqualified: "bg-orange-500/10 text-orange-400 ring-1 ring-orange-500/20",
    email_generated: "bg-purple-500/10 text-purple-400 ring-1 ring-purple-500/20",
    pushed: "bg-indigo-500/10 text-indigo-400 ring-1 ring-indigo-500/20",
    error: "bg-red-500/10 text-red-400 ring-1 ring-red-500/20",
  };
  return colors[status] || "bg-gray-500/10 text-gray-400 ring-1 ring-gray-500/20";
}
