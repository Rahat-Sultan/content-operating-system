"use client";

import { ScrollX } from "@/components/ScrollX";
import Link from "next/link";
import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchAnalyticsSummary, AnalyticsSummaryPost } from "@/lib/api";
import { PlatformBadge, platformLabel } from "@/components/PlatformBadge";
import { Greeting } from "@/components/Greeting";

const BAR = "#3987e5"; // reference dark categorical slot 1, validated on the app surface
const ALL = "all";

function fmtDate(iso?: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  const zone = new Intl.DateTimeFormat(undefined, { timeZoneName: "short" })
    .formatToParts(d).find((p) => p.type === "timeZoneName")?.value ?? "";
  return `${d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })} ${zone}`.trim();
}

/** One series, so no legend. Bars are labeled with their value; hover shows the post. */
function ImpressionsBars({ posts }: { posts: AnalyticsSummaryPost[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const rows = posts.filter((p) => p.has_snapshot);
  if (rows.length === 0) return null;
  const max = Math.max(1, ...rows.map((p) => p.impressions ?? 0));
  return (
    <div className="relative space-y-2" data-testid="analytics-bars" role="list"
      aria-label={`Impressions for ${rows.length} posts with metrics`}>
      {rows.map((p, i) => {
        const title = p.idea_title ?? p.external_id ?? "";
        const pct = Math.max(2, ((p.impressions ?? 0) / max) * 100);
        return (
          <div
            key={p.publication_id}
            role="listitem"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
            className="grid grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)_3rem] items-center gap-x-3 gap-y-1"
          >
            <span className="truncate text-xs text-muted" title={title}>{title}</span>
            <span className="text-xs font-mono text-body-strong text-right sm:order-last">{p.impressions ?? 0}</span>
            <div className="col-span-2 sm:col-span-1 h-2.5 rounded-full bg-raised overflow-hidden">
              <div
                className="h-full rounded-full transition-opacity"
                style={{ width: `${pct}%`, background: BAR, opacity: hover === null || hover === i ? 1 : 0.55 }}
              />
            </div>
          </div>
        );
      })}
      {hover !== null && rows[hover] && (
        <div className="mt-2 px-2 py-1 rounded bg-canvas border border-line-strong text-[11px] text-body-strong font-mono">
          {platformLabel(rows[hover].platform)} · {rows[hover].impressions ?? 0} impressions · {rows[hover].reactions ?? 0} reactions · {fmtDate(rows[hover].published_at)}
        </div>
      )}
    </div>
  );
}

export default function AnalyticsPage() {
  const [includeTest, setIncludeTest] = useState(false);
  // The selected platform lives in the URL, so a reload (or a shared link) stays on it.
  const router = useRouter();
  const searchParams = useSearchParams();
  const tab = searchParams.get("platform") || ALL;
  function setTab(next: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (next === ALL) params.delete("platform");
    else params.set("platform", next);
    const qs = params.toString();
    router.replace(qs ? `/analytics?${qs}` : "/analytics");
  }
  const platformParam = tab === ALL ? undefined : tab;
  const { data, isLoading, error } = useQuery({
    queryKey: ["analytics-summary", includeTest, platformParam ?? ALL],
    queryFn: () => fetchAnalyticsSummary(includeTest, platformParam),
  });

  const tabInfo = data?.platforms.find((p) => p.key === tab);
  const notConnected = tab !== ALL && tabInfo && !tabInfo.connected;

  return (
    <div className="min-h-screen bg-canvas text-body-strong p-4 sm:p-6 space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <Greeting text={(name) => `Hello ${name}, here is your analytics.`} />
          <h1 className="text-xl font-bold text-strong">Analytics</h1>
          <p className="text-xs text-subtle">Newest valid snapshot per published post, by platform</p>
        </div>
      </header>

      <div role="tablist" aria-label="Platform" className="cos-scroll-x flex gap-2 overflow-x-auto border-b border-line pb-3 sm:flex-wrap [&>button]:shrink-0">
        <button role="tab" aria-selected={tab === ALL} onClick={() => setTab(ALL)}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold border ${tab === ALL ? "bg-accent border-accent text-strong" : "border-line-strong text-body hover:bg-raised"}`}>
          Show all
        </button>
        {(data?.platforms ?? []).map((p) => (
          <button key={p.key} role="tab" aria-selected={tab === p.key} onClick={() => setTab(p.key)}
            data-testid={`tab-${p.key}`}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold border flex items-center gap-2 ${tab === p.key ? "bg-accent border-accent text-strong" : "border-line-strong text-body hover:bg-raised"}`}>
            <PlatformBadge platform={p.key} muted={!p.connected} />
            <span className="text-muted font-mono">{p.post_count}</span>
            {!p.connected && <span className="text-[10px] text-subtle">not connected</span>}
          </button>
        ))}
      </div>

      {isLoading && <p className="text-sm text-subtle">Loading…</p>}
      {error && <p className="text-sm text-rose-400">{(error as Error).message}</p>}

      {notConnected && (
        <section data-testid="platform-not-connected" className="p-5 rounded-xl bg-panel/60 border border-line space-y-2">
          <p className="text-sm font-semibold text-body-strong">{platformLabel(tab)} is not connected</p>
          <p className="text-xs text-muted">
            Content OS only publishes to LinkedIn today (through Buffer). Posts and metrics for {platformLabel(tab)} will appear here after a {platformLabel(tab)} channel is connected. No numbers are shown for it until then.
          </p>
        </section>
      )}

      {data && !notConnected && (
        <>
          <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              [tab === ALL ? "Published posts" : `${platformLabel(tab)} posts`, data.post_count],
              ["Posts with metrics", data.posts_with_metrics],
              ["Impressions (total)", data.total_impressions],
              ["Reactions (total)", data.total_reactions],
            ].map(([label, value]) => (
              <div key={label as string} className="p-3 rounded-lg bg-panel/70 border border-line">
                <span className="text-[10px] uppercase font-semibold text-subtle block mb-1">{label}</span>
                <span className="text-lg font-bold text-strong font-mono">{value as number}</span>
              </div>
            ))}
          </section>

          <label className="flex items-center space-x-2 text-xs text-muted">
            <input type="checkbox" checked={includeTest} onChange={(e) => setIncludeTest(e.target.checked)} />
            <span>Include test and placeholder publications</span>
          </label>

          {data.posts.length === 0 ? (
            <p className="text-sm text-subtle" data-testid="analytics-empty">
              {tab === ALL ? "No published posts yet." : `No ${platformLabel(tab)} posts yet.`}
            </p>
          ) : (
            <>
              {data.posts_with_metrics === 0 ? (
                <p className="text-sm text-amber-300" data-testid="analytics-no-metrics">
                  Buffer has not returned metrics for any of these posts yet. Rows show "—", not zero.
                </p>
              ) : (
                <section className="p-4 rounded-xl bg-panel/50 border border-line space-y-2">
                  <div className="text-[11px] font-semibold text-muted">Impressions per post</div>
                  <ImpressionsBars posts={data.posts} />
                </section>
              )}

              <ScrollX className="rounded-lg border border-line">
                <table className="w-full min-w-[720px] text-left text-xs">
                  <thead className="bg-panel/80 text-[10px] uppercase text-subtle border-b border-line">
                    <tr>
                      <th className="py-2 px-3">Published</th>
                      {tab === ALL && <th className="py-2 px-3">Platform</th>}
                      <th className="py-2 px-3 min-w-[240px]">Post</th>
                      <th className="py-2 px-3 text-right">Impressions</th>
                      <th className="py-2 px-3 text-right">Reactions</th>
                      <th className="py-2 px-3 text-right">Comments</th>
                      <th className="py-2 px-3 text-right">Snapshots</th>
                      <th className="py-2 px-3">Last collected</th>
                      <th className="py-2 px-3">Run</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                    {data.posts.map((p) => (
                      <tr key={p.publication_id} className={p.is_test_post ? "text-subtle" : ""}>
                        <td className="py-2 px-3 whitespace-nowrap">{fmtDate(p.published_at)}</td>
                        {tab === ALL && <td className="py-2 px-3"><PlatformBadge platform={p.platform} /></td>}
                        <td className="py-2 px-3 min-w-[240px]">{p.is_test_post ? "test · " : ""}{p.idea_title ?? (p.external_id ?? "—").slice(0, 14)}</td>
                        <td className="py-2 px-3 text-right">{p.has_snapshot ? p.impressions ?? 0 : "—"}</td>
                        <td className="py-2 px-3 text-right">{p.has_snapshot ? p.reactions ?? 0 : "—"}</td>
                        <td className="py-2 px-3 text-right">{p.has_snapshot ? p.comments ?? 0 : "—"}</td>
                        <td className="py-2 px-3 text-right">{p.snapshot_count}</td>
                        <td className="py-2 px-3 whitespace-nowrap">{fmtDate(p.collected_at)}</td>
                        <td className="py-2 px-3">
                          {p.workflow_run_id ? (
                            <Link href={`/workflow-runs/${p.workflow_run_id}`} className="text-accent-text hover:underline">open</Link>
                          ) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </ScrollX>
            </>
          )}
        </>
      )}
    </div>
  );
}
