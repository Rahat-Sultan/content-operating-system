"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { fetchSources, createSource, updateSource, fetchSourceSuggestions, SourceOption, CreateSourcePayload } from "@/lib/api";
import { Greeting } from "@/components/Greeting";

function SourceName({ source }: { source: SourceOption }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(source.name);
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () => updateSource(source.id, { name }),
    onSuccess: () => {
      setError(null);
      setEditing(false);
      queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
    onError: (e: any) => setError(e.message),
  });

  if (editing) {
    return (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          if (!name.trim()) {
            setError("Name can't be empty.");
            return;
          }
          save.mutate();
        }}
        className="flex items-center gap-1.5 min-w-0 flex-1"
        data-testid={`source-name-form-${source.id}`}
      >
        <input
          className="cos-input py-1 text-sm font-semibold"
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoFocus
          maxLength={120}
        />
        <button type="submit" className="cos-btn-primary whitespace-nowrap px-2 py-1 text-xs" disabled={save.isPending}>
          {save.isPending ? "…" : "Save"}
        </button>
        <button
          type="button"
          className="cos-btn whitespace-nowrap px-2 py-1 text-xs"
          onClick={() => {
            setName(source.name);
            setError(null);
            setEditing(false);
          }}
        >
          Cancel
        </button>
        {error && <p className="text-[11px] text-bad">{error}</p>}
      </form>
    );
  }

  return (
    <button
      type="button"
      onClick={() => setEditing(true)}
      className="group flex min-w-0 flex-1 items-center gap-1.5 text-left"
      title="Edit name"
    >
      <h3 className="font-semibold text-strong truncate">{source.name}</h3>
      <svg
        width="13"
        height="13"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        className="shrink-0 text-faint opacity-0 group-hover:opacity-100"
      >
        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
        <path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4Z" />
      </svg>
    </button>
  );
}

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

  const { data: suggestions } = useQuery({
    queryKey: ["source-suggestions"],
    queryFn: fetchSourceSuggestions,
  });

  const addSuggestion = useMutation({
    mutationFn: (s: { name: string; url: string; topic: string }) =>
      createSource({ name: s.name, url: s.url, source_type: "rss", config: { topic: s.topic } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sources"] });
      queryClient.invalidateQueries({ queryKey: ["source-suggestions"] });
      queryClient.invalidateQueries({ queryKey: ["available-sources"] });
    },
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
    if (!formData.url.trim()) {
      setFormError("Source URL is required.");
      return;
    }

    createMutation.mutate({
      // Blank name: the source is named after its link.
      name: formData.name.trim() || undefined,
      source_type: formData.source_type,
      url: formData.url.trim(),
      enabled: formData.enabled,
    });
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
            <Greeting text={(name) => `Hello ${name}, here are your sources.`} />
            <h2 className="text-2xl font-bold text-strong tracking-tight">Signal Sources</h2>
            <p className="text-sm text-muted mt-1">
              Configure external feeds and content channels that feed into discovery strategies.
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
              + Add Source
            </button>
          </div>
        </div>

        {/* Loading / Error States */}
        {isLoading && (
          <div className="py-20 text-center text-subtle text-sm">
            Loading sources...
          </div>
        )}

        {isError && (
          <div className="my-6 p-4 rounded-lg bg-rose-950/40 border border-rose-800 text-rose-300 text-sm">
            Failed to load sources: {(error as Error)?.message || "Unknown error"}
          </div>
        )}

        {/* Suggested feeds this account does not have yet */}
        {suggestions && suggestions.length > 0 && (
          <section data-testid="source-suggestions" className="mt-6 space-y-3">
            <div>
              <h3 className="cos-label">Suggested sources</h3>
              <p className="text-xs text-muted mt-1">Feeds that fit this niche. Add the ones you want to search.</p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {suggestions.map((s) => (
                <div key={s.url} className="cos-card p-4 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-body-strong truncate">{s.name}</p>
                    <p className="text-[11px] text-subtle">{s.topic}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => addSuggestion.mutate(s)}
                    disabled={addSuggestion.isPending}
                    className="cos-btn shrink-0"
                  >
                    Add
                  </button>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Sources List */}
        {!isLoading && !isError && sources && (
          <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
            {sources.length === 0 ? (
              <div className="col-span-full py-16 text-center text-subtle border border-dashed border-line rounded-xl">
                No signal sources configured yet. Click "+ Add Source" to add one.
              </div>
            ) : (
              sources.map((source: SourceOption) => (
                <div
                  key={source.id}
                  className="p-5 rounded-xl bg-panel/60 border border-line flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-center justify-between gap-2">
                      <SourceName source={source} />
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-raised text-body border border-line-strong">
                          {source.source_type}
                        </span>
                        <span
                          className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${
                            source.enabled
                              ? "bg-emerald-950/60 text-emerald-300 border-emerald-800"
                              : "bg-raised text-muted border-line-strong"
                          }`}
                        >
                          {source.enabled ? "Active" : "Disabled"}
                        </span>
                      </div>
                    </div>
                    {source.url && (
                      <p className="text-xs font-mono text-muted mt-2 truncate bg-canvas/50 p-2 rounded border border-line/80">
                        {source.url}
                      </p>
                    )}
                  </div>
                  <div className="mt-4 pt-3 border-t border-line/80 flex items-center justify-between text-xs text-subtle">
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
          <div className="bg-panel border border-line rounded-xl max-w-lg w-full p-6 shadow-2xl my-8">
            <div className="flex items-center justify-between pb-4 border-b border-line">
              <h3 className="text-lg font-semibold text-strong">Add Signal Source</h3>
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
                  Source Name <span className="text-subtle font-normal">(optional)</span>
                </label>
                <input
                  type="text"
                  placeholder="Leave blank to use the link"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="w-full bg-canvas border border-line rounded-md px-3 py-2 text-strong focus:outline-none focus:border-accent"
                />
              </div>

              <div>
                <label className="block text-body font-medium mb-1">
                  Source Type
                </label>
                <select
                  value={formData.source_type}
                  onChange={(e) => setFormData({ ...formData, source_type: e.target.value })}
                  className="w-full bg-canvas border border-line rounded-md px-3 py-2 text-strong focus:outline-none focus:border-accent"
                >
                  <option value="rss">RSS Feed (Fully Supported)</option>
                  <option value="website">Website (Web Scraping)</option>
                  <option value="youtube">YouTube Channel</option>
                  <option value="reddit">Reddit Subreddit</option>
                </select>
              </div>

              <div>
                <label className="block text-body font-medium mb-1">
                  Feed / Resource URL *
                </label>
                <input
                  type="url"
                  required
                  placeholder="https://aws.amazon.com/blogs/architecture/feed/"
                  value={formData.url}
                  onChange={(e) => setFormData({ ...formData, url: e.target.value })}
                  className="w-full bg-canvas border border-line rounded-md px-3 py-2 text-strong focus:outline-none focus:border-accent font-mono text-[11px]"
                />
              </div>

              <div className="flex items-center space-x-2 pt-2">
                <input
                  type="checkbox"
                  id="source_enabled"
                  checked={formData.enabled}
                  onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                  className="rounded border-line-strong text-accent focus:ring-indigo-500"
                />
                <label htmlFor="source_enabled" className="text-body">
                  Enable source for discovery ingestion
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
