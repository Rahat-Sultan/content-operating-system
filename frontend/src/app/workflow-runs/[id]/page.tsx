"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { fetchWorkflowRun } from "@/lib/api";

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

export default function WorkflowRunDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  const {
    data: run,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["workflow-run", id],
    queryFn: () => fetchWorkflowRun(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      // Keep polling while active
      if (status === "RUNNING" || status === "PENDING" || status === "PAUSED" || status === "PUBLISHING") {
        return 2500;
      }
      return false;
    },
  });

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center">
        <div className="flex flex-col items-center space-y-3">
          <div className="h-7 w-7 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
          <p className="text-sm text-slate-400">Loading workflow run {id}...</p>
        </div>
      </div>
    );
  }

  if (isError || !run) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 p-8 max-w-4xl mx-auto">
        <div className="p-4 rounded-lg bg-rose-950/40 border border-rose-800 text-rose-300">
          <h2 className="font-semibold text-sm">Failed to load workflow run</h2>
          <p className="text-xs mt-1 text-rose-400">
            {(error as Error)?.message || "Run not found"}
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
    <div className="min-h-screen bg-slate-950 text-slate-100 pb-16">
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
          <button
            onClick={() => refetch()}
            className="text-xs px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700"
          >
            Refresh
          </button>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-8 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-slate-800">
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-xs font-mono text-slate-400">Run ID: {run.id}</span>
            </div>
            <h1 className="text-2xl font-bold text-white tracking-tight mt-1">
              Production Workflow Execution
            </h1>
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
              {run.current_phase || "None"}
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

        {run.status === "NEEDS_REVIEW" && (
          <div className="p-4 rounded-xl bg-amber-950/30 border border-amber-700/60 text-amber-200 space-y-2">
            <h4 className="text-sm font-semibold text-amber-300">⏸️ Workflow Paused for Approval</h4>
            <p className="text-xs leading-relaxed text-amber-200/90">
              The workflow has successfully paused at the Approval checkpoint. Waiting for human editorial review.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
