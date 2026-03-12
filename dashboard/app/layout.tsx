import type { Metadata } from "next";
import Link from "next/link";
import NavAuth from "@/components/nav-auth";
import "./globals.css";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "GrowthPal",
  description: "Lead enrichment pipeline dashboard",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <nav className="border-b border-gray-800/60 bg-gray-950/80 backdrop-blur-xl sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-2">
              <div className="w-8 h-8 bg-gradient-to-br from-amber-400 to-amber-600 rounded-lg flex items-center justify-center text-white font-bold text-sm shadow-glow-gold-sm">
                GP
              </div>
              <span className="text-lg font-semibold text-white">GrowthPal</span>
            </Link>
            <div className="flex items-center gap-6 text-sm text-gray-400">
              <Link href="/" className="relative hover:text-white transition-colors after:absolute after:bottom-[-4px] after:left-0 after:w-0 after:h-[2px] after:bg-amber-500 after:transition-all after:duration-200 hover:after:w-full">
                Campaigns
              </Link>
              <Link href="/costs" className="relative hover:text-white transition-colors after:absolute after:bottom-[-4px] after:left-0 after:w-0 after:h-[2px] after:bg-amber-500 after:transition-all after:duration-200 hover:after:w-full">
                Costs
              </Link>
              <Link href="/settings" className="relative hover:text-white transition-colors after:absolute after:bottom-[-4px] after:left-0 after:w-0 after:h-[2px] after:bg-amber-500 after:transition-all after:duration-200 hover:after:w-full">
                Settings
              </Link>
              <Link
                href="/campaigns/new"
                className="bg-amber-600 hover:bg-amber-500 text-white px-3 py-1.5 rounded-lg transition-all duration-200 hover:shadow-glow-gold-sm active:scale-[0.97]"
              >
                + New
              </Link>
              <div className="border-l border-gray-800 pl-4">
                <NavAuth />
              </div>
            </div>
          </div>
        </nav>
        <main className="max-w-7xl mx-auto px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
