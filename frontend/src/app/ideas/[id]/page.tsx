"use client";

import { use, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { fetchIdea, fetchIdeaSources, startWorkflowRun } from "@/lib/api";

const STATUS_BADGE_STYLES: Record<string, string> = {
  NEW: "bg-blue-900/60 text-blue-300 border-blue-700/50",
  SELECTED: "bg-emerald-900/60 text-emerald-300 border-emerald-700/50",
  IN_PROGRESS: "bg-amber-900/60 text-amber-300 border-amber-700/50",
  PUBLISHED: "bg-purple-900/60 text-purple-300 border-purple-700/50",
  REJECTED: "bg-rose-900/60 text-rose-300 border-rose-700/50",
  EXPIRED: "bg-raised text-muted border-line-strong",
};

interface ScoreMetricProps {
  label: string;
  score?: number | null;
  weight: string;
}

function ScoreMetric({ label, score, weight }: ScoreMetricProps) {
  const percentage = score != null ? Math.round(score * 100) : 0;
  return (
    <div className="bg-panel/60 border border-line/80 rounded-lg p-3.5 space-y-2">
      <div className="flex items-center justify-between text-xs">
        <span className="text-body font-medium">{label}</span>
        <span className="text-subtle font-mono text-[11px]">{weight}</span>
      </div>
      <div className="flex items-end justify-between">
        <span className="text-lg font-bold text-strong font-mono">
          {score != null ? (score * 100).toFixed(0) : "N/A"}
          <span className="text-xs text-subtle font-normal">/100</span>
        </span>
      </div>
      <div className="w-full bg-raised h-1.5 rounded-full overflow-hidden">
        <div
          className="bg-accent-hover h-full rounded-full transition-all duration-500"
          style={{ width: `${Math.min(100, Math.max(0, percentage))}%` }}
        />
      </div>
    </div>
  );
}

export default function IdeaDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();

  interface ConflictInfo {
    message: string;
    workflow_run_id?: string;
    status?: string;
  }

  const [conflict, setConflict] = useState<ConflictInfo | null>(null);

  const {
    data: idea,
    isLoading: isIdeaLoading,
    isError: isIdeaError,
    error: ideaError,
  } = useQuery({
    queryKey: ["idea", id],
    queryFn: () => fetchIdea(id),
  });

  const {
    data: sources,
    isLoading: isSourcesLoading,
  } = useQuery({
    queryKey: ["idea-sources", id],
    queryFn: () => fetchIdeaSources(id),
  });

  const mutation = useMutation({
    mutationFn: () => {
      if (!idea) throw new Error("Idea not loaded");
      return startWorkflowRun(idea.id, idea.strategy_id);
    },
    onSuccess: (data) => {
      setConflict(null);
      const targetId = data.workflow_run_id || data.id;
      router.push(`/workflow-runs/${targetId}`);
    },
    onError: (err: any) => {
      if (err.status === 409 || err.detail?.code === "ACTIVE_WORKFLOW_EXISTS" || err.message?.toLowerCase().includes("active workflow")) {
        const detail = (typeof err.detail === "object" && err.detail !== null) ? err.detail : {};
        let runId = detail.workflow_run_id;
        let runStatus = detail.status;

        // Fallback: if backend returned a string detail with UUID (legacy/stale backend response)
        const msgStr = typeof err.detail === "string" ? err.detail : (err.message || "");
        if (!runId) {
          const uuidMatch = msgStr.match(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i);
          if (uuidMatch) runId = uuidMatch[1];
        }
        if (!runStatus) {
          const statusMatch = msgStr.match(/status ['"]?([A-Z_]+)['"]?/i);
          if (statusMatch) runStatus = statusMatch[1];
        }

        setConflict({
          message: detail.message || msgStr || "An active workflow already exists for this idea.",
          workflow_run_id: runId,
          status: runStatus,
        });
      } else {
        setConflict({
          message: err.message || "Failed to start workflow run.",
        });
      }
    },
  });

  if (isIdeaLoading) {
    return (
      <div className="min-h-screen bg-canvas text-strong flex items-center justify-center">
        <div className="flex flex-col items-center space-y-3">
          <div className="h-7 w-7 rounded-full border-2 border-accent border-t-transparent animate-spin" />
          <p className="text-sm text-muted">Loading idea details...</p>
        </div>
      </div>
    );
  }

  if (isIdeaError || !idea) {
    return (
      <div className="min-h-screen bg-canvas text-strong p-8 max-w-4xl mx-auto">
        <div className="p-4 rounded-lg bg-rose-950/40 border border-rose-800 text-rose-300">
          <h2 className="font-semibold text-sm">Failed to load idea</h2>
          <p className="text-xs mt-1 text-rose-400">
            {(ideaError as Error)?.message || "Idea not found"}
          </p>
          <Link
            href="/ideas"
            className="inline-block mt-4 text-xs font-semibold text-accent-text hover:underline"
          >
            ← Back to Ideas
          </Link>
        </div>
      </div>
    );
  }

  const badgeStyle =
    STATUS_BADGE_STYLES[idea.status] || "bg-raised text-body border-line-strong";

  return (
    <div className="min-h-screen bg-canvas text-strong pb-16">
      {/* Top Navbar */}
      <header className="border-b border-line bg-panel/50 backdrop-blur px-4 sm:px-6 py-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center space-x-3">
          <Link
            href="/ideas"
            className="text-xs font-medium text-muted hover:text-body-strong transition"
          >
            ← Back to Ideas
          </Link>
        </div>
        <div className="flex items-center space-x-3">
          <span className={`px-2.5 py-0.5 rounded text-xs font-semibold border ${badgeStyle}`}>
            {idea.status}
          </span>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 sm:px-6 py-6 sm:py-8 space-y-8">
        {/* 409 Conflict Recovery Banner */}
        {conflict && (
          <div className="p-4 rounded-xl bg-amber-950/50 border border-amber-600/70 text-amber-200 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-xl">
            <div className="space-y-1.5 flex-1">
              <div className="flex items-center space-x-2">
                <span className="text-amber-400 font-bold text-sm">⚠️ Active Workflow Run Found</span>
                {conflict.status && (
                  <span className="text-[11px] px-2 py-0.5 rounded bg-amber-900/80 text-amber-200 font-mono border border-amber-700/60 uppercase">
                    {conflict.status}
                  </span>
                )}
              </div>
              <p className="text-xs text-amber-200/90 leading-relaxed">
                {conflict.status === "NEEDS_REVIEW"
                  ? "This idea already has an active workflow run waiting for your approval."
                  : conflict.status === "RUNNING" || conflict.status === "PENDING" || conflict.status === "PUBLISHING"
                  ? "This idea already has a workflow run actively in progress."
                  : conflict.message}
              </p>
              {conflict.workflow_run_id && (
                <p className="text-[11px] text-amber-300/70 font-mono">
                  Run ID: {conflict.workflow_run_id}
                </p>
              )}
            </div>

            <div className="flex items-center space-x-3 shrink-0">
              {conflict.workflow_run_id && (
                <Link
                  href={`/workflow-runs/${conflict.workflow_run_id}`}
                  className="px-4 py-2 text-xs font-semibold rounded-lg bg-amber-600 hover:bg-amber-500 text-canvas shadow-md transition flex items-center space-x-1.5"
                >
                  <span>Open Existing Workflow</span>
                  <span>→</span>
                </Link>
              )}
              <button
                onClick={() => setConflict(null)}
                className="px-3 py-2 text-xs rounded-lg bg-amber-900/60 hover:bg-amber-800 text-amber-200 border border-amber-700/60 transition"
              >
                Dismiss
              </button>
            </div>
          </div>
        )}

        {/* Idea Header & Action */}
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-6 pb-6 border-b border-line">
          <div className="space-y-3 flex-1">
            <h1 className="text-2xl sm:text-3xl font-bold text-strong tracking-tight leading-snug">
              {idea.title}
            </h1>
            <p className="text-xs text-muted">
              Captured {new Date(idea.created_at).toLocaleString(undefined, {
                dateStyle: "medium",
                timeStyle: "short",
              })}
            </p>
          </div>

          <div className="shrink-0 flex flex-col items-start md:items-end gap-2">
            <button
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending}
              className={`px-5 py-2.5 rounded-lg text-sm font-semibold shadow-md transition flex items-center space-x-2 ${
                mutation.isPending
                  ? "bg-accent-hover/50 text-accent-soft cursor-not-allowed"
                  : "bg-accent hover:bg-accent-hover text-strong shadow-indigo-600/30"
              }`}
            >
              {mutation.isPending ? (
                <>
                  <div className="h-4 w-4 rounded-full border-2 border-white border-t-transparent animate-spin" />
                  <span>Starting Run...</span>
                </>
              ) : (
                <>
                  <span>🚀</span>
                  <span>Start Production Run</span>
                </>
              )}
            </button>
            <span className="text-[11px] text-subtle">
              Triggers LangGraph Research → Approval workflow
            </span>
          </div>
        </div>

        {/* Description Section */}
        {idea.description && (
          <div className="space-y-2">
            <h3 className="text-xs uppercase font-semibold text-muted tracking-wider">
              Idea Narrative
            </h3>
            <div className="p-4 rounded-xl bg-panel/40 border border-line text-body text-sm leading-relaxed whitespace-pre-wrap">
              {idea.description}
            </div>
          </div>
        )}

        {/* Scoring Breakdown */}
        <div className="space-y-4">
          <div className="flex items-baseline justify-between">
            <h3 className="text-xs uppercase font-semibold text-muted tracking-wider">
              Scoring Breakdown
            </h3>
            <div className="flex items-center space-x-2">
              <span className="text-xs text-muted">Final Composite:</span>
              <span className="text-base font-bold text-emerald-400 font-mono">
                {idea.final_score != null ? (idea.final_score * 100).toFixed(1) : "N/A"}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            <ScoreMetric
              label="Relevance"
              score={idea.relevance_score}
              weight="Weight: 30%"
            />
            <ScoreMetric
              label="Trend Momentum"
              score={idea.trend_score}
              weight="Weight: 20%"
            />
            <ScoreMetric
              label="Novelty"
              score={idea.novelty_score}
              weight="Weight: 20%"
            />
            <ScoreMetric
              label="Audience Fit"
              score={idea.audience_fit_score}
              weight="Weight: 15%"
            />
            <ScoreMetric
              label="Source Quality"
              score={idea.source_quality_score}
              weight="Weight: 15%"
            />
          </div>
        </div>

        {/* Source Provenance */}
        <div className="space-y-3 pt-4 border-t border-line">
          <h3 className="text-xs uppercase font-semibold text-muted tracking-wider">
            Source Provenance ({sources?.length || 0})
          </h3>

          {isSourcesLoading && (
            <div className="py-6 flex items-center justify-center space-x-2 text-xs text-subtle">
              <div className="h-4 w-4 rounded-full border border-accent border-t-transparent animate-spin" />
              <span>Loading provenance data...</span>
            </div>
          )}

          {!isSourcesLoading && (!sources || sources.length === 0) && (
            <div className="p-4 rounded-lg bg-panel/30 border border-line text-xs text-subtle">
              No linked source items found for this idea.
            </div>
          )}

          {!isSourcesLoading && sources && sources.length > 0 && (
            <div className="space-y-2">
              {sources.map((src) => (
                <div
                  key={src.id}
                  className="p-3.5 rounded-lg bg-panel/50 border border-line/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                >
                  <div className="space-y-1 min-w-0 flex-1">
                    <div className="flex items-center space-x-2">
                      <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-raised text-accent-text border border-line-strong">
                        {src.source_type}
                      </span>
                      {src.author && (
                        <span className="text-xs text-muted">by {src.author}</span>
                      )}
                    </div>
                    <a
                      href={src.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs sm:text-sm font-medium text-body-strong hover:text-accent-text transition truncate block"
                    >
                      {src.title || src.url}
                    </a>
                  </div>
                  <a
                    href={src.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-accent-text hover:text-accent-soft font-medium shrink-0 flex items-center space-x-1"
                  >
                    <span>Inspect</span>
                    <span>↗</span>
                  </a>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
