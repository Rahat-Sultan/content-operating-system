"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { PlatformBadge } from "@/components/PlatformBadge";
import { archiveIdea, deleteIdea, fetchIdeas, IdeaItem, restoreIdea } from "@/lib/api";

const STATUS_FILTERS = [
  "ALL",
  "NEW",
  "SELECTED",
  "IN_PROGRESS",
  "PUBLISHED",
  "REJECTED",
  "EXPIRED",
];

const STATUS_BADGE_STYLES: Record<string, string> = {
  NEW: "bg-blue-900/60 text-blue-300 border-blue-700/50",
  SELECTED: "bg-emerald-900/60 text-emerald-300 border-emerald-700/50",
  IN_PROGRESS: "bg-amber-900/60 text-amber-300 border-amber-700/50",
  PUBLISHED: "bg-purple-900/60 text-purple-300 border-purple-700/50",
  REJECTED: "bg-rose-900/60 text-rose-300 border-rose-700/50",
  EXPIRED: "bg-slate-800 text-slate-400 border-slate-700",
};

export default function IdeasPage() {
  const [view, setView] = useState<"active" | "archive">("active");
  const [selectedStatus, setSelectedStatus] = useState("ALL");
  const [rowError, setRowError] = useState<Record<string, string>>({});
  const queryClient = useQueryClient();

  // Archived ideas (status REJECTED) live in their own view. Active view never shows them.
  const queryStatus = view === "archive" ? "REJECTED" : selectedStatus;
  const {
    data: fetched,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["ideas", queryStatus],
    queryFn: () => fetchIdeas(queryStatus),
  });
  const ideas = fetched?.filter((i) => (view === "archive" ? i.status === "REJECTED" : i.status !== "REJECTED"));

  const act = useMutation({
    mutationFn: async ({ id, kind }: { id: string; kind: "archive" | "restore" | "delete" }) => {
      if (kind === "archive") return archiveIdea(id);
      if (kind === "restore") return restoreIdea(id);
      return deleteIdea(id);
    },
    onSuccess: (_, v) => {
      setRowError((e) => ({ ...e, [v.id]: "" }));
      queryClient.invalidateQueries({ queryKey: ["ideas"] });
    },
    onError: (err: any, v) => {
      setRowError((e) => ({ ...e, [v.id]: err?.message || "Action failed." }));
    },
  });

  function confirmDelete(idea: IdeaItem) {
    if (window.confirm(`Delete "${idea.title}" permanently? This cannot be undone.`)) {
      act.mutate({ id: idea.id, kind: "delete" });
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Top Navbar */}
      <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur px-6 py-4 flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center space-x-3">
          <div className="h-8 w-8 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-white shadow-lg shadow-indigo-500/30">
            C
          </div>
          <div>
            <h1 className="text-lg font-semibold text-white tracking-tight">Content OS</h1>
            <p className="text-xs text-slate-400">Autonomous Content Intelligence Engine</p>
          </div>
        </div>
        <nav className="flex items-center space-x-6">
          <Link
            href="/analytics"
            className="text-sm font-medium text-slate-400 hover:text-slate-200 transition-colors"
          >
            Analytics
          </Link>
          <Link
            href="/sources"
            className="text-sm font-medium text-slate-400 hover:text-slate-200 transition-colors"
          >
            Sources
          </Link>
          <Link
            href="/strategies"
            className="text-sm font-medium text-slate-400 hover:text-slate-200 transition-colors"
          >
            Strategies
          </Link>
          <Link
            href="/ideas"
            className="text-sm font-medium text-indigo-400 hover:text-indigo-300 transition-colors"
          >
            Ideas
          </Link>
        </nav>
      </header>

      {/* Main Content Area */}
      <main className="max-w-6xl mx-auto px-6 py-8">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-800">
          <div>
            <h2 className="text-2xl font-bold text-white tracking-tight">Content Ideas</h2>
            <p className="text-sm text-slate-400 mt-1">
              Curated signals and candidate ideas ranked by multi-dimensional scoring.
            </p>
          </div>
          <button
            onClick={() => refetch()}
            className="self-start md:self-auto px-3.5 py-1.5 rounded-md text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
          >
            Refresh List
          </button>
        </div>

        {/* Active ideas or the Rejected archive */}
        <div role="tablist" className="flex items-center gap-2 pt-5">
          {(["active", "archive"] as const).map((v) => (
            <button
              key={v}
              role="tab"
              aria-selected={view === v}
              onClick={() => setView(v)}
              data-testid={`ideas-view-${v}`}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition-colors ${
                view === v
                  ? "bg-indigo-600 border-indigo-500 text-white"
                  : "bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200"
              }`}
            >
              {v === "active" ? "Active" : "Rejected (archive)"}
            </button>
          ))}
          {view === "archive" && (
            <span className="text-[11px] text-slate-500 ml-2">
              Archived ideas are kept, not deleted. Restore one to bring it back.
            </span>
          )}
        </div>

        {/* Filter Pills */}
        {view === "active" && (
        <div className="flex items-center gap-2 overflow-x-auto py-4 scrollbar-none">
          <span className="text-xs uppercase tracking-wider text-slate-500 font-semibold mr-2">
            Status:
          </span>
          {STATUS_FILTERS.filter((x) => x !== "REJECTED").map((status) => {
            const isActive = selectedStatus === status;
            return (
              <button
                key={status}
                onClick={() => setSelectedStatus(status)}
                className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                  isActive
                    ? "bg-indigo-600 border-indigo-500 text-white shadow-sm"
                    : "bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200 hover:border-slate-700"
                }`}
              >
                {status}
              </button>
            );
          })}
        </div>
        )}

        {/* State: Loading */}
        {isLoading && (
          <div className="py-20 flex flex-col items-center justify-center space-y-3">
            <div className="h-7 w-7 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
            <p className="text-sm text-slate-400">Loading ideas...</p>
          </div>
        )}

        {/* State: Error */}
        {isError && (
          <div className="my-8 p-4 rounded-lg bg-rose-950/40 border border-rose-800/80 text-rose-300">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold text-sm">Failed to load ideas</p>
                <p className="text-xs mt-1 text-rose-400/90">{(error as Error)?.message}</p>
              </div>
              <button
                onClick={() => refetch()}
                className="px-3 py-1 rounded text-xs bg-rose-900/60 hover:bg-rose-800 text-rose-200 border border-rose-700"
              >
                Retry
              </button>
            </div>
          </div>
        )}

        {/* State: Empty */}
        {!isLoading && !isError && ideas && ideas.length === 0 && (
          <div className="py-16 text-center border border-dashed border-slate-800 rounded-xl bg-slate-900/30 p-8 my-6">
            <p className="text-base font-medium text-slate-300">No ideas found</p>
            <p className="text-xs text-slate-500 mt-1">
              {view === "archive"
                ? "Nothing archived. Archived ideas appear here."
                : selectedStatus === "ALL"
                ? "No ideas have been captured yet."
                : `No ideas matching status "${selectedStatus}".`}
            </p>
          </div>
        )}

        {/* Ideas Grid / List */}
        {!isLoading && !isError && ideas && ideas.length > 0 && (
          <div className="grid grid-cols-1 gap-4 mt-2">
            {ideas.map((idea) => {
              const badgeStyle =
                STATUS_BADGE_STYLES[idea.status] ||
                "bg-slate-800 text-slate-300 border-slate-700";

              return (
                <div key={idea.id} className="rounded-xl bg-slate-900/70 border border-slate-800 hover:border-slate-700 transition shadow-sm">
                <Link
                  href={`/ideas/${idea.id}`}
                  className="group block p-5"
                >
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                    <div className="space-y-1.5 flex-1 min-w-0">
                      <div className="flex items-center gap-2.5 flex-wrap">
                        <span
                          className={`px-2 py-0.5 rounded text-[11px] font-semibold border ${badgeStyle}`}
                        >
                          {idea.status}
                        </span>
                        <span className="text-xs text-slate-500">
                          {new Date(idea.created_at).toLocaleDateString(undefined, {
                            month: "short",
                            day: "numeric",
                            year: "numeric",
                          })}
                        </span>
                        {idea.strategy_name && (
                          <span
                            data-testid="idea-strategy"
                            className="px-2 py-0.5 rounded border border-indigo-800 bg-indigo-950/50 text-[11px] font-medium text-indigo-300"
                          >
                            Strategy: {idea.strategy_name}
                          </span>
                        )}
                        {(idea.platforms ?? []).map((p) => (
                          <PlatformBadge key={p} platform={p} />
                        ))}
                      </div>
                      <h3 className="text-base font-semibold text-slate-100 group-hover:text-indigo-400 transition-colors">
                        {idea.title}
                      </h3>
                      {idea.description && (
                        <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">
                          {idea.description}
                        </p>
                      )}
                    </div>

                    {/* Final Score Pill */}
                    <div className="flex sm:flex-col items-baseline sm:items-end justify-between sm:justify-center border-t sm:border-t-0 pt-2 sm:pt-0 border-slate-800/60">
                      <span className="text-[10px] uppercase font-bold tracking-wider text-slate-500">
                        Score
                      </span>
                      <div className="text-lg font-bold text-emerald-400">
                        {idea.final_score !== null && idea.final_score !== undefined
                          ? (idea.final_score * 100).toFixed(1)
                          : "N/A"}
                      </div>
                    </div>
                  </div>
                </Link>
                <div className="flex items-center justify-end gap-2 px-5 pb-4 -mt-2">
                  {rowError[idea.id] && (
                    <span className="mr-auto text-[11px] text-rose-400">{rowError[idea.id]}</span>
                  )}
                  {view === "active" ? (
                    <button
                      onClick={() => act.mutate({ id: idea.id, kind: "archive" })}
                      disabled={act.isPending}
                      className="px-3 py-1 rounded-md text-xs border border-slate-700 text-slate-300 hover:bg-slate-800 disabled:opacity-50"
                    >
                      Archive
                    </button>
                  ) : (
                    <>
                      <button
                        onClick={() => act.mutate({ id: idea.id, kind: "restore" })}
                        disabled={act.isPending}
                        className="px-3 py-1 rounded-md text-xs border border-slate-700 text-slate-300 hover:bg-slate-800 disabled:opacity-50"
                      >
                        Restore
                      </button>
                      <button
                        onClick={() => confirmDelete(idea)}
                        disabled={act.isPending}
                        className="px-3 py-1 rounded-md text-xs border border-rose-800 text-rose-300 hover:bg-rose-950/50 disabled:opacity-50"
                      >
                        Delete permanently
                      </button>
                    </>
                  )}
                </div>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
