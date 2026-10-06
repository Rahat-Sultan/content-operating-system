"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchAnalyticsSummary, AnalyticsSummaryPost } from "@/lib/api";
import { PlatformBadge, platformLabel } from "@/components/PlatformBadge";

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
  const ROW = 28, LABEL_W = 170, VAL_W = 56, W = 720;
  const H = rows.length * ROW + 8;
  return (
    <div className="relative" data-testid="analytics-bars">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img"
        aria-label={`Impressions for ${rows.length} posts with metrics`}>
        {rows.map((p, i) => {
          const y = i * ROW + 4;
          const w = ((p.impressions ?? 0) / max) * (W - LABEL_W - VAL_W);
          return (
            <g key={p.publication_id} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <text x={LABEL_W - 8} y={y + 16} textAnchor="end" className="fill-slate-400" fontSize="11">
                {(p.external_id ?? "").slice(0, 12)}…
              </text>
              <rect x={LABEL_W} y={y + 4} width={Math.max(2, w)} height={14} rx={3} fill={BAR}
                opacity={hover === null || hover === i ? 1 : 0.55} />
              <rect x={LABEL_W} y={y} width={W - LABEL_W} height={ROW} fill="transparent" />
              <text x={LABEL_W + w + 6} y={y + 16} className="fill-slate-200" fontSize="11">{p.impressions ?? 0}</text>
            </g>
          );
        })}
      </svg>
      {hover !== null && rows[hover] && (
        <div className="absolute top-0 right-0 px-2 py-1 rounded bg-canvas border border-line-strong text-[11px] text-body-strong font-mono pointer-events-none">
          {platformLabel(rows[hover].platform)} · {rows[hover].impressions ?? 0} impressions · {rows[hover].reactions ?? 0} reactions · {fmtDate(rows[hover].published_at)}
        </div>
      )}
    </div>
  );
}

export default function AnalyticsPage() {
  const [includeTest, setIncludeTest] = useState(false);
  const [tab, setTab] = useState<string>(ALL);
  const platformParam = tab === ALL ? undefined : tab;
  const { data, isLoading, error } = useQuery({
    queryKey: ["analytics-summary", includeTest, platformParam ?? ALL],
    queryFn: () => fetchAnalyticsSummary(includeTest, platformParam),
  });

  const tabInfo = data?.platforms.find((p) => p.key === tab);
  const notConnected = tab !== ALL && tabInfo && !tabInfo.connected;

  return (
    <div className="min-h-screen bg-canvas text-body-strong p-6 space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-strong">Analytics</h1>
          <p className="text-xs text-subtle">Newest valid snapshot per published post, by platform</p>
        </div>
        <nav className="flex items-center space-x-6">
          <Link href="/ideas" className="text-sm font-medium text-muted hover:text-body-strong">Ideas</Link>
          <Link href="/strategies" className="text-sm font-medium text-muted hover:text-body-strong">Strategies</Link>
        </nav>
      </header>

      <div role="tablist" aria-label="Platform" className="flex flex-wrap gap-2 border-b border-line pb-3">
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

              <div className="overflow-x-auto rounded-lg border border-line">
                <table className="w-full text-left text-xs">
                  <thead className="bg-panel/80 text-[10px] uppercase text-subtle border-b border-line">
                    <tr>
                      <th className="py-2 px-3">Published</th>
                      {tab === ALL && <th className="py-2 px-3">Platform</th>}
                      <th className="py-2 px-3">Post</th>
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
                        <td className="py-2 px-3">{p.is_test_post ? "test · " : ""}{(p.external_id ?? "—").slice(0, 14)}</td>
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
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
