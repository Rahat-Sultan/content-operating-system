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
  EXPIRED: "bg-slate-800 text-slate-400 border-slate-700",
};

interface ScoreMetricProps {
  label: string;
  score?: number | null;
  weight: string;
}

function ScoreMetric({ label, score, weight }: ScoreMetricProps) {
  const percentage = score != null ? Math.round(score * 100) : 0;
  return (
    <div className="bg-slate-900/60 border border-slate-800/80 rounded-lg p-3.5 space-y-2">
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-300 font-medium">{label}</span>
        <span className="text-slate-500 font-mono text-[11px]">{weight}</span>
      </div>
      <div className="flex items-end justify-between">
        <span className="text-lg font-bold text-slate-100 font-mono">
          {score != null ? (score * 100).toFixed(0) : "N/A"}
          <span className="text-xs text-slate-500 font-normal">/100</span>
        </span>
      </div>
      <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
        <div
          className="bg-indigo-500 h-full rounded-full transition-all duration-500"
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

  const [conflictError, setConflictError] = useState<string | null>(null);

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
      setConflictError(null);
      router.push(`/workflow-runs/${data.id}`);
    },
    onError: (err: any) => {
      if (err.status === 409 || err.message?.includes("Active workflow run already exists")) {
        setConflictError(err.message);
      } else {
        setConflictError(err.message || "Failed to start workflow run.");
      }
    },
  });

  if (isIdeaLoading) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center">
        <div className="flex flex-col items-center space-y-3">
          <div className="h-7 w-7 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
          <p className="text-sm text-slate-400">Loading idea details...</p>
        </div>
      </div>
    );
  }

  if (isIdeaError || !idea) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 p-8 max-w-4xl mx-auto">
        <div className="p-4 rounded-lg bg-rose-950/40 border border-rose-800 text-rose-300">
          <h2 className="font-semibold text-sm">Failed to load idea</h2>
          <p className="text-xs mt-1 text-rose-400">
            {(ideaError as Error)?.message || "Idea not found"}
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
    STATUS_BADGE_STYLES[idea.status] || "bg-slate-800 text-slate-300 border-slate-700";

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 pb-16">
      {/* Top Navbar */}
      <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur px-6 py-4 flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center space-x-3">
          <Link
            href="/ideas"
            className="text-xs font-medium text-slate-400 hover:text-slate-200 transition"
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

      <main className="max-w-4xl mx-auto px-6 py-8 space-y-8">
        {/* 409 Conflict Banner */}
        {conflictError && (
          <div className="p-4 rounded-xl bg-amber-950/40 border border-amber-600/70 text-amber-200 flex flex-col md:flex-row md:items-center justify-between gap-3 shadow-lg">
            <div className="space-y-1">
              <div className="flex items-center space-x-2">
                <span className="text-amber-400 font-bold text-sm">⚠️ Conflict</span>
                <span className="text-xs text-amber-300/80 uppercase tracking-wide">
                  Concurrent Run Guard
                </span>
              </div>
              <p className="text-xs text-amber-200 font-mono leading-relaxed">
                {conflictError}
              </p>
            </div>
            <button
              onClick={() => setConflictError(null)}
              className="self-start md:self-auto px-3 py-1 text-xs rounded bg-amber-900/60 hover:bg-amber-800 text-amber-100 border border-amber-700/60"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Idea Header & Action */}
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-6 pb-6 border-b border-slate-800">
          <div className="space-y-3 flex-1">
            <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight leading-snug">
              {idea.title}
            </h1>
            <p className="text-xs text-slate-400">
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
                  ? "bg-indigo-700/50 text-indigo-300 cursor-not-allowed"
                  : "bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-600/30"
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
            <span className="text-[11px] text-slate-500">
              Triggers LangGraph Research → Approval workflow
            </span>
          </div>
        </div>

        {/* Description Section */}
        {idea.description && (
          <div className="space-y-2">
            <h3 className="text-xs uppercase font-semibold text-slate-400 tracking-wider">
              Idea Narrative
            </h3>
            <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800 text-slate-300 text-sm leading-relaxed whitespace-pre-wrap">
              {idea.description}
            </div>
          </div>
        )}

        {/* Scoring Breakdown */}
        <div className="space-y-4">
          <div className="flex items-baseline justify-between">
            <h3 className="text-xs uppercase font-semibold text-slate-400 tracking-wider">
              Scoring Breakdown
            </h3>
            <div className="flex items-center space-x-2">
              <span className="text-xs text-slate-400">Final Composite:</span>
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
        <div className="space-y-3 pt-4 border-t border-slate-800">
          <h3 className="text-xs uppercase font-semibold text-slate-400 tracking-wider">
            Source Provenance ({sources?.length || 0})
          </h3>

          {isSourcesLoading && (
            <div className="py-6 flex items-center justify-center space-x-2 text-xs text-slate-500">
              <div className="h-4 w-4 rounded-full border border-indigo-500 border-t-transparent animate-spin" />
              <span>Loading provenance data...</span>
            </div>
          )}

          {!isSourcesLoading && (!sources || sources.length === 0) && (
            <div className="p-4 rounded-lg bg-slate-900/30 border border-slate-800 text-xs text-slate-500">
              No linked source items found for this idea.
            </div>
          )}

          {!isSourcesLoading && sources && sources.length > 0 && (
            <div className="space-y-2">
              {sources.map((src) => (
                <div
                  key={src.id}
                  className="p-3.5 rounded-lg bg-slate-900/50 border border-slate-800/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                >
                  <div className="space-y-1 min-w-0 flex-1">
                    <div className="flex items-center space-x-2">
                      <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-slate-800 text-indigo-400 border border-slate-700">
                        {src.source_type}
                      </span>
                      {src.author && (
                        <span className="text-xs text-slate-400">by {src.author}</span>
                      )}
                    </div>
                    <a
                      href={src.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs sm:text-sm font-medium text-slate-200 hover:text-indigo-400 transition truncate block"
                    >
                      {src.title || src.url}
                    </a>
                  </div>
                  <a
                    href={src.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-indigo-400 hover:text-indigo-300 font-medium shrink-0 flex items-center space-x-1"
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
