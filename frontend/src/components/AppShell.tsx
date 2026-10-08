"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
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
function buildNav(isAdmin: boolean): NavGroup[] {
  const groups: NavGroup[] = [
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
  if (isAdmin) {
    groups.push({ label: "Admin", items: [{ label: "Users", href: "/admin" }] });
  }
  return groups;
}

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
  isAdmin,
  onNavigate,
}: {
  pathname: string;
  query: URLSearchParams;
  isAdmin: boolean;
  onNavigate?: () => void;
}) {
  const nav = buildNav(isAdmin);
  return (
    <nav aria-label="Main" className="space-y-6">
      {nav.map((group) => (
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

function initialsOf(me: { display_name: string | null; email: string }): string {
  const source = (me.display_name || me.email.split("@")[0]).trim();
  const parts = source.split(/\s+/).filter(Boolean);
  const chars = parts.length >= 2 ? [parts[0][0], parts[1][0]] : [source.slice(0, 2)];
  return chars.join("").toUpperCase().slice(0, 2);
}

function SettingsIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
    </svg>
  );
}

function AdminIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />
    </svg>
  );
}

// A door panel with an arrow walking out through it.
function LogoutDoorIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  );
}

function ChevronRightIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M9 18l6-6-6-6" />
    </svg>
  );
}

function AccountFooter() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: me } = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const logout = useMutation({
    mutationFn: logoutAccount,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["me"] }),
  });

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!me) return null;

  function go(href: string) {
    setOpen(false);
    router.push(href);
  }

  return (
    <div ref={ref} className="relative border-t border-line pt-3 px-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex w-full items-center gap-2.5 rounded-lg px-1.5 py-1.5 text-left hover:bg-raised"
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-bold text-white">
          {initialsOf(me)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-body-strong" data-testid="account-email">
            {me.display_name ?? me.email}
          </span>
          <span className="block truncate text-[11px] text-subtle">{me.is_admin ? "Admin" : "Member"}</span>
        </span>
        <ChevronRightIcon />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute bottom-full left-0 right-0 mb-2 rounded-xl border border-line bg-panel shadow-xl shadow-black/40 py-1.5 overflow-hidden"
        >
          <button
            type="button"
            onClick={() => go("/settings/account")}
            className="flex w-full items-center gap-2.5 px-3 py-2 text-left hover:bg-raised"
            role="menuitem"
          >
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-bold text-white">
              {initialsOf(me)}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-body-strong">{me.display_name ?? me.email}</span>
              <span className="block truncate text-[11px] text-subtle">{me.is_admin ? "Admin" : "Member"}</span>
            </span>
            <ChevronRightIcon />
          </button>

          <div className="my-1.5 border-t border-line" />

          <button type="button" onClick={() => go("/settings/account")} role="menuitem"
            className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-body hover:bg-raised">
            <SettingsIcon />
            Settings
          </button>
          {me.is_admin && (
            <button type="button" onClick={() => go("/admin")} role="menuitem"
              className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-body hover:bg-raised">
              <AdminIcon />
              Admin
            </button>
          )}

          <div className="my-1.5 border-t border-line" />

          <button
            type="button"
            onClick={() => {
              setOpen(false);
              logout.mutate();
            }}
            role="menuitem"
            className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-body hover:bg-raised"
          >
            <LogoutDoorIcon />
            Log out
          </button>
        </div>
      )}
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "";
  const searchParams = useSearchParams();
  const query = new URLSearchParams(searchParams?.toString() ?? "");
  const [open, setOpen] = useState(false);
  const { data: me } = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const isAdmin = me?.is_admin ?? false;

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
          <NavList pathname={pathname} query={query} isAdmin={isAdmin} />
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
              <NavList pathname={pathname} query={query} isAdmin={isAdmin} onNavigate={() => setOpen(false)} />
            </div>
            <AccountFooter />
          </div>
        </div>
      )}

      <div className="lg:pl-60">{children}</div>
    </div>
  );
}
