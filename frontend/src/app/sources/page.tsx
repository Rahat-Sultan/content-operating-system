"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { fetchSources, createSource, SourceOption, CreateSourcePayload } from "@/lib/api";

export default function SourcesPage() {
  const queryClient = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const [formData, setFormData] = useState<{
    name: string;
    source_type: string;
    url: string;
    enabled: boolean;
  }>({
    name: "",
    source_type: "rss",
    url: "",
    enabled: true,
  });

  const [formError, setFormError] = useState<string | null>(null);

  const {
    data: sources,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["sources"],
    queryFn: fetchSources,
  });

  const createMutation = useMutation({
    mutationFn: (payload: CreateSourcePayload) => createSource(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sources"] });
      queryClient.invalidateQueries({ queryKey: ["available-sources"] });
      setShowModal(false);
      setFormData({
        name: "",
        source_type: "rss",
        url: "",
        enabled: true,
      });
      setFormError(null);
    },
    onError: (err: any) => {
      setFormError(err.message || "Failed to create source");
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name.trim()) {
      setFormError("Source name is required.");
      return;
    }
    if (!formData.url.trim()) {
      setFormError("Source URL is required.");
      return;
    }

    createMutation.mutate({
      name: formData.name.trim(),
      source_type: formData.source_type,
      url: formData.url.trim(),
      enabled: formData.enabled,
    });
  };

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
            href="/sources"
            className="text-sm font-medium text-indigo-400 hover:text-indigo-300 transition-colors"
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
            className="text-sm font-medium text-slate-400 hover:text-slate-200 transition-colors"
          >
            Ideas
          </Link>
        </nav>
      </header>

      {/* Main Content Area */}
      <main className="max-w-6xl mx-auto px-6 py-8">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-800">
          <div>
            <h2 className="text-2xl font-bold text-white tracking-tight">Signal Sources</h2>
            <p className="text-sm text-slate-400 mt-1">
              Configure external feeds and content channels that feed into discovery strategies.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => refetch()}
              className="px-3.5 py-1.5 rounded-md text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
            >
              Refresh
            </button>
            <button
              onClick={() => setShowModal(true)}
              className="px-4 py-1.5 rounded-md text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/20 transition"
            >
              + Add Source
            </button>
          </div>
        </div>

        {/* Loading / Error States */}
        {isLoading && (
          <div className="py-20 text-center text-slate-500 text-sm">
            Loading sources...
          </div>
        )}

        {isError && (
          <div className="my-6 p-4 rounded-lg bg-rose-950/40 border border-rose-800 text-rose-300 text-sm">
            Failed to load sources: {(error as Error)?.message || "Unknown error"}
          </div>
        )}

        {/* Sources List */}
        {!isLoading && !isError && sources && (
          <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
            {sources.length === 0 ? (
              <div className="col-span-full py-16 text-center text-slate-500 border border-dashed border-slate-800 rounded-xl">
                No signal sources configured yet. Click "+ Add Source" to add one.
              </div>
            ) : (
              sources.map((source: SourceOption) => (
                <div
                  key={source.id}
                  className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-center justify-between">
                      <h3 className="font-semibold text-slate-100">{source.name}</h3>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                          {source.source_type}
                        </span>
                        <span
                          className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${
                            source.enabled
                              ? "bg-emerald-950/60 text-emerald-300 border-emerald-800"
                              : "bg-slate-800 text-slate-400 border-slate-700"
                          }`}
                        >
                          {source.enabled ? "Active" : "Disabled"}
                        </span>
                      </div>
                    </div>
                    {source.url && (
                      <p className="text-xs font-mono text-slate-400 mt-2 truncate bg-slate-950/50 p-2 rounded border border-slate-800/80">
                        {source.url}
                      </p>
                    )}
                  </div>
                  <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-500">
                    <span>ID: {source.id.slice(0, 8)}...</span>
                    <span>Ready for Discovery</span>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </main>

      {/* Add Source Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 overflow-y-auto">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-lg w-full p-6 shadow-2xl my-8">
            <div className="flex items-center justify-between pb-4 border-b border-slate-800">
              <h3 className="text-lg font-semibold text-white">Add Signal Source</h3>
              <button
                onClick={() => setShowModal(false)}
                className="text-slate-400 hover:text-slate-200 text-sm"
              >
                ✕
              </button>
            </div>

            {formError && (
              <div className="mt-4 p-3 bg-rose-950/50 border border-rose-800 rounded text-rose-300 text-xs">
                {formError}
              </div>
            )}

            <form onSubmit={handleSubmit} className="mt-4 space-y-4 text-xs">
              <div>
                <label className="block text-slate-300 font-medium mb-1">
                  Source Name *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. AWS Architecture Blog RSS"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-2 text-slate-100 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">
                  Source Type
                </label>
                <select
                  value={formData.source_type}
                  onChange={(e) => setFormData({ ...formData, source_type: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-2 text-slate-100 focus:outline-none focus:border-indigo-500"
                >
                  <option value="rss">RSS Feed (Fully Supported)</option>
                  <option value="website">Website (Web Scraping)</option>
                  <option value="youtube">YouTube Channel</option>
                  <option value="reddit">Reddit Subreddit</option>
                </select>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">
                  Feed / Resource URL *
                </label>
                <input
                  type="url"
                  required
                  placeholder="https://aws.amazon.com/blogs/architecture/feed/"
                  value={formData.url}
                  onChange={(e) => setFormData({ ...formData, url: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-2 text-slate-100 focus:outline-none focus:border-indigo-500 font-mono text-[11px]"
                />
              </div>

              <div className="flex items-center space-x-2 pt-2">
                <input
                  type="checkbox"
                  id="source_enabled"
                  checked={formData.enabled}
                  onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                  className="rounded border-slate-700 text-indigo-600 focus:ring-indigo-500"
                />
                <label htmlFor="source_enabled" className="text-slate-300">
                  Enable source for discovery ingestion
                </label>
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="px-4 py-2 rounded-md bg-indigo-600 hover:bg-indigo-500 text-white font-medium shadow-md shadow-indigo-600/20 transition disabled:opacity-50"
                >
                  {createMutation.isPending ? "Adding Source..." : "Add Source"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
