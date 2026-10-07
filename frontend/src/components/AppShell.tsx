"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchMe, logoutAccount } from "@/lib/api";

type NavItem = {
  label: string;
  href: string;
  // Matched against the current path and query, so /ideas?view=archive can be its own item.
  match?: (pathname: string, query: URLSearchParams) => boolean;
  children?: NavItem[];
};

type NavGroup = { label: string; items: NavItem[] };

// One menu for every page. Add a page here and it appears on every screen size.
const NAV: NavGroup[] = [
  {
    label: "Create",
    items: [
      {
        label: "Ideas",
        href: "/ideas",
        children: [
          {
            label: "Board",
            href: "/ideas",
            match: (p, q) => p === "/ideas" && q.get("view") !== "archive",
          },
          {
            label: "Archive",
            href: "/ideas?view=archive",
            match: (p, q) => p === "/ideas" && q.get("view") === "archive",
          },
        ],
      },
    ],
  },
  {
    label: "Plan",
    items: [
      { label: "Strategies", href: "/strategies" },
      { label: "Sources", href: "/sources" },
    ],
  },
  {
    label: "Results",
    items: [{ label: "Analytics", href: "/analytics" }],
  },
  {
    label: "Account",
    items: [
      {
        label: "Settings",
        href: "/settings",
        children: [
          { label: "Account", href: "/settings/account" },
          { label: "Platforms", href: "/settings/platforms" },
          { label: "API keys", href: "/settings/api-keys" },
        ],
      },
    ],
  },
];

function isActive(item: NavItem, pathname: string, query: URLSearchParams): boolean {
  if (item.match) return item.match(pathname, query);
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

function NavRow({
  item,
  pathname,
  query,
  onNavigate,
}: {
  item: NavItem;
  pathname: string;
  query: URLSearchParams;
  onNavigate?: () => void;
}) {
  // Submenus start closed and open only when clicked.
  const [open, setOpen] = useState(false);
  const active = isActive(item, pathname, query);
  const childActive = item.children?.some((c) => isActive(c, pathname, query)) ?? false;

  if (!item.children) {
    return (
      <Link
        href={item.href}
        onClick={onNavigate}
        aria-current={active ? "page" : undefined}
        className={`flex items-center rounded-md px-3 py-2 text-sm font-medium transition-colors ${
          active ? "bg-accent/15 text-accent-text" : "text-muted hover:bg-raised hover:text-body-strong"
        }`}
      >
        {item.label}
      </Link>
    );
  }

  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-sm font-medium transition-colors ${
          childActive ? "text-accent-text" : "text-muted hover:bg-raised hover:text-body-strong"
        }`}
      >
        <span>{item.label}</span>
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
          className={`transition-transform ${open ? "rotate-180" : ""}`}
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open && (
        <ul className="mt-1 space-y-0.5 border-l border-line-strong ml-5 pl-2">
          {item.children.map((child) => {
            const childNow = isActive(child, pathname, query);
            return (
              <li key={child.href}>
                <Link
                  href={child.href}
                  onClick={onNavigate}
                  aria-current={childNow ? "page" : undefined}
                  className={`flex items-center rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                    childNow
                      ? "bg-accent text-strong shadow-sm shadow-accent/20"
                      : "text-subtle hover:bg-raised hover:text-body-strong"
                  }`}
                >
                  {child.label}
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function NavList({
  pathname,
  query,
  onNavigate,
}: {
  pathname: string;
  query: URLSearchParams;
  onNavigate?: () => void;
}) {
  return (
    <nav aria-label="Main" className="space-y-6">
      {NAV.map((group) => (
        <div key={group.label}>
          <p className="cos-label px-3 pb-2">{group.label}</p>
          <div className="space-y-0.5">
            {group.items.map((item) => (
              <NavRow key={item.label} item={item} pathname={pathname} query={query} onNavigate={onNavigate} />
            ))}
          </div>
        </div>
      ))}
    </nav>
  );
}

function AccountFooter() {
  const queryClient = useQueryClient();
  const { data: me } = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const logout = useMutation({
    mutationFn: logoutAccount,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["me"] }),
  });
  if (!me) return null;
  return (
    <div className="border-t border-line pt-4 px-3 flex items-center justify-between gap-3">
      <span className="text-xs text-muted truncate" data-testid="account-email">
        {me.display_name ?? me.email}
      </span>
      <button onClick={() => logout.mutate()} className="text-xs font-semibold text-body hover:text-strong shrink-0">
        Log out
      </button>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "";
  const searchParams = useSearchParams();
  const query = new URLSearchParams(searchParams?.toString() ?? "");
  const [open, setOpen] = useState(false);

  // Close the drawer after navigating and on Escape.
  useEffect(() => setOpen(false), [pathname, searchParams]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className="min-h-screen">
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex fixed inset-y-0 left-0 z-20 w-60 flex-col gap-6 border-r border-line bg-panel px-3 py-6">
        <Link href="/analytics" className="px-3 text-sm font-bold tracking-tight text-strong">
          Content OS
        </Link>
        <div className="flex-1 overflow-y-auto">
          <NavList pathname={pathname} query={query} />
        </div>
        <AccountFooter />
      </aside>

      {/* Phone and tablet top bar */}
      <header className="lg:hidden sticky top-0 z-20 flex items-center justify-between border-b border-line bg-panel/90 px-4 py-3 backdrop-blur">
        <Link href="/analytics" className="text-sm font-bold tracking-tight text-strong">
          Content OS
        </Link>
        <button
          type="button"
          aria-label="Open menu"
          aria-expanded={open}
          aria-controls="mobile-menu"
          onClick={() => setOpen(true)}
          className="cos-btn px-2.5 py-2"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <path d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
      </header>

      {/* Phone and tablet drawer */}
      {open && (
        <div className="lg:hidden fixed inset-0 z-30">
          <button
            type="button"
            aria-label="Close menu"
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-black/60"
          />
          <div
            id="mobile-menu"
            role="dialog"
            aria-modal="true"
            aria-label="Menu"
            className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col gap-6 overflow-y-auto border-r border-line bg-panel px-3 py-6"
          >
            <div className="flex items-center justify-between px-3">
              <span className="text-sm font-bold tracking-tight text-strong">Content OS</span>
              <button type="button" onClick={() => setOpen(false)} className="cos-btn px-2.5 py-1.5">
                Close
              </button>
            </div>
            <div className="flex-1">
              <NavList pathname={pathname} query={query} onNavigate={() => setOpen(false)} />
            </div>
            <AccountFooter />
          </div>
        </div>
      )}

      <div className="lg:pl-60">{children}</div>
    </div>
  );
}
