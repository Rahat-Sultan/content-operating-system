"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import {
  fetchStrategies,
  createStrategy,
  fetchSources,
  StrategyItem,
  CreateStrategyPayload,
} from "@/lib/api";

export default function StrategiesPage() {
  const queryClient = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const [formData, setFormData] = useState<{
    name: string;
    description: string;
    niche: string;
    audience: string;
    topics: string;
    goals: string;
    platforms: string;
    tone: string;
    voice_guidelines: string;
    enabled: boolean;
    source_ids: string[];
  }>({
    name: "",
    description: "",
    niche: "",
    audience: "",
    topics: "",
    goals: "",
    platforms: "LinkedIn",
    tone: "Authoritative and educational",
    voice_guidelines: "",
    enabled: true,
    source_ids: [],
  });

  const [formError, setFormError] = useState<string | null>(null);

  const {
    data: strategies,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["strategies"],
    queryFn: () => fetchStrategies(false),
  });

  const { data: availableSources } = useQuery({
    queryKey: ["available-sources"],
    queryFn: fetchSources,
  });

  const createMutation = useMutation({
    mutationFn: (payload: CreateStrategyPayload) => createStrategy(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["strategies"] });
      setShowModal(false);
      setFormData({
        name: "",
        description: "",
        niche: "",
        audience: "",
        topics: "",
        goals: "",
        platforms: "LinkedIn",
        tone: "Authoritative and educational",
        voice_guidelines: "",
        enabled: true,
        source_ids: [],
      });
      setFormError(null);
    },
    onError: (err: any) => {
      setFormError(err.message || "Failed to create strategy");
    },
  });

  const handleSourceToggle = (sourceId: string) => {
    setFormData((prev) => {
      const exists = prev.source_ids.includes(sourceId);
      return {
        ...prev,
        source_ids: exists
          ? prev.source_ids.filter((id) => id !== sourceId)
          : [...prev.source_ids, sourceId],
      };
    });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name.trim()) {
      setFormError("Strategy name is required.");
      return;
    }

    const payload: CreateStrategyPayload = {
      name: formData.name.trim(),
      description: formData.description.trim() || undefined,
      enabled: formData.enabled,
      config: {
        niche: formData.niche.trim() || undefined,
        audience: formData.audience.trim() || undefined,
        topics: formData.topics
          ? formData.topics.split(",").map((s) => s.trim()).filter(Boolean)
          : [],
        goals: formData.goals
          ? formData.goals.split(",").map((s) => s.trim()).filter(Boolean)
          : [],
        platforms: formData.platforms
          ? formData.platforms.split(",").map((s) => s.trim()).filter(Boolean)
          : ["LinkedIn"],
        tone: formData.tone.trim() || undefined,
        voice_guidelines: formData.voice_guidelines.trim() || undefined,
      },
      source_ids: formData.source_ids,
    };

    createMutation.mutate(payload);
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
            className="text-sm font-medium text-slate-400 hover:text-slate-200 transition-colors"
          >
            Sources
          </Link>
          <Link
            href="/strategies"
            className="text-sm font-medium text-indigo-400 hover:text-indigo-300 transition-colors"
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
            <h2 className="text-2xl font-bold text-white tracking-tight">Content Strategies</h2>
            <p className="text-sm text-slate-400 mt-1">
              Define niches, target audiences, and attached sources to govern discovery and production.
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
              + New Strategy
            </button>
          </div>
        </div>

        {/* Loading / Error States */}
        {isLoading && (
          <div className="py-20 text-center text-slate-500 text-sm">
            Loading strategies...
          </div>
        )}

        {isError && (
          <div className="my-6 p-4 rounded-lg bg-rose-950/40 border border-rose-800 text-rose-300 text-sm">
            Failed to load strategies: {(error as Error)?.message || "Unknown error"}
          </div>
        )}

        {/* Strategy List */}
        {!isLoading && !isError && strategies && (
          <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
            {strategies.length === 0 ? (
              <div className="col-span-full py-16 text-center text-slate-500 border border-dashed border-slate-800 rounded-xl">
                No strategies configured yet. Click "+ New Strategy" to create one.
              </div>
            ) : (
              strategies.map((strategy: StrategyItem) => {
                const niche = strategy.config?.niche || "General";
                const audience = strategy.config?.audience || "Not specified";
                const topics = strategy.config?.topics || [];
                const sourcesCount = strategy.sources?.length || 0;

                return (
                  <Link
                    key={strategy.id}
                    href={`/strategies/${strategy.id}`}
                    className="group block p-5 rounded-xl bg-slate-900/60 border border-slate-800 hover:border-indigo-500/50 hover:bg-slate-900 transition-all duration-200"
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="font-semibold text-slate-100 group-hover:text-indigo-400 transition-colors">
                            {strategy.name}
                          </h3>
                          <span
                            className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${
                              strategy.enabled
                                ? "bg-emerald-950/60 text-emerald-300 border-emerald-800"
                                : "bg-slate-800 text-slate-400 border-slate-700"
                            }`}
                          >
                            {strategy.enabled ? "Active" : "Disabled"}
                          </span>
                        </div>
                        {strategy.description && (
                          <p className="text-xs text-slate-400 mt-1 line-clamp-2">
                            {strategy.description}
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="mt-4 pt-3 border-t border-slate-800/80 grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <span className="text-slate-500">Niche:</span>{" "}
                        <span className="text-slate-300 font-medium">{niche}</span>
                      </div>
                      <div>
                        <span className="text-slate-500">Sources:</span>{" "}
                        <span className="text-slate-300 font-medium">
                          {sourcesCount} attached
                        </span>
                      </div>
                      <div className="col-span-2">
                        <span className="text-slate-500">Audience:</span>{" "}
                        <span className="text-slate-300">{audience}</span>
                      </div>
                    </div>

                    {topics.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1">
                        {topics.slice(0, 3).map((topic, i) => (
                          <span
                            key={i}
                            className="text-[10px] px-2 py-0.5 rounded bg-slate-800/80 text-slate-300 border border-slate-700/60"
                          >
                            {topic}
                          </span>
                        ))}
                        {topics.length > 3 && (
                          <span className="text-[10px] px-1.5 py-0.5 text-slate-500">
                            +{topics.length - 3} more
                          </span>
                        )}
                      </div>
                    )}
                  </Link>
                );
              })
            )}
          </div>
        )}
      </main>

      {/* Create Strategy Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 overflow-y-auto">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-xl w-full p-6 shadow-2xl my-8">
            <div className="flex items-center justify-between pb-4 border-b border-slate-800">
              <h3 className="text-lg font-semibold text-white">Create Content Strategy</h3>
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
                  Strategy Name *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Cloud Native Infrastructure"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-2 text-slate-100 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">
                  Description
                </label>
                <textarea
                  rows={2}
                  placeholder="High-level purpose of this content strategy"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-2 text-slate-100 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Niche</label>
                  <input
                    type="text"
                    placeholder="e.g. Kubernetes, AI Agents"
                    value={formData.niche}
                    onChange={(e) => setFormData({ ...formData, niche: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-2 text-slate-100 focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Audience</label>
                  <input
                    type="text"
                    placeholder="e.g. Senior Staff Engineers"
                    value={formData.audience}
                    onChange={(e) => setFormData({ ...formData, audience: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-2 text-slate-100 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">
                  Topics (comma-separated)
                </label>
                <input
                  type="text"
                  placeholder="e.g. eBPF, Distributed Systems, Reliability"
                  value={formData.topics}
                  onChange={(e) => setFormData({ ...formData, topics: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-2 text-slate-100 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Tone</label>
                  <input
                    type="text"
                    placeholder="e.g. Authoritative, rigorous"
                    value={formData.tone}
                    onChange={(e) => setFormData({ ...formData, tone: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-2 text-slate-100 focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Platforms</label>
                  <input
                    type="text"
                    placeholder="e.g. LinkedIn, Twitter"
                    value={formData.platforms}
                    onChange={(e) => setFormData({ ...formData, platforms: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-2 text-slate-100 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              {/* Attach Sources */}
              <div>
                <label className="block text-slate-300 font-medium mb-1">
                  Attach Sources (for Discovery)
                </label>
                <div className="border border-slate-800 rounded-md p-2 bg-slate-950 max-h-32 overflow-y-auto space-y-1">
                  {availableSources && availableSources.length > 0 ? (
                    availableSources.map((source) => (
                      <label
                        key={source.id}
                        className="flex items-center space-x-2 text-slate-300 hover:text-white cursor-pointer py-1 px-1 rounded hover:bg-slate-900"
                      >
                        <input
                          type="checkbox"
                          checked={formData.source_ids.includes(source.id)}
                          onChange={() => handleSourceToggle(source.id)}
                          className="rounded border-slate-700 text-indigo-600 focus:ring-indigo-500"
                        />
                        <span className="font-medium">{source.name}</span>
                        <span className="text-slate-500 text-[10px]">
                          ({source.source_type})
                        </span>
                      </label>
                    ))
                  ) : (
                    <div className="text-slate-500 text-center py-2">
                      No sources available
                    </div>
                  )}
                </div>
              </div>

              <div className="flex items-center space-x-2 pt-2">
                <input
                  type="checkbox"
                  id="enabled"
                  checked={formData.enabled}
                  onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                  className="rounded border-slate-700 text-indigo-600 focus:ring-indigo-500"
                />
                <label htmlFor="enabled" className="text-slate-300">
                  Enable strategy for discovery
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
                  {createMutation.isPending ? "Creating..." : "Create Strategy"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
