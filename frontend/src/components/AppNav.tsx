"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// One navigation for every page. Add a page here and it appears everywhere.
const LINKS = [
  { href: "/analytics", label: "Analytics" },
  { href: "/sources", label: "Sources" },
  { href: "/strategies", label: "Strategies" },
  { href: "/ideas", label: "Ideas" },
];

export function AppNav() {
  const pathname = usePathname() ?? "";
  return (
    <nav className="flex items-center gap-6" aria-label="Main">
      {LINKS.map((l) => {
        const active = pathname === l.href || pathname.startsWith(`${l.href}/`);
        return (
          <Link
            key={l.href}
            href={l.href}
            aria-current={active ? "page" : undefined}
            className={`text-sm font-medium transition-colors ${
              active ? "text-accent-text" : "text-muted hover:text-body-strong"
            }`}
          >
            {l.label}
          </Link>
        );
      })}
    </nav>
  );
}
