"use client";

import { use, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import {
  fetchWorkflowRun,
  fetchIdea,
  fetchWorkflowRunResearch,
  fetchWorkflowRunBrief,
  fetchWorkflowRunDraft,
  submitApprovalDecision,
  fetchWorkflowRunPublication,
  fetchPublicationAnalytics,
  syncPublicationAnalytics,
  submitManualMetrics,
  fetchVersionMedia,
  generateVersionMedia,
} from "@/lib/api";

const STATUS_BADGE_STYLES: Record<string, string> = {
  PENDING: "bg-slate-800 text-slate-300 border-slate-700",
  RUNNING: "bg-blue-900/60 text-blue-300 border-blue-700/50 animate-pulse",
  PAUSED: "bg-amber-900/60 text-amber-300 border-amber-700/50",
  NEEDS_REVIEW: "bg-amber-500/20 text-amber-300 border-amber-500/50 animate-pulse",
  PUBLISHING: "bg-indigo-900/60 text-indigo-300 border-indigo-700/50 animate-pulse",
  COMPLETED: "bg-emerald-900/60 text-emerald-300 border-emerald-700/50",
  FAILED: "bg-rose-900/60 text-rose-300 border-rose-700/50",
  REJECTED: "bg-rose-950 text-rose-400 border-rose-800",
  CANCELLED: "bg-slate-800 text-slate-400 border-slate-700",
};

/** Local date, time and zone label, e.g. "Oct 6, 2026, 10:04 AM PKT". */
function fmtDateTime(iso?: string | null, fallback = "—") {
  if (!iso) return fallback;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return fallback;
  const zone = new Intl.DateTimeFormat(undefined, { timeZoneName: "short" })
    .formatToParts(d)
    .find((p) => p.type === "timeZoneName")?.value ?? "";
  return `${d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })} ${zone}`.trim();
}

const OUTCOME_LABELS: Record<string, string> = {
  ready: "metrics returned",
  not_ready: "Buffer had no metrics yet",
  network_error: "network error, Buffer not reached",
  failed: "failed",
};

export default function WorkflowRunDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const [feedback, setFeedback] = useState("");
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);

  // Manual metrics modal / form state
  const [showManualMetricsForm, setShowManualMetricsForm] = useState(false);
  const [showInvalidRows, setShowInvalidRows] = useState(false);
  const [manualImpressions, setManualImpressions] = useState(0);
  const [manualReactions, setManualReactions] = useState(0);
  const [manualComments, setManualComments] = useState(0);
  const [manualClicks, setManualClicks] = useState(0);
  const [manualShares, setManualShares] = useState(0);
  const [manualError, setManualError] = useState<string | null>(null);

  // 1. Workflow Run State
  const {
    data: run,
    isLoading: isRunLoading,
    isError: isRunError,
    error: runError,
    refetch,
  } = useQuery({
    queryKey: ["workflow-run", id],
    queryFn: () => fetchWorkflowRun(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      // Active non-terminal states that should poll:
      if (status === "RUNNING" || status === "PENDING" || status === "PUBLISHING") {
        return 2000;
      }
      return false;
    },
  });

  // 2. Idea Information
  const { data: idea } = useQuery({
    queryKey: ["idea", run?.idea_id],
    queryFn: () => fetchIdea(run!.idea_id),
    enabled: !!run?.idea_id,
  });

  // 3. Research Information
  const { data: research, refetch: refetchResearch } = useQuery({
    queryKey: ["workflow-run-research", id],
    queryFn: () => fetchWorkflowRunResearch(id),
    enabled: !!run && (run.status === "NEEDS_REVIEW" || run.status === "COMPLETED" || run.status === "PUBLISHING" || run.status === "REJECTED"),
    retry: false,
  });

  // 4. Brief Information
  const { data: brief, refetch: refetchBrief } = useQuery({
    queryKey: ["workflow-run-brief", id],
    queryFn: () => fetchWorkflowRunBrief(id),
    enabled: !!run && (run.status === "NEEDS_REVIEW" || run.status === "COMPLETED" || run.status === "PUBLISHING" || run.status === "REJECTED"),
    retry: false,
  });

  // 5. Draft & Content Information
  const { data: draft, refetch: refetchDraft } = useQuery({
    queryKey: ["workflow-run-draft", id],
    queryFn: () => fetchWorkflowRunDraft(id),
    enabled: !!run && (run.status === "NEEDS_REVIEW" || run.status === "COMPLETED" || run.status === "PUBLISHING" || run.status === "REJECTED"),
    refetchInterval: (query) => {
      // While run is active/running, poll for new draft versions
      if (run?.status === "RUNNING" || run?.status === "PENDING") {
        return 2000;
      }
      return false;
    },
    retry: false,
  });

  // 6. Publication Information
  const { data: publication, refetch: refetchPublication } = useQuery({
    queryKey: ["workflow-run-publication", id],
    queryFn: () => fetchWorkflowRunPublication(id),
    enabled: !!run && (run.status === "COMPLETED" || run.status === "PUBLISHING" || run.status === "FAILED"),
    refetchInterval: (query) => {
      if (run?.status === "PUBLISHING") {
        return 2000;
      }
      return false;
    },
    retry: false,
  });

  // 7. Publication Analytics & Metrics Snapshots
  const {
    data: analyticsSnapshots,
    isLoading: isAnalyticsLoading,
    refetch: refetchAnalytics,
  } = useQuery({
    queryKey: ["publication-analytics", publication?.id],
    queryFn: () => fetchPublicationAnalytics(publication!.id),
    enabled: !!publication?.id && publication?.status === "PUBLISHED",
  });

  // Sync Metrics Mutation
  const [syncError, setSyncError] = useState<string | null>(null);
  const syncMetricsMutation = useMutation({
    mutationFn: () => {
      if (!publication?.id) throw new Error("No publication found to sync metrics for.");
      return syncPublicationAnalytics(publication.id);
    },
    onSuccess: () => {
      setSyncError(null);
      refetchAnalytics();
      refetchPublication();
    },
    onError: (err: any) => {
      setSyncError(err?.message || "Failed to sync metrics from provider.");
      refetchPublication();
    },
  });

  // Manual Metrics Mutation (CP-1.5)
  const manualMetricsMutation = useMutation({
    mutationFn: () => {
      if (!publication?.id) throw new Error("No publication found to record manual metrics for.");
      return submitManualMetrics(publication.id, {
        impressions: Number(manualImpressions) || 0,
        reactions: Number(manualReactions) || 0,
        comments: Number(manualComments) || 0,
        clicks: Number(manualClicks) || 0,
        shares: Number(manualShares) || 0,
      });
    },
    onSuccess: () => {
      setManualError(null);
      setShowManualMetricsForm(false);
      refetchAnalytics();
      // analytics_status lives on the publication response, so refetch it too.
      refetchPublication();
    },
    onError: (err: any) => {
      setManualError(err?.message || "Failed to submit manual metrics.");
    },
  });


  // 8. Version Media Assets
  const currentVersionId = draft?.current_version?.id;
  const contentId = draft?.content_id;

  const {
    data: mediaAssets,
    isLoading: isMediaLoading,
    refetch: refetchMedia,
  } = useQuery({
    queryKey: ["version-media", contentId, currentVersionId],
    queryFn: () => fetchVersionMedia(contentId!, currentVersionId!),
    enabled: !!contentId && !!currentVersionId,
  });

  // Generate Media Mutation
  const [mediaError, setMediaError] = useState<string | null>(null);
  const generateMediaMutation = useMutation({
    mutationFn: async ({ regenerate = false }: { regenerate?: boolean } = {}) => {
      if (!contentId || !currentVersionId) {
        throw new Error("No draft content version loaded to generate media for.");
      }
      return generateVersionMedia(contentId, currentVersionId, undefined, regenerate);
    },
    onSuccess: () => {
      setMediaError(null);
      refetchMedia();
      queryClient.invalidateQueries({ queryKey: ["version-media", contentId, currentVersionId] });
    },
    onError: (err: any) => {
      setMediaError(err?.message || "Failed to generate image.");
    },
  });

  // Approval Mutation
  const approvalMutation = useMutation({
    mutationFn: async ({
      decision,
    }: {
      decision: "APPROVED" | "REJECTED" | "REVISION_REQUESTED";
    }) => {
      // Fetch latest draft to guarantee matching current_version_id
      const latestDraft = await fetchWorkflowRunDraft(id);
      if (!latestDraft?.current_version?.id) {
        throw new Error("No draft version loaded for approval.");
      }
      return submitApprovalDecision(
        id,
        latestDraft.current_version.id,
        decision,
        feedback
      );
    },
    onSuccess: () => {
      setDecisionError(null);
      setFeedback("");
      queryClient.invalidateQueries({ queryKey: ["workflow-run", id] });
      queryClient.invalidateQueries({ queryKey: ["workflow-run-draft", id] });
      queryClient.invalidateQueries({ queryKey: ["workflow-run-publication", id] });
      refetch();
      refetchDraft();
    },
    onError: (err: any) => {
      setDecisionError(err.message || "Failed to process decision");
      refetchDraft();
    },
  });

  if (isRunLoading) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center">
        <div className="flex flex-col items-center space-y-3">
          <div className="h-7 w-7 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
          <p className="text-sm text-slate-400">Loading workflow run {id}...</p>
        </div>
      </div>
    );
  }

  if (isRunError || !run) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 p-8 max-w-4xl mx-auto">
        <div className="p-4 rounded-lg bg-rose-950/40 border border-rose-800 text-rose-300">
          <h2 className="font-semibold text-sm">Failed to load workflow run</h2>
          <p className="text-xs mt-1 text-rose-400">
            {(runError as Error)?.message || "Run not found"}
          </p>
          <Link
            href="/ideas"
            className="inline-block mt-4 text-xs font-semibold text-indigo-400 hover:underline"
          >
            ← Back to Ideas
          </Link>
        </div>
      </div>
    );
  }

  const badgeStyle =
    STATUS_BADGE_STYLES[run.status] || "bg-slate-800 text-slate-300 border-slate-700";

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 pb-20">
      <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur px-6 py-4 flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center space-x-3">
          <Link
            href={`/ideas/${run.idea_id}`}
            className="text-xs font-medium text-slate-400 hover:text-slate-200 transition"
          >
            ← Back to Idea
          </Link>
        </div>
        <div className="flex items-center space-x-3">
          {lastRefreshedAt && (
            <span
              data-testid="refresh-updated-at"
              className="text-[11px] font-mono text-emerald-400 bg-emerald-950/40 border border-emerald-800/60 px-2 py-0.5 rounded"
            >
              Updated {lastRefreshedAt}
            </span>
          )}
          {refreshError && (
            <span className="text-[11px] text-rose-400">
              {refreshError}
            </span>
          )}
          <button
            onClick={async () => {
              try {
                setIsRefreshing(true);
                setRefreshError(null);
                await Promise.all([
                  refetch(),
                  refetchDraft(),
                  refetchResearch(),
                  refetchBrief(),
                  refetchPublication(),
                  refetchAnalytics(),
                  refetchMedia(),
                  queryClient.invalidateQueries({ queryKey: ["workflow-run", id] }),
                  queryClient.invalidateQueries({ queryKey: ["workflow-run-draft", id] }),
                  queryClient.invalidateQueries({ queryKey: ["workflow-run-research", id] }),
                  queryClient.invalidateQueries({ queryKey: ["workflow-run-brief", id] }),
                  queryClient.invalidateQueries({ queryKey: ["workflow-run-publication", id] }),
                  queryClient.invalidateQueries({ queryKey: ["publication-analytics"] }),
                  queryClient.invalidateQueries({ queryKey: ["version-media"] }),
                ]);
                const now = new Date();
                const timeStr = now.toTimeString().split(" ")[0]; // HH:MM:SS
                setLastRefreshedAt(timeStr);
              } catch (err: any) {
                setRefreshError("Refresh failed: " + (err?.message || "network error"));
              } finally {
                setIsRefreshing(false);
              }
            }}
            disabled={isRefreshing}
            data-testid="header-refresh-btn"
            className="text-xs px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-300 border border-slate-700 flex items-center space-x-1.5 transition active:scale-95"
          >
            {isRefreshing ? (
              <>
                <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                <span>Refreshing…</span>
              </>
            ) : (
              <>
                <span>↻</span>
                <span>Refresh</span>
              </>
            )}
          </button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        {/* Header Block */}
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 pb-6 border-b border-slate-800">
          <div className="space-y-1">
            <span className="text-xs font-mono text-slate-400">Run ID: {run.id}</span>
            <h1 className="text-2xl font-bold text-white tracking-tight">
              {idea ? idea.title : "Production Workflow Execution"}
            </h1>
            {idea && (
              <p className="text-xs text-slate-400 mt-1">
                Strategy ID: <span className="font-mono text-slate-300">{idea.strategy_id}</span>
              </p>
            )}
          </div>
          <div>
            <span
              className={`px-3 py-1 rounded-md text-xs font-semibold border ${badgeStyle}`}
            >
              {run.status}
            </span>
          </div>
        </div>

        {/* Phase / Execution Info */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
            <span className="text-xs uppercase font-medium text-slate-500">Current Phase</span>
            <p className="text-base font-semibold text-slate-200 font-mono">
              {run.current_phase || (run.status === "NEEDS_REVIEW" ? "APPROVAL_REVIEW" : run.status)}
            </p>
          </div>
          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
            <span className="text-xs uppercase font-medium text-slate-500">Started At</span>
            <p className="text-sm font-semibold text-slate-200">
              {new Date(run.started_at).toLocaleString()}
            </p>
          </div>
        </div>

        {run.resolved_at && (
          <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800">
            <span className="text-xs uppercase font-medium text-slate-500">Resolved At</span>
            <p className="text-sm font-semibold text-emerald-400 mt-1">
              {new Date(run.resolved_at).toLocaleString()}
            </p>
          </div>
        )}

        {run.error && (
          <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800 text-rose-300 space-y-1">
            <span className="text-xs font-bold uppercase tracking-wider text-rose-400">Error Details</span>
            <p className="text-xs font-mono">{run.error}</p>
          </div>
        )}

        {/* Queued but nothing will start it until the scheduler worker runs */}
        {run.status === "PENDING" && run.worker_running === false && (
          <section data-testid="run-queued-no-worker" className="p-4 rounded-xl bg-amber-950/30 border border-amber-700/60 text-amber-200 text-xs space-y-1">
            <p className="font-semibold">Queued. The workflow has not started yet.</p>
            <p>
              Nothing is running it: the scheduler worker is not running. Start it in your own terminal with{" "}
              <code className="font-mono">python -m app.scheduler</code>.
            </p>
          </section>
        )}

        {/* NEEDS_REVIEW Notice & Human Editorial Actions */}
        {run.status === "NEEDS_REVIEW" && (
          <section className="p-6 rounded-xl bg-amber-950/20 border border-amber-600/50 space-y-4 shadow-lg">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <div className="flex items-center space-x-2">
                  <span className="h-2.5 w-2.5 rounded-full bg-amber-400 animate-ping" />
                  <h3 className="text-sm font-bold text-amber-300 tracking-wide uppercase">
                    Editorial Review Checkpoint
                  </h3>
                </div>
                <p className="text-xs text-amber-200/80">
                  The automated pipeline has reached the approval boundary. Please review the research, brief, and draft below before making a decision.
                </p>
              </div>
            </div>

            {decisionError && (
              <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-700 text-rose-200 text-xs">
                ⚠️ {decisionError}
              </div>
            )}

            <div className="space-y-2">
              <label className="block text-xs font-medium text-slate-300">
                Editorial Feedback / Revision Instructions (optional for Approve, recommended for Revision):
              </label>
              <textarea
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                placeholder="Enter specific feedback or revision requirements for the Writer agent..."
                rows={2}
                className="w-full text-xs rounded-lg bg-slate-900 border border-slate-700 p-2.5 text-slate-200 focus:outline-none focus:border-amber-500 transition"
              />
            </div>

            <div className="flex flex-wrap items-center gap-3 pt-2">
              <button
                onClick={() => approvalMutation.mutate({ decision: "APPROVED" })}
                disabled={approvalMutation.isPending || !draft}
                className="px-4 py-2 rounded-lg text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white shadow transition flex items-center space-x-1.5 disabled:opacity-50"
              >
                <span>✓</span>
                <span>Approve Draft</span>
              </button>

              <button
                onClick={() => approvalMutation.mutate({ decision: "REVISION_REQUESTED" })}
                disabled={approvalMutation.isPending || !draft}
                className="px-4 py-2 rounded-lg text-xs font-bold bg-amber-600 hover:bg-amber-500 text-white shadow transition flex items-center space-x-1.5 disabled:opacity-50"
              >
                <span>↺</span>
                <span>Request Revision</span>
              </button>

              <button
                onClick={() => approvalMutation.mutate({ decision: "REJECTED" })}
                disabled={approvalMutation.isPending || !draft}
                className="px-4 py-2 rounded-lg text-xs font-bold bg-rose-600 hover:bg-rose-500 text-white shadow transition flex items-center space-x-1.5 disabled:opacity-50"
              >
                <span>✕</span>
                <span>Reject Draft</span>
              </button>

              {approvalMutation.isPending && (
                <span className="text-xs text-slate-400 flex items-center space-x-2">
                  <div className="h-3.5 w-3.5 rounded-full border-2 border-amber-400 border-t-transparent animate-spin" />
                  <span>Submitting decision & resuming graph...</span>
                </span>
              )}
            </div>
          </section>
        )}

        {/* Publication Information Section */}
        {publication && (
          <section className="space-y-3 pt-2">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                Publication Dispatch Status
              </h2>
              <span className={`px-2.5 py-0.5 rounded text-[11px] font-semibold border ${STATUS_BADGE_STYLES[publication.status] || "bg-slate-800 text-slate-300 border-slate-700"}`}>
                {publication.status}
              </span>
            </div>
            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3 shadow">
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                  <span className="text-[11px] uppercase font-semibold text-slate-500 block mb-1">
                    Platform
                  </span>
                  <span className="text-slate-200 capitalize font-medium">{publication.platform}</span>
                </div>
                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                  <span className="text-[11px] uppercase font-semibold text-slate-500 block mb-1">
                    External Post ID
                  </span>
                  <span className="text-slate-200 font-mono text-[11px] truncate block" title={publication.external_id || "None"}>
                    {publication.external_id || "—"}
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                  <span className="text-[11px] uppercase font-semibold text-slate-500 block mb-1">
                    Idempotency Key
                  </span>
                  <span className="text-slate-300 font-mono text-[11px] truncate block" title={publication.idempotency_key}>
                    {publication.idempotency_key}
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                  <span className="text-[11px] uppercase font-semibold text-slate-500 block mb-1">
                    Published At
                  </span>
                  <span className="text-emerald-400 font-medium">
                    {publication.published_at ? new Date(publication.published_at).toLocaleString() : "—"}
                  </span>
                </div>
              </div>
              {publication.url && (
                <div className="pt-1 flex items-center space-x-2 text-xs">
                  <span className="text-slate-400">Post URL:</span>
                  <a
                    href={publication.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-indigo-400 hover:text-indigo-300 underline font-mono truncate"
                  >
                    {publication.url}
                  </a>
                </div>
              )}
              {publication.error && (
                <div className="p-3 rounded-lg bg-rose-950/50 border border-rose-800 text-rose-300 text-xs font-mono">
                  {publication.error}
                </div>
              )}

              {/* Metrics & Analytics Section */}
              {publication.status === "PUBLISHED" && (
                <div className="mt-4 pt-4 border-t border-slate-800/80 space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                        Publication Metrics & Analytics
                      </h3>
                      <p className="text-[11px] text-slate-500">
                        Real performance metrics polled from Buffer
                      </p>
                    </div>
                    <div className="flex items-center space-x-2">
                    <button
                      onClick={() => setShowManualMetricsForm(!showManualMetricsForm)}
                      className="px-3 py-1.5 rounded-lg border border-slate-700 hover:bg-slate-800 text-slate-200 text-xs font-semibold transition-colors"
                    >
                      {showManualMetricsForm ? "Cancel manual entry" : "Enter metrics from LinkedIn"}
                    </button>
                    <button
                      onClick={() => syncMetricsMutation.mutate()}
                      disabled={syncMetricsMutation.isPending}
                      className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold flex items-center space-x-1.5 shadow transition-colors"
                    >
                      {syncMetricsMutation.isPending ? (
                        <>
                          <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin mr-1" />
                          <span>Syncing...</span>
                        </>
                      ) : (
                        <span>Sync Metrics</span>
                      )}
                    </button>
                    </div>
                  </div>

                  {/* One analytics status, derived by the backend from the most recent attempt (CP-D.1, D.5) */}
                  {(() => {
                    const status = publication.analytics_status;
                    const schedule = publication.schedule_info;
                    const state = status?.state ?? "none";
                    const allSnapshots = analyticsSnapshots || [];
                    const validSnapshots = allSnapshots.filter(
                      (snap) => !snap.metrics.is_stub && !snap.metrics.invalid_reason
                    );
                    const latestValid = validSnapshots[0] ?? null;
                    const metrics = latestValid?.metrics ?? null;
                    const showNumbers = !!metrics && (state === "available" || state === "manual");
                    const visibleSnapshots = showInvalidRows ? allSnapshots : validSnapshots;
                    const hiddenCount = allSnapshots.length - validSnapshots.length;

                    const headline =
                      state === "available" ? "Metrics from Buffer"
                      : state === "manual" ? "Entered manually"
                      : state === "not_collected_yet" ? "Buffer has no metrics for this post yet"
                      : state === "network_error" ? "Couldn't reach Buffer from this server"
                      : state === "failed" ? "Last sync failed"
                      : "No metrics checked yet";
                    const tone =
                      state === "network_error" || state === "failed"
                        ? "bg-rose-950/40 border-rose-800 text-rose-200"
                        : state === "available" || state === "manual"
                        ? "bg-slate-900/60 border-slate-800 text-slate-200"
                        : "bg-amber-950/30 border-amber-800/80 text-amber-200";
                    const reason =
                      state === "not_collected_yet"
                        ? `Buffer responded at ${fmtDateTime(status?.last_buffer_response_at)} but has no metrics for this post yet.`
                        : state === "network_error"
                        ? `This server could not reach Buffer (network error). Last successful contact: ${fmtDateTime(status?.last_buffer_response_at, "none")}.`
                        : state === "failed"
                        ? `Provider error: ${status?.last_attempt_message ?? "unknown"}`
                        : null;
                    const collected =
                      latestValid && state === "manual" ? `Entered manually on ${fmtDateTime(latestValid.collected_at)}`
                      : latestValid && state === "available" ? `Collected ${fmtDateTime(latestValid.collected_at)}`
                      : null;
                    const attemptNo = status?.attempt_number ?? schedule?.attempt_number ?? 1;
                    const lastAttempt = status?.last_attempt_at
                      ? `${fmtDateTime(status.last_attempt_at)} — ${OUTCOME_LABELS[status.last_attempt_outcome ?? ""] ?? status.last_attempt_outcome}${status.last_attempt_source === "manual" ? " (your click)" : ""}`
                      : "none yet";

                    return (
                      <div className="space-y-4">
                        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                          {[
                            ["Impressions", metrics?.impressions],
                            ["Clicks", metrics?.clicks],
                            ["Likes / Reactions", metrics?.likes ?? metrics?.reactions],
                            ["Comments", metrics?.comments],
                            ["Shares", metrics?.shares],
                          ].map(([label, value]) => (
                            <div key={label as string} className="p-3 rounded-lg bg-slate-950/70 border border-slate-800">
                              <span className="text-[10px] uppercase font-semibold text-slate-500 block mb-1">{label}</span>
                              <span className="text-lg font-bold text-slate-100 font-mono">
                                {showNumbers ? ((value as number | undefined) ?? 0) : "—"}
                              </span>
                            </div>
                          ))}
                        </div>

                        <div data-testid="analytics-status" data-state={state} className={`p-4 rounded-xl border space-y-2 ${tone}`}>
                          <div className="text-xs font-semibold">{headline}</div>
                          {reason && <p className="text-[11px]">{reason}</p>}
                          {collected && <p className="text-[11px] font-mono">{collected}</p>}
                          {syncError && (
                            <p className="text-[11px] font-mono text-rose-300">
                              Sync Metrics ({fmtDateTime(new Date().toISOString())}): {syncError}
                            </p>
                          )}
                          <div className="text-[11px] font-mono space-y-1 pt-1 text-slate-400">
                            <div>Last attempt: {lastAttempt}</div>
                            <div>Last successful Buffer response: {fmtDateTime(status?.last_buffer_response_at, "none")}</div>
                            {status && !status.scheduler_running && status.next_sync_at && (
                              <div className="text-amber-300" data-testid="analytics-scheduler-off">
                                Automatic sync is OFF. Start the worker: <code>python -m app.scheduler</code>
                              </div>
                            )}
                            {status?.network_retry_paused && (
                              <div className="text-amber-300">
                                Automatic retries paused after {status.network_failures_in_row} network failures in a row. Use Sync Metrics to try again.
                              </div>
                            )}
                            {!status?.network_retry_paused && status?.next_sync_at && (
                              <div data-testid="analytics-next-sync">
                                {status.next_sync_overdue
                                  ? `Overdue since ${fmtDateTime(status.next_sync_at)}`
                                  : `Next sync ${fmtDateTime(status.next_sync_at)}`}
                                {` · Attempt ${attemptNo} of 6`}
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Manual Metrics Entry Bar / Form (CP-1.5) */}
                        <div className="pt-2 border-t border-slate-800/60 flex flex-col space-y-3">
                          {showManualMetricsForm && (
                            <div className="p-4 rounded-lg bg-slate-950/80 border border-slate-800 space-y-3">
                              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                                Record Manual Snapshot from LinkedIn
                              </h4>
                              {manualError && (
                                <p className="text-xs text-rose-400">{manualError}</p>
                              )}
                              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-xs">
                                <div>
                                  <label className="text-[10px] text-slate-400 uppercase block mb-1">Impressions</label>
                                  <input
                                    type="number"
                                    min="0"
                                    value={manualImpressions}
                                    onChange={(e) => setManualImpressions(Math.max(0, parseInt(e.target.value) || 0))}
                                    className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1 text-slate-100 font-mono text-xs"
                                  />
                                </div>
                                <div>
                                  <label className="text-[10px] text-slate-400 uppercase block mb-1">Reactions</label>
                                  <input
                                    type="number"
                                    min="0"
                                    value={manualReactions}
                                    onChange={(e) => setManualReactions(Math.max(0, parseInt(e.target.value) || 0))}
                                    className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1 text-slate-100 font-mono text-xs"
                                  />
                                </div>
                                <div>
                                  <label className="text-[10px] text-slate-400 uppercase block mb-1">Comments</label>
                                  <input
                                    type="number"
                                    min="0"
                                    value={manualComments}
                                    onChange={(e) => setManualComments(Math.max(0, parseInt(e.target.value) || 0))}
                                    className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1 text-slate-100 font-mono text-xs"
                                  />
                                </div>
                                <div>
                                  <label className="text-[10px] text-slate-400 uppercase block mb-1">Clicks</label>
                                  <input
                                    type="number"
                                    min="0"
                                    value={manualClicks}
                                    onChange={(e) => setManualClicks(Math.max(0, parseInt(e.target.value) || 0))}
                                    className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1 text-slate-100 font-mono text-xs"
                                  />
                                </div>
                                <div>
                                  <label className="text-[10px] text-slate-400 uppercase block mb-1">Shares</label>
                                  <input
                                    type="number"
                                    min="0"
                                    value={manualShares}
                                    onChange={(e) => setManualShares(Math.max(0, parseInt(e.target.value) || 0))}
                                    className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1 text-slate-100 font-mono text-xs"
                                  />
                                </div>
                              </div>
                              <div className="flex justify-end pt-1">
                                <button
                                  onClick={() => manualMetricsMutation.mutate()}
                                  disabled={manualMetricsMutation.isPending}
                                  className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-semibold shadow transition"
                                >
                                  {manualMetricsMutation.isPending ? "Saving..." : "Save Manual Snapshot"}
                                </button>
                              </div>
                            </div>
                          )}
                        </div>

                        {/* Historical Snapshots Table */}
                        {allSnapshots.length > 0 && (
                          <div className="mt-3 pt-3 border-t border-slate-800/60">
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-[11px] font-semibold text-slate-400">
                                Historical Snapshots ({visibleSnapshots.length})
                              </span>
                              {hiddenCount > 0 && (
                                <button
                                  onClick={() => setShowInvalidRows(!showInvalidRows)}
                                  className="text-[10px] text-slate-400 hover:text-slate-200 underline"
                                >
                                  {showInvalidRows ? "Hide test / invalid rows" : `Show test / invalid rows (${hiddenCount})`}
                                </button>
                              )}
                              {isAnalyticsLoading && (
                                <span className="text-[10px] text-slate-500 animate-pulse">Refreshing...</span>
                              )}
                            </div>
                            <div className="overflow-x-auto rounded-lg border border-slate-800/80 bg-slate-950/40">
                              <table className="w-full text-left text-xs">
                                <thead className="bg-slate-900/80 text-[10px] uppercase text-slate-500 border-b border-slate-800/80">
                                  <tr>
                                    <th className="py-2 px-3 font-semibold">Collected At</th>
                                    <th className="py-2 px-3 font-semibold">Provider</th>
                                    <th className="py-2 px-3 font-semibold text-right">Impressions</th>
                                    <th className="py-2 px-3 font-semibold text-right">Clicks</th>
                                    <th className="py-2 px-3 font-semibold text-right">Reactions</th>
                                    <th className="py-2 px-3 font-semibold text-right">Comments</th>
                                    <th className="py-2 px-3 font-semibold text-right">Shares</th>
                                    <th className="py-2 px-3 font-semibold text-center">Status</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-800/50 font-mono text-[11px]">
                                  {visibleSnapshots.map((snap) => {
                                    const isQuarantined = !!snap.metrics.invalid_reason;
                                    const isStub = !!snap.metrics.is_stub;
                                    return (
                                      <tr key={snap.id} className="hover:bg-slate-900/40">
                                        <td className="py-2 px-3 text-slate-300 whitespace-nowrap">
                                          {new Date(snap.collected_at).toLocaleString()}
                                        </td>
                                        <td className="py-2 px-3 text-slate-400">
                                          {isStub ? (
                                            <span className="px-1.5 py-0.5 rounded text-[10px] bg-amber-950/60 text-amber-400 border border-amber-800/60">stub</span>
                                          ) : snap.metrics.provider === "manual" ? (
                                            <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-950/60 text-emerald-300 border border-emerald-800/60">
                                              manual
                                            </span>
                                          ) : (
                                            <span className="px-1.5 py-0.5 rounded text-[10px] bg-indigo-950/60 text-indigo-300 border border-indigo-800/60">
                                              {snap.metrics.provider || "buffer"}
                                            </span>
                                          )}
                                        </td>
                                        <td className="py-2 px-3 text-right text-slate-200">
                                          {snap.metrics.impressions ?? 0}
                                        </td>
                                        <td className="py-2 px-3 text-right text-slate-200">
                                          {snap.metrics.clicks ?? 0}
                                        </td>
                                        <td className="py-2 px-3 text-right text-slate-200">
                                          {snap.metrics.likes ?? snap.metrics.reactions ?? 0}
                                        </td>
                                        <td className="py-2 px-3 text-right text-slate-200">
                                          {snap.metrics.comments ?? 0}
                                        </td>
                                        <td className="py-2 px-3 text-right text-slate-200">
                                          {snap.metrics.shares ?? 0}
                                        </td>
                                        <td className="py-2 px-3 text-center">
                                          {isQuarantined ? (
                                            <span className="px-1.5 py-0.5 rounded text-[9px] bg-rose-950/70 text-rose-300 border border-rose-800" title={snap.metrics.invalid_reason}>
                                              quarantined
                                            </span>
                                          ) : isStub ? (
                                            <span className="px-1.5 py-0.5 rounded text-[9px] bg-amber-950/70 text-amber-400 border border-amber-800">
                                              stub
                                            </span>
                                          ) : (
                                            <span className="text-[10px] text-slate-400">
                                              {snap.metrics.post_status || "synced"}
                                            </span>
                                          )}
                                        </td>
                                      </tr>
                                    );
                                  })}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })()}

                </div>
              )}
            </div>
          </section>
        )}

        {/* Draft Section */}
        {draft && draft.current_version && (
          <section className="space-y-3 pt-2">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                Generated Draft (v{draft.current_version.version_number})
              </h2>
              <span className="text-xs font-mono text-slate-500">
                Origin: {draft.current_version.origin}
              </span>
            </div>
            <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-4 shadow">
              {draft.current_version.title && (
                <h3 className="text-base font-bold text-slate-100 border-b border-slate-800 pb-2">
                  {draft.current_version.title}
                </h3>
              )}

              {/* Draft Lint Warnings Banner */}
              {draft.current_version.lint_warnings && draft.current_version.lint_warnings.length > 0 && (
                <div className="p-3 rounded-lg bg-amber-950/40 border border-amber-800/80 text-amber-300 space-y-1.5 text-xs">
                  <div className="flex items-center space-x-1.5 font-semibold text-amber-400 text-[11px] uppercase tracking-wider">
                    <span>⚠</span>
                    <span>Editorial Lint Warnings ({draft.current_version.lint_warnings.length})</span>
                  </div>
                  <ul className="list-disc pl-4 space-y-0.5 text-[11px] text-amber-200/90 font-mono">
                    {draft.current_version.lint_warnings.map((warn: any, idx: number) => (
                      <li key={idx}>
                        <span className="font-semibold capitalize text-amber-300">[{warn.category}]:</span> {warn.message}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="text-xs leading-relaxed text-slate-300 font-mono whitespace-pre-wrap">
                {draft.current_version.body}
              </div>

              {/* LinkedIn Plain Text Preview Panel (CP-3.3) */}
              <div className="mt-4 pt-4 border-t border-slate-800 space-y-3" data-testid="linkedin-preview-panel">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <span className="text-xs font-bold uppercase tracking-wider text-indigo-400">
                      LinkedIn Preview (Plain Text)
                    </span>
                    <span className="text-[10px] bg-indigo-950/70 border border-indigo-800 text-indigo-300 px-1.5 py-0.5 rounded">
                      Publish Payload
                    </span>
                  </div>
                  <div className="flex items-center space-x-2 text-xs font-mono">
                    <span
                      data-testid="linkedin-char-counter"
                      className={`font-semibold ${
                        (draft.current_version.char_count ?? draft.linkedin_preview?.length ?? 0) > 3000
                          ? "text-rose-400"
                          : "text-slate-400"
                      }`}
                    >
                      {(draft.current_version.char_count ?? draft.linkedin_preview?.length ?? 0).toLocaleString()} / 3,000 chars
                    </span>
                  </div>
                </div>

                {draft.current_version.will_truncate && (
                  <div className="p-2.5 rounded-lg bg-amber-950/50 border border-amber-800 text-amber-300 text-xs flex items-center space-x-2">
                    <span>⚠️</span>
                    <span>
                      Draft exceeds LinkedIn platform limit (3,000 characters) and will be cleanly truncated at sentence boundary upon publishing.
                    </span>
                  </div>
                )}

                <div
                  data-testid="linkedin-preview-text"
                  className="p-4 rounded-lg bg-slate-950/80 border border-slate-800/80 text-xs text-slate-200 font-sans whitespace-pre-wrap leading-relaxed selection:bg-indigo-900"
                >
                  {draft.current_version.linkedin_preview || draft.linkedin_preview || draft.current_version.body}
                </div>
              </div>
            </div>

            {/* Media Section */}
            <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-4 shadow">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                    Media (v{draft.current_version.version_number})
                  </h3>
                  <p className="text-[11px] text-slate-500">
                    Version-locked visual media asset
                  </p>
                </div>
                <button
                  onClick={() => generateMediaMutation.mutate({ regenerate: !!(mediaAssets && mediaAssets.length > 0) })}
                  disabled={generateMediaMutation.isPending}
                  className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold flex items-center space-x-1.5 shadow transition-colors"
                >
                  {generateMediaMutation.isPending ? (
                    <>
                      <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin mr-1" />
                      <span>Generating...</span>
                    </>
                  ) : (
                    <span>{mediaAssets && mediaAssets.length > 0 ? "Regenerate Image" : "Generate Image"}</span>
                  )}
                </button>
              </div>

              {mediaError && (
                <div className="p-3 rounded-lg bg-rose-950/50 border border-rose-800 text-rose-300 text-xs font-mono">
                  Error: {mediaError}
                </div>
              )}

              {/* Media Asset Preview & Details */}
              {(() => {
                const latestMedia = mediaAssets && mediaAssets.length > 0 ? mediaAssets[0] : null;

                if (!latestMedia) {
                  return (
                    <div className="p-6 rounded-lg bg-slate-950/50 border border-slate-800/80 text-center space-y-2">
                      <p className="text-xs text-slate-400">
                        No image generated for ContentVersion v{draft.current_version.version_number} yet.
                      </p>
                      <p className="text-[11px] text-slate-500">
                        Click "Generate Image" to create an editorial visual asset for review.
                      </p>
                    </div>
                  );
                }

                return (
                  <div className="space-y-4">
                    <div className="rounded-lg overflow-hidden border border-slate-800 bg-slate-950/80">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={`http://localhost:8000${latestMedia.storage_url}`}
                        alt={latestMedia.alt_text || "Generated media asset"}
                        className="w-full max-h-96 object-contain bg-slate-950"
                      />
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                      <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                        <span className="text-[10px] uppercase font-semibold text-slate-500 block mb-1">
                          Type
                        </span>
                        <span className="text-slate-200 font-medium">
                          {latestMedia.type}
                        </span>
                      </div>
                      <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                        <span className="text-[10px] uppercase font-semibold text-slate-500 block mb-1">
                          Provider
                        </span>
                        <span className="text-indigo-300 font-mono text-[11px]">
                          {latestMedia.provider}
                        </span>
                        {latestMedia.asset_metadata?.is_stub && (
                          <span className="text-[9px] text-amber-400 block mt-0.5">test stub</span>
                        )}
                      </div>
                      <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                        <span className="text-[10px] uppercase font-semibold text-slate-500 block mb-1">
                          Status
                        </span>
                        <span className="text-emerald-400 font-medium font-mono text-[11px]">
                          {latestMedia.status}
                        </span>
                      </div>
                      <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                        <span className="text-[10px] uppercase font-semibold text-slate-500 block mb-1">
                          Generated At
                        </span>
                        <span className="text-slate-300 font-mono text-[11px]">
                          {new Date(latestMedia.created_at).toLocaleTimeString()}
                        </span>
                      </div>
                    </div>

                    {latestMedia.alt_text && (
                      <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80 text-xs">
                        <span className="text-[10px] uppercase font-semibold text-slate-500 block mb-1">
                          Alt Text
                        </span>
                        <span className="text-slate-300">
                          {latestMedia.alt_text}
                        </span>
                      </div>
                    )}
                  </div>
                );
              })()}
            </div>
          </section>
        )}

        {/* Content Brief Section */}
        {brief && (
          <section className="space-y-3 pt-2">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Content Brief
            </h2>
            <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800 space-y-2">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                {Object.entries(brief.brief).map(([key, value]) => (
                  <div key={key} className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                    <span className="text-[11px] uppercase font-semibold text-slate-500 block mb-1">
                      {key.replace(/_/g, " ")}
                    </span>
                    <span className="text-slate-300">
                      {typeof value === "object" ? JSON.stringify(value, null, 2) : String(value)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}

        {/* Research Information Section */}
        {research && (
          <section className="space-y-3 pt-2">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Research Findings
            </h2>
            <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800 space-y-3">
              {research.summary && (
                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80 text-xs text-slate-300">
                  <span className="text-[11px] uppercase font-semibold text-slate-500 block mb-1">
                    Summary
                  </span>
                  {research.summary}
                </div>
              )}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                  <span className="text-[11px] uppercase font-semibold text-slate-500 block mb-1">
                    Key Findings
                  </span>
                  <pre className="text-slate-300 font-mono text-[11px] whitespace-pre-wrap overflow-x-auto">
                    {JSON.stringify(research.findings, null, 2)}
                  </pre>
                </div>
                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                  <span className="text-[11px] uppercase font-semibold text-slate-500 block mb-1">
                    Sources
                  </span>
                  <pre className="text-slate-300 font-mono text-[11px] whitespace-pre-wrap overflow-x-auto">
                    {JSON.stringify(research.sources, null, 2)}
                  </pre>
                </div>
              </div>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
