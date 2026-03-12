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
    imported: "bg-gray-100 text-gray-700",
    in_progress: "bg-blue-100 text-blue-700",
    enriched: "bg-green-100 text-green-700",
    qualified: "bg-emerald-100 text-emerald-700",
    disqualified: "bg-orange-100 text-orange-700",
    email_generated: "bg-purple-100 text-purple-700",
    pushed: "bg-indigo-100 text-indigo-700",
    error: "bg-red-100 text-red-700",
  };
  return colors[status] || "bg-gray-100 text-gray-700";
}
