"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AppNav } from "@/components/AppNav";
import { PlatformLogo } from "@/components/PlatformBadge";
import {
  fetchPlatformSettings,
  PlatformSetting,
  savePlatformSettings,
  testPlatformConnection,
} from "@/lib/api";

const STATE_STYLE: Record<PlatformSetting["state"], string> = {
  ready: "border-emerald-700 text-emerald-300 bg-emerald-950/40",
  needs_token: "border-amber-700 text-amber-300 bg-amber-950/40",
  needs_channel: "border-amber-700 text-amber-300 bg-amber-950/40",
  disabled: "border-line-strong text-muted bg-raised",
  no_provider: "border-line-strong text-subtle bg-raised",
};
const STATE_LABEL: Record<PlatformSetting["state"], string> = {
  ready: "Ready",
  needs_token: "Needs token",
  needs_channel: "Needs channel",
  disabled: "Off",
  no_provider: "Not built yet",
};

function PlatformCard({ p }: { p: PlatformSetting }) {
  const queryClient = useQueryClient();
  const [enabled, setEnabled] = useState(p.enabled);
  const [displayName, setDisplayName] = useState(p.display_name ?? "");
  const [channelId, setChannelId] = useState(p.channel_id ?? "");
  const [notes, setNotes] = useState(p.notes ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [test, setTest] = useState<{ ok: boolean; message: string } | null>(null);

  // Keep the form in step with the server after a save or refresh.
  useEffect(() => {
    setEnabled(p.enabled);
    setDisplayName(p.display_name ?? "");
    setChannelId(p.channel_id ?? "");
    setNotes(p.notes ?? "");
  }, [p.enabled, p.display_name, p.channel_id, p.notes]);

  const save = useMutation({
    mutationFn: () =>
      savePlatformSettings(p.key, {
        enabled,
        display_name: displayName.trim() || null,
        channel_id: channelId.trim() || null,
        notes: notes.trim() || null,
      }),
    onSuccess: () => {
      setError(null);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      queryClient.invalidateQueries({ queryKey: ["platform-settings"] });
      queryClient.invalidateQueries({ queryKey: ["analytics-summary"] });
    },
    onError: (e: any) => setError(e.message),
  });

  const check = useMutation({
    mutationFn: () => testPlatformConnection(p.key),
    onSuccess: (r) => setTest(r),
    onError: (e: any) => setTest({ ok: false, message: e.message }),
  });

  const dirty =
    enabled !== p.enabled ||
    (displayName.trim() || "") !== (p.display_name ?? "") ||
    (channelId.trim() || "") !== (p.channel_id ?? "") ||
    (notes.trim() || "") !== (p.notes ?? "");

  return (
    <section data-testid={`platform-${p.key}`} className="cos-card p-5 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <PlatformLogo platform={p.key} size={28} />
          <div>
            <h3 className="font-semibold text-strong">{p.label}</h3>
            <p className="text-[11px] text-subtle">
              {p.publishes_via === "buffer" ? "Publishes through Buffer" : "No publishing provider yet"}
            </p>
          </div>
        </div>
        <span
          data-testid={`platform-state-${p.key}`}
          className={`px-2 py-0.5 rounded border text-[11px] font-semibold ${STATE_STYLE[p.state]}`}
        >
          {STATE_LABEL[p.state]}
        </span>
      </div>

      <p className="text-xs text-muted">{p.reason}</p>

      <div className="grid gap-3 md:grid-cols-2">
        <label className="flex items-center gap-2 text-sm text-body md:col-span-2">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            disabled={p.publishes_via !== "buffer"}
          />
          Use {p.label} for publishing and analytics
        </label>

        <div>
          <span className="cos-label">Display name</span>
          <input className="cos-input mt-1" value={displayName} placeholder={p.label}
            onChange={(e) => setDisplayName(e.target.value)} />
        </div>

        <div>
          <span className="cos-label">Buffer channel ID</span>
          <input className="cos-input mt-1 font-mono" value={channelId} placeholder="e.g. 6ab12cd3…"
            onChange={(e) => setChannelId(e.target.value)} disabled={p.publishes_via !== "buffer"} />
          <p className="mt-1 text-[11px] text-faint">
            Find it in Buffer under the channel's settings. It is an identifier, not a secret.
          </p>
        </div>

        <div className="md:col-span-2">
          <span className="cos-label">Notes</span>
          <textarea className="cos-input mt-1" rows={2} value={notes}
            onChange={(e) => setNotes(e.target.value)} placeholder="Anything you want to remember about this account" />
        </div>
      </div>

      {error && <p className="text-xs text-bad">{error}</p>}
      {test && (
        <p data-testid={`platform-test-${p.key}`} className={`text-xs ${test.ok ? "text-good" : "text-warn"}`}>
          {test.ok ? "✓ " : "⚠ "}
          {test.message}
        </p>
      )}

      <div className="flex items-center justify-end gap-2 pt-1">
        <button
          onClick={() => check.mutate()}
          disabled={check.isPending || p.publishes_via !== "buffer" || dirty}
          title={dirty ? "Save your changes first" : undefined}
          className="cos-btn"
        >
          {check.isPending ? "Checking…" : "Test connection"}
        </button>
        <button onClick={() => save.mutate()} disabled={!dirty || save.isPending} className="cos-btn-primary">
          {save.isPending ? "Saving…" : saved ? "Saved" : "Save"}
        </button>
      </div>
    </section>
  );
}

export default function SettingsPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["platform-settings"],
    queryFn: fetchPlatformSettings,
  });

  return (
    <div className="min-h-screen bg-canvas text-body-strong">
      <header className="cos-header">
        <div className="flex items-center gap-3">
          <img src="/logo.svg" alt="Content OS" className="h-8 w-8 shrink-0" />
          <div>
            <h1 className="text-lg font-semibold text-strong tracking-tight">Content OS</h1>
            <p className="text-xs text-muted">Autonomous Content Intelligence Engine</p>
          </div>
        </div>
        <AppNav />
      </header>

      <main className="max-w-4xl mx-auto px-6 py-8 space-y-6">
        <div>
          <h2 className="text-2xl font-bold text-strong tracking-tight">Platforms</h2>
          <p className="text-sm text-muted mt-1">
            Set up each platform you publish to. A platform is used only when it is turned on, has a channel,
            and its token is in <code className="font-mono">backend/.env</code>. Tokens are never shown here.
          </p>
        </div>

        {isLoading && <p className="text-sm text-subtle">Loading…</p>}
        {isError && <p className="text-sm text-bad">{(error as Error).message}</p>}
        {data?.map((p) => <PlatformCard key={p.key} p={p} />)}
      </main>
    </div>
  );
}
