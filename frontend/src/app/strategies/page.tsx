"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import {
  fetchStrategies,
  archiveStrategy,
  restoreStrategy,
  deleteStrategy,
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
    voice_sample: string;
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
    voice_sample: "",
    enabled: true,
    source_ids: [],
  });

  const [formError, setFormError] = useState<string | null>(null);

  const [view, setView] = useState<"active" | "archive">("active");
  const {
    data: strategies,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["strategies", view],
    queryFn: () => fetchStrategies(false, view === "archive"),
  });

  const [rowError, setRowError] = useState<Record<string, string>>({});
  const act = useMutation({
    mutationFn: async ({ id, kind }: { id: string; kind: "archive" | "restore" | "delete" }) => {
      if (kind === "archive") return archiveStrategy(id);
      if (kind === "restore") return restoreStrategy(id);
      return deleteStrategy(id);
    },
    onSuccess: (_, v) => {
      setRowError((e) => ({ ...e, [v.id]: "" }));
      queryClient.invalidateQueries({ queryKey: ["strategies"] });
      queryClient.invalidateQueries({ queryKey: ["ideas"] });
    },
    onError: (err: any, v) => {
      setRowError((e) => ({ ...e, [v.id]: err?.message || "Action failed." }));
    },
  });

  function confirmDelete(strategy: StrategyItem) {
    if (window.confirm(`Delete the strategy "${strategy.name}" and its unrun ideas permanently? This cannot be undone.`)) {
      act.mutate({ id: strategy.id, kind: "delete" });
    }
  }

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
        voice_sample: "",
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
        voice_sample: formData.voice_sample.trim() || undefined,
      },
      source_ids: formData.source_ids,
    };

    createMutation.mutate(payload);
  };

  return (
    <div className="min-h-screen bg-canvas text-strong">
      {/* Top Navbar */}
      <header className="border-b border-line bg-panel/50 backdrop-blur px-4 sm:px-6 py-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center space-x-3">
          <img src="/logo.svg" alt="Content OS" className="h-8 w-8 shrink-0" />
          <div>
            <h1 className="text-lg font-semibold text-strong tracking-tight">Content OS</h1>
            <p className="text-xs text-muted">Autonomous Content Intelligence Engine</p>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-line">
          <div>
            <h2 className="text-2xl font-bold text-strong tracking-tight">Content Strategies</h2>
            <p className="text-sm text-muted mt-1">
              Define niches, target audiences, and attached sources to govern discovery and production.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => refetch()}
              className="px-3.5 py-1.5 rounded-md text-xs font-medium bg-raised hover:bg-raised-strong text-body-strong border border-line-strong transition"
            >
              Refresh
            </button>
            <button
              onClick={() => setShowModal(true)}
              className="px-4 py-1.5 rounded-md text-xs font-semibold bg-accent hover:bg-accent-hover text-strong shadow-md shadow-accent/20 transition"
            >
              + New Strategy
            </button>
          </div>
        </div>

        <div role="tablist" className="flex items-center gap-2 mt-5">
          {(["active", "archive"] as const).map((v) => (
            <button
              key={v}
              role="tab"
              aria-selected={view === v}
              onClick={() => setView(v)}
              data-testid={`strategies-view-${v}`}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition-colors ${
                view === v
                  ? "bg-accent border-accent text-strong"
                  : "bg-panel border-line text-muted hover:text-body-strong"
              }`}
            >
              {v === "active" ? "Active" : "Rejected (archive)"}
            </button>
          ))}
          {view === "archive" && (
            <span className="text-[11px] text-subtle ml-2">
              Archived strategies are kept, not deleted. Restore one to bring it back.
            </span>
          )}
        </div>

        {/* Loading / Error States */}
        {isLoading && (
          <div className="py-20 text-center text-subtle text-sm">
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
              <div className="col-span-full py-16 text-center text-subtle border border-dashed border-line rounded-xl">
                No strategies configured yet. Click "+ New Strategy" to create one.
              </div>
            ) : (
              strategies.map((strategy: StrategyItem) => {
                const niche = strategy.config?.niche || "General";
                const audience = strategy.config?.audience || "Not specified";
                const topics = strategy.config?.topics || [];
                const sourcesCount = strategy.sources?.length || 0;

                return (
                  <div key={strategy.id} className="rounded-xl bg-panel/60 border border-line hover:border-accent/50 transition-all duration-200">
                  <Link
                    href={`/strategies/${strategy.id}`}
                    className="group block p-5"
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="font-semibold text-strong group-hover:text-accent-text transition-colors">
                            {strategy.name}
                          </h3>
                          <span
                            className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${
                              strategy.enabled
                                ? "bg-emerald-950/60 text-emerald-300 border-emerald-800"
                                : "bg-raised text-muted border-line-strong"
                            }`}
                          >
                            {strategy.enabled ? "Active" : "Disabled"}
                          </span>
                        </div>
                        {strategy.description && (
                          <p className="text-xs text-muted mt-1 line-clamp-2">
                            {strategy.description}
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="mt-4 pt-3 border-t border-line/80 grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                      <div>
                        <span className="text-subtle">Niche:</span>{" "}
                        <span className="text-body font-medium">{niche}</span>
                      </div>
                      <div>
                        <span className="text-subtle">Sources:</span>{" "}
                        <span className="text-body font-medium">
                          {sourcesCount} attached
                        </span>
                      </div>
                      <div className="col-span-2">
                        <span className="text-subtle">Audience:</span>{" "}
                        <span className="text-body">{audience}</span>
                      </div>
                    </div>

                    {topics.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1">
                        {topics.slice(0, 3).map((topic, i) => (
                          <span
                            key={i}
                            className="text-[10px] px-2 py-0.5 rounded bg-raised/80 text-body border border-line-strong/60"
                          >
                            {topic}
                          </span>
                        ))}
                        {topics.length > 3 && (
                          <span className="text-[10px] px-1.5 py-0.5 text-subtle">
                            +{topics.length - 3} more
                          </span>
                        )}
                      </div>
                    )}
                  </Link>
                  <div className="flex items-center justify-end gap-2 px-5 pb-4 -mt-2">
                    {rowError[strategy.id] && (
                      <span className="mr-auto text-[11px] text-rose-400">{rowError[strategy.id]}</span>
                    )}
                    {view === "active" ? (
                      <>
                        <button
                          onClick={() => act.mutate({ id: strategy.id, kind: "archive" })}
                          disabled={act.isPending}
                          className="px-3 py-1 rounded-md text-xs border border-line-strong text-body hover:bg-raised disabled:opacity-50"
                        >
                          Archive
                        </button>
                        <button
                          onClick={() => confirmDelete(strategy)}
                          disabled={act.isPending}
                          className="px-3 py-1 rounded-md text-xs border border-rose-800 text-rose-300 hover:bg-rose-950/50 disabled:opacity-50"
                        >
                          Delete
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          onClick={() => act.mutate({ id: strategy.id, kind: "restore" })}
                          disabled={act.isPending}
                          className="px-3 py-1 rounded-md text-xs border border-line-strong text-body hover:bg-raised disabled:opacity-50"
                        >
                          Restore
                        </button>
                        <button
                          onClick={() => confirmDelete(strategy)}
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
              })
            )}
          </div>
        )}
      </main>

      {/* Create Strategy Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 overflow-y-auto">
          <div className="bg-panel border border-line rounded-xl max-w-xl w-full p-6 shadow-2xl my-8">
            <div className="flex items-center justify-between pb-4 border-b border-line">
              <h3 className="text-lg font-semibold text-strong">Create Content Strategy</h3>
              <button
                onClick={() => setShowModal(false)}
                className="text-muted hover:text-body-strong text-sm"
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
                <label className="block text-body font-medium mb-1">
                  Strategy Name *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Cloud Native Infrastructure"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="w-full bg-canvas border border-line rounded-md px-3 py-2 text-strong focus:outline-none focus:border-accent"
                />
              </div>

              <div>
                <label className="block text-body font-medium mb-1">
                  Description
                </label>
                <textarea
                  rows={2}
                  placeholder="High-level purpose of this content strategy"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  className="w-full bg-canvas border border-line rounded-md px-3 py-2 text-strong focus:outline-none focus:border-accent"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-body font-medium mb-1">Niche</label>
                  <input
                    type="text"
                    placeholder="e.g. Kubernetes, AI Agents"
                    value={formData.niche}
                    onChange={(e) => setFormData({ ...formData, niche: e.target.value })}
                    className="w-full bg-canvas border border-line rounded-md px-3 py-2 text-strong focus:outline-none focus:border-accent"
                  />
                </div>
                <div>
                  <label className="block text-body font-medium mb-1">Audience</label>
                  <input
                    type="text"
                    placeholder="e.g. Senior Staff Engineers"
                    value={formData.audience}
                    onChange={(e) => setFormData({ ...formData, audience: e.target.value })}
                    className="w-full bg-canvas border border-line rounded-md px-3 py-2 text-strong focus:outline-none focus:border-accent"
                  />
                </div>
              </div>

              <div>
                <label className="block text-body font-medium mb-1">
                  Topics (comma-separated)
                </label>
                <input
                  type="text"
                  placeholder="e.g. eBPF, Distributed Systems, Reliability"
                  value={formData.topics}
                  onChange={(e) => setFormData({ ...formData, topics: e.target.value })}
                  className="w-full bg-canvas border border-line rounded-md px-3 py-2 text-strong focus:outline-none focus:border-accent"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-body font-medium mb-1">Tone</label>
                  <input
                    type="text"
                    placeholder="e.g. Authoritative, rigorous"
                    value={formData.tone}
                    onChange={(e) => setFormData({ ...formData, tone: e.target.value })}
                    className="w-full bg-canvas border border-line rounded-md px-3 py-2 text-strong focus:outline-none focus:border-accent"
                  />
                </div>
                <div>
                  <label className="block text-body font-medium mb-1">Platforms</label>
                  <input
                    type="text"
                    placeholder="e.g. LinkedIn, Twitter"
                    value={formData.platforms}
                    onChange={(e) => setFormData({ ...formData, platforms: e.target.value })}
                    className="w-full bg-canvas border border-line rounded-md px-3 py-2 text-strong focus:outline-none focus:border-accent"
                  />
                </div>
              </div>

              <div>
                <label className="block text-body font-medium mb-1">
                  Voice / Style Sample (Optional)
                </label>
                <p className="text-subtle text-[11px] mb-1.5">
                  Paste an excerpt of real writing you want the Writer to emulate (tone, sentence rhythm, and vocabulary).
                </p>
                <textarea
                  rows={4}
                  placeholder="Paste an excerpt of how you or your team actually write..."
                  value={formData.voice_sample}
                  onChange={(e) => setFormData({ ...formData, voice_sample: e.target.value })}
                  className="w-full bg-canvas border border-line rounded-md px-3 py-2 text-strong focus:outline-none focus:border-accent font-mono text-xs"
                />
              </div>

              {/* Attach Sources */}
              <div>
                <label className="block text-body font-medium mb-1">
                  Attach Sources (for Discovery)
                </label>
                <div className="border border-line rounded-md p-2 bg-canvas max-h-32 overflow-y-auto space-y-1">
                  {availableSources && availableSources.length > 0 ? (
                    availableSources.map((source) => (
                      <label
                        key={source.id}
                        className="flex items-center space-x-2 text-body hover:text-strong cursor-pointer py-1 px-1 rounded hover:bg-panel"
                      >
                        <input
                          type="checkbox"
                          checked={formData.source_ids.includes(source.id)}
                          onChange={() => handleSourceToggle(source.id)}
                          className="rounded border-line-strong text-accent focus:ring-indigo-500"
                        />
                        <span className="font-medium">{source.name}</span>
                        <span className="text-subtle text-[10px]">
                          ({source.source_type})
                        </span>
                      </label>
                    ))
                  ) : (
                    <div className="text-subtle text-center py-2">
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
                  className="rounded border-line-strong text-accent focus:ring-indigo-500"
                />
                <label htmlFor="enabled" className="text-body">
                  Enable strategy for discovery
                </label>
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-line">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 rounded-md bg-raised hover:bg-raised-strong text-body font-medium transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="px-4 py-2 rounded-md bg-accent hover:bg-accent-hover text-strong font-medium shadow-md shadow-accent/20 transition disabled:opacity-50"
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
