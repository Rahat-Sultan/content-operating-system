"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { fetchIdeas, IdeaItem } from "@/lib/api";

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
  const [selectedStatus, setSelectedStatus] = useState("ALL");

  const {
    data: ideas,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["ideas", selectedStatus],
    queryFn: () => fetchIdeas(selectedStatus),
  });

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
        <nav className="flex items-center space-x-4">
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

        {/* Filter Pills */}
        <div className="flex items-center gap-2 overflow-x-auto py-4 scrollbar-none">
          <span className="text-xs uppercase tracking-wider text-slate-500 font-semibold mr-2">
            Status:
          </span>
          {STATUS_FILTERS.map((status) => {
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
              {selectedStatus === "ALL"
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
                <Link
                  key={idea.id}
                  href={`/ideas/${idea.id}`}
                  className="group block p-5 rounded-xl bg-slate-900/70 border border-slate-800 hover:border-slate-700 hover:bg-slate-900 transition shadow-sm"
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
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
