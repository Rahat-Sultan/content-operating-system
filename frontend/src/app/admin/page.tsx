"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchAdminUsers } from "@/lib/api";
import { Greeting } from "@/components/Greeting";
import { ScrollX } from "@/components/ScrollX";

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });
}

export default function AdminPage() {
  const { data, isLoading, isError, error } = useQuery({ queryKey: ["admin-users"], queryFn: fetchAdminUsers });
  const forbidden = isError && /admins only/i.test((error as Error)?.message ?? "");

  return (
    <div className="min-h-screen bg-canvas text-strong">
      <header className="border-b border-line bg-panel/50 backdrop-blur px-4 sm:px-6 py-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center space-x-3">
          <img src="/logo.svg" alt="Content OS" className="h-8 w-8 shrink-0" />
          <div>
            <h1 className="text-lg font-semibold text-strong tracking-tight">Content OS</h1>
            <p className="text-xs text-muted">Autonomous Content Intelligence Engine</p>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <div className="pb-6 border-b border-line">
          <Greeting text={(name) => `Hello ${name}, here are your users.`} />
          <h2 className="text-2xl font-bold text-strong tracking-tight">Users</h2>
          <p className="text-sm text-muted mt-1">Every account on Content OS. Visible only to admins.</p>
        </div>

        {isLoading && <p className="mt-8 text-sm text-subtle">Loading…</p>}

        {forbidden && (
          <div className="mt-8 p-5 rounded-xl bg-panel/60 border border-line space-y-1" data-testid="admin-forbidden">
            <p className="text-sm font-semibold text-body-strong">Admins only</p>
            <p className="text-xs text-muted">Your account doesn't have admin access.</p>
          </div>
        )}
        {isError && !forbidden && (
          <p className="mt-8 text-sm text-bad">{(error as Error).message}</p>
        )}

        {data && (
          <>
            <section className="mt-6 grid grid-cols-2 sm:grid-cols-3 gap-3">
              <div className="cos-card p-4">
                <p className="cos-label">Accounts</p>
                <p className="mt-1 text-2xl font-bold text-strong" data-testid="admin-account-count">{data.accounts}</p>
              </div>
              <div className="cos-card p-4">
                <p className="cos-label">Storage limit / account</p>
                <p className="mt-1 text-2xl font-bold text-strong">{data.storage_limit_mb_per_account} MB</p>
              </div>
            </section>

            <ScrollX className="mt-6 rounded-lg border border-line">
              <table className="w-full min-w-[720px] text-left text-xs">
                <thead className="bg-panel/80 text-[10px] uppercase text-subtle border-b border-line">
                  <tr>
                    <th className="py-2 px-3">Name</th>
                    <th className="py-2 px-3">Email</th>
                    <th className="py-2 px-3">Sign-in</th>
                    <th className="py-2 px-3">Joined</th>
                    <th className="py-2 px-3 text-right">Posts</th>
                    <th className="py-2 px-3 text-right">Ideas</th>
                    <th className="py-2 px-3 text-right">Storage</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line font-mono text-[11px]">
                  {data.users.map((u) => (
                    <tr key={u.id} data-testid={`admin-user-${u.id}`}>
                      <td className="py-2 px-3 whitespace-nowrap">
                        {u.name ?? "—"}
                        {u.is_admin && (
                          <span className="ml-1.5 cos-tag align-middle">admin</span>
                        )}
                      </td>
                      <td className="py-2 px-3 whitespace-nowrap">{u.email}</td>
                      <td className="py-2 px-3 whitespace-nowrap capitalize">{u.sign_in}</td>
                      <td className="py-2 px-3 whitespace-nowrap">{fmtDate(u.created_at)}</td>
                      <td className="py-2 px-3 text-right">{u.posts}</td>
                      <td className="py-2 px-3 text-right">{u.ideas}</td>
                      <td className="py-2 px-3 text-right whitespace-nowrap">
                        {u.storage_mb} / {u.storage_limit_mb} MB
                        <span className="text-subtle"> ({u.storage_percent}%)</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </ScrollX>
          </>
        )}
      </main>
    </div>
  );
}
