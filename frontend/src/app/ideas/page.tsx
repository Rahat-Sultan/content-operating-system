"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { PlatformBadge } from "@/components/PlatformBadge";
import { Greeting } from "@/components/Greeting";
import { archiveIdea, deleteIdea, fetchIdeas, IdeaItem, restoreIdea, selectIdea } from "@/lib/api";

// Board columns: one per stage. Archived (REJECTED) ideas live in their own tab.
const STAGES: { status: string; label: string }[] = [
  { status: "NEW", label: "New" },
  { status: "SELECTED", label: "Selected" },
  { status: "IN_PROGRESS", label: "In progress" },
  { status: "PUBLISHED", label: "Published" },
];

function scoreOf(i: IdeaItem) {
  return i.final_score === null || i.final_score === undefined ? null : i.final_score * 100;
}

export default function IdeasPage() {
  // The view lives in the URL, so the menu and the tabs always agree.
  const router = useRouter();
  const searchParams = useSearchParams();
  const view: "board" | "archive" = searchParams.get("view") === "archive" ? "archive" : "board";
  const [rowError, setRowError] = useState<Record<string, string>>({});
  // On a phone, the board shows one stage at a time instead of stacking all four.
  const [mobileStage, setMobileStage] = useState<string>(STAGES[0].status);
  const queryClient = useQueryClient();

  const { data: all, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["ideas", "board"],
    queryFn: () => fetchIdeas("ALL", undefined, 500),
  });

  const archived = (all ?? []).filter((i) => i.status === "REJECTED");
  const active = (all ?? []).filter((i) => i.status !== "REJECTED");
  const shown = view === "archive" ? archived : active;

  const act = useMutation({
    mutationFn: async ({ id, kind }: { id: string; kind: "select" | "archive" | "restore" | "delete" }) => {
      if (kind === "select") return selectIdea(id);
      if (kind === "archive") return archiveIdea(id);
      if (kind === "restore") return restoreIdea(id);
      // Stop the running work first. If a step is still finishing, wait and try again.
      for (let attempt = 0; attempt < 60; attempt++) {
        const result = await deleteIdea(id, true);
        if (result.status === "deleted") return result;
        setRowError((e) => ({ ...e, [id]: "Stopping the running step… the idea is deleted when it stops." }));
        await new Promise((resolve) => setTimeout(resolve, 5000));
      }
      throw new Error("The running step did not stop in time. Try again in a minute.");
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
    const message =
      `Delete "${idea.title}" permanently?\n\n` +
      `If it has a workflow run, that run is stopped first. Its drafts, approvals and publication records are deleted too. ` +
      `Published LinkedIn posts stay on LinkedIn. This cannot be undone.`;
    if (window.confirm(message)) {
      act.mutate({ id: idea.id, kind: "delete" });
    }
  }

  function Card({ idea }: { idea: IdeaItem }) {
    const score = scoreOf(idea);
    return (
      <div className="rounded-lg bg-canvas border border-line hover:border-zinc-600 p-3 space-y-2">
        <Link href={`/ideas/${idea.id}`} className="block group">
          <h4 className="text-[13px] font-semibold leading-snug text-strong group-hover:text-violet-300 transition-colors">
            {idea.title}
          </h4>
          <div className="mt-2 h-1.5 rounded bg-raised overflow-hidden">
            <div
              className="h-full rounded bg-gradient-to-r from-violet-400 to-sky-400"
              style={{ width: `${Math.min(100, Math.max(0, score ?? 0))}%` }}
            />
          </div>
        </Link>
        <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
          {idea.strategy_name && (
            <span data-testid="idea-strategy" className="px-1.5 py-0.5 rounded bg-violet-950 text-violet-300">
              {idea.strategy_name}
            </span>
          )}
          {(idea.platforms ?? []).map((p) => (
            <PlatformBadge key={p} platform={p} />
          ))}
          <span className="ml-auto font-bold text-body-strong">{score === null ? "N/A" : score.toFixed(1)}</span>
        </div>
        <div className="flex items-center justify-end gap-2">
          {rowError[idea.id] && <span className="mr-auto text-[11px] text-rose-400">{rowError[idea.id]}</span>}
          {view === "board" ? (
            <>
            {idea.status === "NEW" && (
              <button
                onClick={() => act.mutate({ id: idea.id, kind: "select" })}
                disabled={act.isPending}
                className="px-2 py-0.5 rounded text-[11px] bg-accent text-strong hover:bg-accent-hover disabled:opacity-50"
              >
                Select
              </button>
            )}
            <button
              onClick={() => act.mutate({ id: idea.id, kind: "archive" })}
              disabled={act.isPending}
              className="px-2 py-0.5 rounded text-[11px] border border-line-strong text-muted hover:bg-raised disabled:opacity-50"
            >
              Archive
            </button>
            <button
              onClick={() => confirmDelete(idea)}
              disabled={act.isPending}
              className="px-2 py-0.5 rounded text-[11px] border border-rose-900 text-rose-300 hover:bg-rose-950/50 disabled:opacity-50"
            >
              Delete
            </button>
            </>
          ) : (
            <>
              <button
                onClick={() => act.mutate({ id: idea.id, kind: "restore" })}
                disabled={act.isPending}
                className="px-2 py-0.5 rounded text-[11px] border border-line-strong text-body hover:bg-raised disabled:opacity-50"
              >
                Restore
              </button>
              <button
                onClick={() => confirmDelete(idea)}
                disabled={act.isPending}
                className="px-2 py-0.5 rounded text-[11px] border border-rose-900 text-rose-300 hover:bg-rose-950/50 disabled:opacity-50"
              >
                Delete permanently
              </button>
            </>
          )}
        </div>
      </div>
    );
  }

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
      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <Greeting text={(name) => `Hi ${name}, here are your ideas.`} />
            <h2 className="text-2xl font-bold text-strong tracking-tight">Ideas by stage</h2>
            <p className="text-sm text-subtle mt-1">Each column is a stage. Highest score first inside each column.</p>
          </div>
          <div className="flex items-center gap-2">
            <div role="tablist" className="flex items-center gap-1 rounded-lg border border-line p-1">
              {(["board", "archive"] as const).map((v) => (
                <button
                  key={v}
                  role="tab"
                  aria-selected={view === v}
                  onClick={() => router.push(v === "archive" ? "/ideas?view=archive" : "/ideas")}
                  data-testid={`ideas-view-${v}`}
                  className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${
                    view === v ? "bg-violet-600 text-strong" : "text-muted hover:text-body-strong"
                  }`}
                >
                  {v === "board" ? "Board" : `Archive (${archived.length})`}
                </button>
              ))}
            </div>
            <button
              onClick={() => refetch()}
              className="px-3 py-1.5 rounded-md text-xs font-medium bg-raised hover:bg-raised-strong text-body-strong border border-line-strong"
            >
              Refresh
            </button>
          </div>
        </div>

        {isLoading && <p className="py-20 text-center text-sm text-subtle">Loading ideas…</p>}
        {isError && (
          <div className="my-8 p-4 rounded-lg bg-rose-950/40 border border-rose-800 text-rose-300 text-sm">
            Failed to load ideas: {(error as Error)?.message}
          </div>
        )}

        {!isLoading && !isError && view === "board" && (
          <>
            {/* Phone: one stage at a time, picked by tab, so reaching Published never means
                scrolling past every New idea first. */}
            <div className="md:hidden mt-6">
              <div role="tablist" aria-label="Stage" className="cos-scroll-x flex gap-2 overflow-x-auto pb-1 [&>button]:shrink-0">
                {STAGES.map((stage) => {
                  const count = active.filter((i) => i.status === stage.status).length;
                  const selected = mobileStage === stage.status;
                  return (
                    <button
                      key={stage.status}
                      role="tab"
                      aria-selected={selected}
                      onClick={() => setMobileStage(stage.status)}
                      data-testid={`mobile-stage-${stage.status}`}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold border ${
                        selected ? "bg-accent border-accent text-strong" : "border-line-strong text-body hover:bg-raised"
                      }`}
                    >
                      {stage.label} <span className="text-subtle">{count}</span>
                    </button>
                  );
                })}
              </div>
              {STAGES.filter((s) => s.status === mobileStage).map((stage) => {
                const items = active
                  .filter((i) => i.status === stage.status)
                  .sort((a, b) => (scoreOf(b) ?? -1) - (scoreOf(a) ?? -1));
                return (
                  <div key={stage.status} className="mt-3 space-y-2.5" data-testid={`stage-mobile-${stage.status}`}>
                    {items.length === 0 ? (
                      <p className="py-12 text-center text-xs text-faint border border-dashed border-line rounded-xl">
                        No ideas in this stage.
                      </p>
                    ) : (
                      items.map((idea) => <Card key={idea.id} idea={idea} />)
                    )}
                  </div>
                );
              })}
            </div>

            {/* Tablet and up: all four stages side by side. */}
            <div className="hidden md:grid mt-6 md:grid-cols-2 xl:grid-cols-4 gap-4">
              {STAGES.map((stage) => {
                const items = active
                  .filter((i) => i.status === stage.status)
                  .sort((a, b) => (scoreOf(b) ?? -1) - (scoreOf(a) ?? -1));
                return (
                  <section key={stage.status} className="rounded-xl bg-panel border border-line p-3 min-h-[480px]" data-testid={`stage-${stage.status}`}>
                    <h3 className="flex items-center justify-between px-1 mb-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
                      {stage.label}
                      <span className="text-subtle">{items.length}</span>
                    </h3>
                    <div className="space-y-2.5">
                      {items.length === 0 ? (
                        <p className="text-xs text-faint px-1">No ideas in this stage.</p>
                      ) : (
                        items.map((idea) => <Card key={idea.id} idea={idea} />)
                      )}
                    </div>
                  </section>
                );
              })}
            </div>
          </>
        )}

        {!isLoading && !isError && view === "archive" && (
          <div className="mt-6 space-y-2.5 max-w-3xl">
            <p className="text-xs text-subtle">Archived ideas are kept, not deleted. Restore one to bring it back to the board.</p>
            {archived.length === 0 ? (
              <p className="py-12 text-center text-sm text-faint border border-dashed border-line rounded-xl">Nothing archived.</p>
            ) : (
              archived.map((idea) => <Card key={idea.id} idea={idea} />)
            )}
          </div>
        )}
      </main>
    </div>
  );
}
