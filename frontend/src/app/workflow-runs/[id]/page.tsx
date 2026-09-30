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

export default function WorkflowRunDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const [feedback, setFeedback] = useState("");
  const [decisionError, setDecisionError] = useState<string | null>(null);

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
  const { data: research } = useQuery({
    queryKey: ["workflow-run-research", id],
    queryFn: () => fetchWorkflowRunResearch(id),
    enabled: !!run && (run.status === "NEEDS_REVIEW" || run.status === "COMPLETED" || run.status === "PUBLISHING" || run.status === "REJECTED"),
    retry: false,
  });

  // 4. Brief Information
  const { data: brief } = useQuery({
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
          <button
            onClick={() => refetch()}
            className="text-xs px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700"
          >
            Refresh
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
              <div className="text-xs leading-relaxed text-slate-300 font-mono whitespace-pre-wrap">
                {draft.current_version.body}
              </div>
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
