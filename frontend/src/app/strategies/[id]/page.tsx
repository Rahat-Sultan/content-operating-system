"use client";

import { use, useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import {
  fetchStrategy,
  updateStrategy,
  runStrategyDiscovery,
  fetchSources,
  StrategyItem,
  UpdateStrategyPayload,
  StrategyDiscoveryResult,
  fetchIdeas,
} from "@/lib/api";

export default function StrategyDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const queryClient = useQueryClient();

  const [isEditing, setIsEditing] = useState(false);
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
    discovery_interval_hours: string;
    enabled: boolean;
    source_ids: string[];
  }>({
    name: "",
    description: "",
    niche: "",
    audience: "",
    topics: "",
    goals: "",
    platforms: "",
    tone: "",
    voice_guidelines: "",
    voice_sample: "",
    discovery_interval_hours: "",
    enabled: true,
    source_ids: [],
  });

  const [discoverySuccessMsg, setDiscoverySuccessMsg] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const {
    data: strategy,
    isLoading: isStrategyLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ["strategy", id],
    queryFn: () => fetchStrategy(id),
  });

  const { data: availableSources } = useQuery({
    queryKey: ["available-sources"],
    queryFn: fetchSources,
  });

  // Populate formData on strategy fetch or edit toggle
  useEffect(() => {
    if (strategy) {
      setFormData({
        name: strategy.name || "",
        description: strategy.description || "",
        niche: strategy.config?.niche || "",
        audience: strategy.config?.audience || "",
        topics: (strategy.config?.topics || []).join(", "),
        goals: (strategy.config?.goals || []).join(", "),
        platforms: (strategy.config?.platforms || ["LinkedIn"]).join(", "),
        tone: strategy.config?.tone || "",
        voice_guidelines: strategy.config?.voice_guidelines || "",
        voice_sample: strategy.config?.voice_sample || "",
        discovery_interval_hours:
          strategy.config?.discovery_interval_hours !== undefined
            ? String(strategy.config.discovery_interval_hours)
            : "",
        enabled: strategy.enabled,
        source_ids: strategy.sources?.map((s) => s.id) || [],
      });
    }
  }, [strategy, isEditing]);

  const updateMutation = useMutation({
    mutationFn: (payload: UpdateStrategyPayload) => updateStrategy(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["strategy", id] });
      queryClient.invalidateQueries({ queryKey: ["strategies"] });
      setIsEditing(false);
      setFormError(null);
    },
    onError: (err: any) => {
      setFormError(err.message || "Failed to update strategy");
    },
  });

  // Ideas this strategy has produced. Same blocks as the Ideas page, linking to the same /ideas/{id}.
  const { data: strategyIdeas } = useQuery({
    queryKey: ["ideas-by-strategy", id],
    queryFn: () => fetchIdeas("ALL", id),
  });

  const discoveryMutation = useMutation({
    mutationFn: () => runStrategyDiscovery(id),
    onSuccess: (result: StrategyDiscoveryResult) => {
      setDiscoverySuccessMsg(
        `Discovery completed: Synced ${result.sources_synced} source(s), fetched ${result.items_fetched} item(s), created ${result.ideas_created_count} idea(s).`
      );
      queryClient.invalidateQueries({ queryKey: ["ideas"] });
      queryClient.invalidateQueries({ queryKey: ["ideas-by-strategy", id] });
    },
    onError: (err: any) => {
      setFormError(err.message || "Failed to run discovery for strategy");
    },
  });

  const handleSourceToggle = (sourceId: string) => {
    setFormData((prev) => {
      const exists = prev.source_ids.includes(sourceId);
      return {
        ...prev,
        source_ids: exists
          ? prev.source_ids.filter((s) => s !== sourceId)
          : [...prev.source_ids, sourceId],
      };
    });
  };

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name.trim()) {
      setFormError("Strategy name is required.");
      return;
    }

    const payload: UpdateStrategyPayload = {
      name: formData.name.trim(),
      description: formData.description.trim() || undefined,
      enabled: formData.enabled,
      config: {
        ...(strategy?.config || {}),
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
        discovery_interval_hours: formData.discovery_interval_hours.trim()
          ? parseFloat(formData.discovery_interval_hours.trim())
          : undefined,
      },
      source_ids: formData.source_ids,
    };

    updateMutation.mutate(payload);
  };

  if (isStrategyLoading) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center">
        <div className="text-slate-500 text-sm">Loading strategy...</div>
      </div>
    );
  }

  if (isError || !strategy) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 p-8">
        <div className="max-w-2xl mx-auto p-4 bg-rose-950/40 border border-rose-800 rounded-lg text-rose-300">
          Error loading strategy: {(error as Error)?.message || "Strategy not found"}
          <div className="mt-4">
            <Link href="/strategies" className="text-xs text-indigo-400 hover:underline">
              ← Back to Strategies
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 pb-16">
      {/* Top Navbar */}
      <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur px-6 py-4 flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center space-x-3">
          <Link
            href="/strategies"
            className="text-xs font-medium text-slate-400 hover:text-slate-200 transition"
          >
            ← Back to Strategies
          </Link>
        </div>
        <div className="flex items-center space-x-6">
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
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-4xl mx-auto px-6 py-8">
        {/* Banner Alert Messages */}
        {discoverySuccessMsg && (
          <div className="mb-6 p-4 rounded-lg bg-emerald-950/50 border border-emerald-800 text-emerald-300 text-sm flex items-center justify-between">
            <div>
              <p className="font-semibold">{discoverySuccessMsg}</p>
              <Link href="/ideas" className="text-xs text-emerald-400 underline mt-1 inline-block">
                View Ideas Feed →
              </Link>
            </div>
            <button
              onClick={() => setDiscoverySuccessMsg(null)}
              className="text-slate-400 hover:text-slate-200 text-xs ml-4"
            >
              ✕
            </button>
          </div>
        )}

        {formError && (
          <div className="mb-6 p-4 rounded-lg bg-rose-950/50 border border-rose-800 text-rose-300 text-sm flex items-center justify-between">
            <p>{formError}</p>
            <button
              onClick={() => setFormError(null)}
              className="text-slate-400 hover:text-slate-200 text-xs ml-4"
            >
              ✕
            </button>
          </div>
        )}

        {/* Strategy Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-800">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-2xl font-bold text-white tracking-tight">
                {strategy.name}
              </h2>
              <span
                className={`text-[11px] font-medium px-2.5 py-0.5 rounded-full border ${
                  strategy.enabled
                    ? "bg-emerald-950/60 text-emerald-300 border-emerald-800"
                    : "bg-slate-800 text-slate-400 border-slate-700"
                }`}
              >
                {strategy.enabled ? "Active" : "Disabled"}
              </span>
            </div>
            {strategy.description && (
              <p className="text-sm text-slate-400 mt-1">{strategy.description}</p>
            )}
          </div>

          <div className="flex items-center gap-3">
            {!isEditing ? (
              <>
                <button
                  onClick={() => setIsEditing(true)}
                  className="px-3.5 py-1.5 rounded-md text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
                >
                  Edit Configuration
                </button>
                <button
                  onClick={() => {
                    setDiscoverySuccessMsg(null);
                    setFormError(null);
                    discoveryMutation.mutate();
                  }}
                  disabled={discoveryMutation.isPending || !strategy.enabled}
                  className="px-4 py-1.5 rounded-md text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/20 transition disabled:opacity-50"
                >
                  {discoveryMutation.isPending ? "Running Discovery..." : "Run Discovery"}
                </button>
              </>
            ) : (
              <button
                onClick={() => setIsEditing(false)}
                className="px-3.5 py-1.5 rounded-md text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
              >
                Cancel Edit
              </button>
            )}
          </div>
        </div>

        {/* Read-Only Configuration Overview */}
        {!isEditing ? (
          <div className="mt-8 space-y-6">
            <section className="bg-slate-900/60 border border-slate-800 rounded-xl p-6">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400 mb-4">
                Strategy Configuration
              </h3>
              <dl className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div>
                  <dt className="text-slate-500">Niche</dt>
                  <dd className="text-slate-200 font-medium text-sm mt-0.5">
                    {strategy.config?.niche || "Not specified"}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Target Audience</dt>
                  <dd className="text-slate-200 font-medium text-sm mt-0.5">
                    {strategy.config?.audience || "Not specified"}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Tone</dt>
                  <dd className="text-slate-300 mt-0.5">
                    {strategy.config?.tone || "Default"}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Target Platforms</dt>
                  <dd className="text-slate-300 mt-0.5">
                    {(strategy.config?.platforms || ["LinkedIn"]).join(", ")}
                  </dd>
                </div>
                <div className="col-span-full">
                  <dt className="text-slate-500">Core Topics</dt>
                  <dd className="mt-1 flex flex-wrap gap-1.5">
                    {(strategy.config?.topics || []).length > 0 ? (
                      strategy.config?.topics?.map((t: string, i: number) => (
                        <span
                          key={i}
                          className="px-2.5 py-1 rounded bg-slate-800 text-slate-200 border border-slate-700 text-xs"
                        >
                          {t}
                        </span>
                      ))
                    ) : (
                      <span className="text-slate-500 italic">No topics configured</span>
                    )}
                  </dd>
                </div>
                <div className="col-span-full">
                  <dt className="text-slate-500">Goals</dt>
                  <dd className="mt-1 flex flex-wrap gap-1.5">
                    {(strategy.config?.goals || []).length > 0 ? (
                      strategy.config?.goals?.map((g: string, i: number) => (
                        <span
                          key={i}
                          className="px-2 py-0.5 rounded bg-slate-800/80 text-slate-300 border border-slate-700/60 text-xs"
                        >
                          {g}
                        </span>
                      ))
                    ) : (
                      <span className="text-slate-500 italic">No explicit goals specified</span>
                    )}
                  </dd>
                </div>
                <div className="col-span-full">
                  <dt className="text-slate-500">Voice / Style Sample</dt>
                  <dd className="mt-1">
                    {strategy.config?.voice_sample ? (
                      <pre className="text-xs bg-slate-950 p-3 rounded-lg border border-slate-800 text-slate-300 font-mono whitespace-pre-wrap max-h-40 overflow-y-auto">
                        {strategy.config.voice_sample}
                      </pre>
                    ) : (
                      <span className="text-slate-500 italic text-xs">No voice sample provided</span>
                    )}
                  </dd>
                </div>
              </dl>
            </section>

            {/* Scheduled Discovery & Last Run (CP-2C.1) */}
            <section className="bg-slate-900/60 border border-slate-800 rounded-xl p-6" data-testid="discovery-schedule-card">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
                  Discovery Schedule & Background Polling
                </h3>
                <span
                  className={`text-[11px] font-medium px-2 py-0.5 rounded-full border ${
                    strategy.schedule_info?.is_scheduled
                      ? "bg-indigo-950/60 text-indigo-300 border-indigo-800"
                      : "bg-slate-800 text-slate-400 border-slate-700"
                  }`}
                  data-testid="schedule-status-badge"
                >
                  {strategy.schedule_info?.is_scheduled
                    ? `Scheduled (Every ${strategy.schedule_info.interval_hours}h)`
                    : "Schedule Disabled"}
                </span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs pt-2 border-t border-slate-800/80">
                <div>
                  <div className="text-slate-500">Configured Interval</div>
                  <div className="text-slate-200 font-medium mt-0.5" data-testid="schedule-interval-value">
                    {strategy.schedule_info?.interval_hours
                      ? `${strategy.schedule_info.interval_hours} hour(s)`
                      : "Manual trigger only (interval not set)"}
                  </div>
                </div>
                <div>
                  <div className="text-slate-500">Last Scheduled Run</div>
                  <div className="text-slate-200 font-medium mt-0.5" data-testid="schedule-last-run-value">
                    {strategy.schedule_info?.last_run ? (
                      <span>
                        {new Date(strategy.schedule_info.last_run.completed_at || "").toLocaleString()}{" "}
                        <span className="text-slate-400 text-[11px]">
                          ({strategy.schedule_info.last_run.items_found || 0} items fetched,{" "}
                          {strategy.schedule_info.last_run.ideas_created || 0} ideas created)
                        </span>
                      </span>
                    ) : (
                      <span className="text-slate-500 italic">No scheduled runs recorded yet</span>
                    )}
                  </div>
                </div>
              </div>
            </section>

            {/* Attached Sources */}
            <section className="bg-slate-900/60 border border-slate-800 rounded-xl p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
                  Attached Sources ({strategy.sources?.length || 0})
                </h3>
              </div>
              <p className="text-xs text-slate-400 mb-4">
                When you click "Run Discovery", Content OS ingests and scores signals strictly from these sources for this strategy.
              </p>
              {strategy.sources && strategy.sources.length > 0 ? (
                <div className="divide-y divide-slate-800 border border-slate-800 rounded-lg overflow-hidden">
                  {strategy.sources.map((src) => (
                    <div
                      key={src.id}
                      className="p-3 bg-slate-950/60 flex items-center justify-between text-xs"
                    >
                      <div>
                        <div className="font-medium text-slate-200">{src.name}</div>
                        {src.url && (
                          <div className="text-slate-500 text-[11px] font-mono mt-0.5">
                            {src.url}
                          </div>
                        )}
                      </div>
                      <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 text-[10px] uppercase">
                        {src.source_type}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-4 border border-dashed border-slate-800 rounded-lg text-center text-slate-500 text-xs">
                  No sources attached to this strategy. Click "Edit Configuration" to attach sources.
                </div>
              )}
            </section>

            {/* Ideas from this strategy (after discovery) */}
            <section data-testid="strategy-ideas" className="bg-slate-900/60 border border-slate-800 rounded-xl p-6 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
                  Ideas from this strategy ({strategyIdeas?.length ?? 0})
                </h3>
                <Link href="/ideas" className="text-xs text-indigo-400 hover:underline">All ideas →</Link>
              </div>
              {strategyIdeas && strategyIdeas.length > 0 ? (
                <div className="grid grid-cols-1 gap-3">
                  {[...strategyIdeas]
                    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
                    .slice(0, 12)
                    .map((idea) => (
                      <Link
                        key={idea.id}
                        href={`/ideas/${idea.id}`}
                        data-testid="strategy-idea-card"
                        className="group block p-4 rounded-xl bg-slate-900/70 border border-slate-800 hover:border-slate-700 hover:bg-slate-900 transition shadow-sm"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="space-y-1 min-w-0">
                            <div className="flex items-center gap-2 text-[11px] text-slate-500">
                              <span className="px-2 py-0.5 rounded border border-slate-700 text-slate-300">{idea.status}</span>
                              <span>{new Date(idea.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</span>
                            </div>
                            <h4 className="text-sm font-semibold text-slate-100 group-hover:text-indigo-400 transition-colors truncate">{idea.title}</h4>
                          </div>
                          <div className="text-right shrink-0">
                            <span className="text-[10px] uppercase font-bold tracking-wider text-slate-500 block">Score</span>
                            <span className="text-base font-bold text-emerald-400">
                              {idea.final_score !== null && idea.final_score !== undefined ? (idea.final_score * 100).toFixed(1) : "N/A"}
                            </span>
                          </div>
                        </div>
                      </Link>
                    ))}
                </div>
              ) : (
                <div className="p-4 border border-dashed border-slate-800 rounded-lg text-center text-slate-500 text-xs">
                  No ideas yet. Run discovery to create ideas from this strategy's sources.
                </div>
              )}
            </section>
          </div>
        ) : (
          /* Edit Form */
          <form onSubmit={handleSave} className="mt-8 space-y-6 text-xs">
            <section className="bg-slate-900/60 border border-slate-800 rounded-xl p-6 space-y-4">
              <h3 className="text-sm font-semibold text-white pb-2 border-b border-slate-800">
                Edit Strategy
              </h3>

              <div>
                <label className="block text-slate-300 font-medium mb-1">
                  Strategy Name *
                </label>
                <input
                  type="text"
                  required
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
                    value={formData.niche}
                    onChange={(e) => setFormData({ ...formData, niche: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-2 text-slate-100 focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Audience</label>
                  <input
                    type="text"
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
                  value={formData.topics}
                  onChange={(e) => setFormData({ ...formData, topics: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-2 text-slate-100 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">
                  Goals (comma-separated)
                </label>
                <input
                  type="text"
                  value={formData.goals}
                  onChange={(e) => setFormData({ ...formData, goals: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-2 text-slate-100 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Tone</label>
                  <input
                    type="text"
                    value={formData.tone}
                    onChange={(e) => setFormData({ ...formData, tone: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-2 text-slate-100 focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Platforms</label>
                  <input
                    type="text"
                    value={formData.platforms}
                    onChange={(e) => setFormData({ ...formData, platforms: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-2 text-slate-100 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">
                  Voice / Style Sample (Optional)
                </label>
                <p className="text-slate-500 text-[11px] mb-1.5">
                  Paste an excerpt of real writing you want the Writer to emulate (tone, sentence rhythm, and vocabulary).
                </p>
                <textarea
                  rows={4}
                  placeholder="Paste an excerpt of how you or your team actually write..."
                  value={formData.voice_sample}
                  onChange={(e) => setFormData({ ...formData, voice_sample: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-2 text-slate-100 focus:outline-none focus:border-indigo-500 font-mono text-xs"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">
                  Scheduled Discovery Interval (Hours)
                </label>
                <p className="text-slate-500 text-[11px] mb-1.5">
                  Interval in hours between automated background discovery runs (e.g. 1, 4, 24). Leave blank to disable automated scheduling.
                </p>
                <input
                  type="number"
                  min="0.1"
                  step="any"
                  placeholder="e.g. 4 (leave blank for manual discovery only)"
                  value={formData.discovery_interval_hours}
                  onChange={(e) =>
                    setFormData({ ...formData, discovery_interval_hours: e.target.value })
                  }
                  className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-2 text-slate-100 focus:outline-none focus:border-indigo-500 font-mono text-xs"
                  data-testid="schedule-interval-input"
                />
              </div>

              {/* Source Attachment Selector */}
              <div>
                <label className="block text-slate-300 font-medium mb-1">
                  Attached Sources (Strategy Isolation)
                </label>
                <p className="text-slate-500 text-[11px] mb-2">
                  Select which sources feed into this strategy. Only these sources will be read during discovery.
                </p>
                <div className="border border-slate-800 rounded-md p-2 bg-slate-950 max-h-48 overflow-y-auto space-y-1">
                  {availableSources && availableSources.length > 0 ? (
                    availableSources.map((source) => (
                      <label
                        key={source.id}
                        className="flex items-center space-x-2 text-slate-300 hover:text-white cursor-pointer py-1.5 px-2 rounded hover:bg-slate-900"
                      >
                        <input
                          type="checkbox"
                          checked={formData.source_ids.includes(source.id)}
                          onChange={() => handleSourceToggle(source.id)}
                          className="rounded border-slate-700 text-indigo-600 focus:ring-indigo-500"
                        />
                        <span className="font-medium text-xs">{source.name}</span>
                        <span className="text-slate-500 text-[10px]">
                          ({source.source_type} - {source.url || "no URL"})
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
                  id="enabled_edit"
                  checked={formData.enabled}
                  onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                  className="rounded border-slate-700 text-indigo-600 focus:ring-indigo-500"
                />
                <label htmlFor="enabled_edit" className="text-slate-300">
                  Enable strategy for discovery
                </label>
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsEditing(false)}
                  className="px-4 py-2 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={updateMutation.isPending}
                  className="px-4 py-2 rounded-md bg-indigo-600 hover:bg-indigo-500 text-white font-medium shadow-md shadow-indigo-600/20 transition disabled:opacity-50"
                >
                  {updateMutation.isPending ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </section>
          </form>
        )}
      </main>
    </div>
  );
}
