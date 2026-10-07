"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const TABS = [
  { href: "/settings/account", label: "Account" },
  { href: "/settings/platforms", label: "Platforms" },
  { href: "/settings/api-keys", label: "API keys" },
];

export default function SettingsLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "";
  return (
    <div className="min-h-screen bg-canvas text-body-strong">
      <header className="cos-header">
        <div className="flex items-center gap-3">
          <img src="/logo.svg" alt="Content OS" className="h-8 w-8 shrink-0" />
          <div>
            <h1 className="text-lg font-semibold text-strong tracking-tight">Content OS</h1>
            <p className="text-xs text-muted">Autonomous Content Intelligence Engine</p>
          </div>
        </div>
      </header>
      <main className="max-w-4xl mx-auto px-4 sm:px-6 py-6 sm:py-8 space-y-6">
        <div>
          <h2 className="text-2xl font-bold text-strong tracking-tight">Settings</h2>
          <p className="text-sm text-muted mt-1">Your own account, API keys and platforms. Only you can see them.</p>
        </div>

        <nav role="tablist" aria-label="Settings" className="cos-scroll-x flex gap-1 overflow-x-auto rounded-lg border border-line p-1 [&>a]:shrink-0">
          {TABS.map((t) => {
            const active = pathname === t.href;
            return (
              <Link
                key={t.href}
                href={t.href}
                role="tab"
                aria-selected={active}
                className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                  active ? "bg-accent text-white" : "text-muted hover:text-body-strong"
                }`}
              >
                {t.label}
              </Link>
            );
          })}
        </nav>

        {children}
      </main>
    </div>
  );
}
