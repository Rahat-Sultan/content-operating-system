"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PlatformLogo } from "@/components/PlatformBadge";
import { PasswordInput } from "@/components/PasswordInput";
import {
  ApiKeyState,
  changePassword,
  fetchApiKeys,
  fetchMe,
  fetchPlatformSettings,
  PlatformSetting,
  removeApiKey,
  saveApiKey,
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

function AccountSection() {
  const queryClient = useQueryClient();
  const { data: me } = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const save = useMutation({
    mutationFn: () => changePassword(me?.has_password ? current : null, next),
    onSuccess: () => {
      setError(null);
      setCurrent("");
      setNext("");
      setConfirm("");
      setDone(true);
      setTimeout(() => setDone(false), 2500);
      queryClient.invalidateQueries({ queryKey: ["me"] });
    },
    onError: (e: any) => setError(e.message),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (next !== confirm) {
      setError("The new password and its confirmation don't match.");
      return;
    }
    save.mutate();
  }

  if (!me) return null;

  return (
    <section id="account" className="scroll-mt-20 space-y-3">
      <h3 className="cos-label">Account</h3>
      <div className="cos-card p-4 space-y-1">
        <p className="text-sm text-body-strong">{me.display_name ?? me.email}</p>
        <p className="text-xs text-subtle">{me.email}</p>
        <p className="text-[11px] text-faint">
          {me.auth_provider === "google" ? "Signed in with Google" : "Local account"}
          {!me.has_password && " · no password set yet"}
        </p>
      </div>

      <form onSubmit={onSubmit} className="cos-card p-4 space-y-3" data-testid="change-password-form">
        <h4 className="text-sm font-semibold text-body-strong">
          {me.has_password ? "Change password" : "Set a password"}
        </h4>
        {!me.has_password && (
          <p className="text-xs text-muted">
            Your account signed in with Google and has no password yet. Set one to also log in with email and password.
          </p>
        )}
        {me.has_password && (
          <div>
            <span className="cos-label">Current password</span>
            <div className="mt-1">
              <PasswordInput value={current} onChange={setCurrent} autoComplete="current-password" testId="current-password" />
            </div>
          </div>
        )}
        <div>
          <span className="cos-label">New password</span>
          <div className="mt-1">
            <PasswordInput value={next} onChange={setNext} autoComplete="new-password" testId="new-password" />
          </div>
          <p className="mt-1 text-[11px] text-faint">At least 10 characters.</p>
        </div>
        <div>
          <span className="cos-label">Confirm new password</span>
          <div className="mt-1">
            <PasswordInput value={confirm} onChange={setConfirm} autoComplete="new-password" testId="confirm-password" />
          </div>
        </div>
        {error && <p className="text-xs text-bad">{error}</p>}
        <div className="flex justify-end">
          <button type="submit" className="cos-btn-primary" disabled={save.isPending || !next || !confirm}>
            {save.isPending ? "Saving…" : done ? "Saved" : me.has_password ? "Change password" : "Set password"}
          </button>
        </div>
      </form>
    </section>
  );
}

function ApiKeyRow({ k }: { k: ApiKeyState }) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => saveApiKey(k.name, value),
    onSuccess: () => {
      setValue("");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["api-keys"] });
    },
    onError: (e: any) => setError(e.message),
  });
  const remove = useMutation({
    mutationFn: () => removeApiKey(k.name),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["api-keys"] });
    },
    onError: (e: any) => setError(e.message),
  });
  return (
    <div className="cos-card p-4 space-y-3" data-testid={`key-${k.name}`}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="font-semibold text-strong text-sm">{k.label}</h3>
          <p className="font-mono text-[11px] text-subtle">{k.name}</p>
        </div>
        <span className={`px-2 py-0.5 rounded border text-[11px] font-semibold ${k.is_set ? "border-emerald-700 text-emerald-300 bg-emerald-950/40" : "border-line-strong text-muted bg-raised"}`}>
          {k.is_set ? `Set · ends …${k.last4 ?? ""}` : "Not set"}
        </span>
      </div>
      <p className="text-[11px] text-subtle">
        {k.saved_in_app
          ? "Saved in the app (encrypted)."
          : k.from_env
          ? "Set in backend/.env. Saving here overrides it."
          : "Not set anywhere yet."}
      </p>
      <div className="flex gap-2">
        <input
          type="password"
          autoComplete="off"
          aria-label={`New ${k.label} key`}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={k.is_set ? "Enter a new key to replace it" : "Paste the key"}
          className="cos-input font-mono"
        />
        <button className="cos-btn-primary whitespace-nowrap" disabled={!value.trim() || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? "Saving…" : "Save key"}
        </button>
        {k.saved_in_app && (
          <button className="cos-btn-danger whitespace-nowrap" disabled={remove.isPending} onClick={() => remove.mutate()}>
            Remove
          </button>
        )}
      </div>
      {error && <p className="text-xs text-bad">{error}</p>}
    </div>
  );
}

function SettingsContent({ onLock: _onLock }: { onLock: () => void }) {
  const queryClient = useQueryClient();
  const { data: keys, error: keysError } = useQuery({ queryKey: ["api-keys"], queryFn: fetchApiKeys });
  const { data, isLoading, isError, error } = useQuery({ queryKey: ["platform-settings"], queryFn: fetchPlatformSettings });
  // The server answers 401 once the session has ended. Go back to the password form.
  useEffect(() => {
    const msg = String((keysError as Error | null)?.message ?? (error as Error | null)?.message ?? "");
    if (msg.includes("session has ended") || msg.includes("Settings are locked")) {
      queryClient.invalidateQueries({ queryKey: ["settings-auth"] });
    }
  }, [keysError, error, queryClient]);
  return (
    <>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-strong tracking-tight">Settings</h2>
          <p className="text-sm text-muted mt-1">
            Your own API keys and platforms. Only you can see them.
          </p>
        </div>
      </div>

      <AccountSection />

      <section id="api-keys" className="scroll-mt-20 space-y-3">
        <h3 className="cos-label">API keys</h3>
        <p className="text-xs text-muted">
          Keys are encrypted before they are stored. Once saved, a key is never shown again; only its last four characters.
        </p>
        {keysError && <p className="text-sm text-bad">{(keysError as Error).message}</p>}
        {keys?.map((k) => <ApiKeyRow key={k.name} k={k} />)}
      </section>

      <section id="platforms" className="scroll-mt-20 space-y-4">
        <h3 className="cos-label">Platforms</h3>
        <p className="text-sm text-muted">
          A platform is used only when it is turned on, has a channel, and its token is set above or in <code className="font-mono">backend/.env</code>.
        </p>
        {isLoading && <p className="text-sm text-subtle">Loading…</p>}
        {isError && <p className="text-sm text-bad">{(error as Error).message}</p>}
        {data?.map((p) => <PlatformCard key={p.key} p={p} />)}
      </section>
    </>
  );
}

export default function SettingsPage() {
  // The account login is the gate for the whole app, so Settings needs no second password.
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
      </header>
      <main className="max-w-4xl mx-auto px-4 sm:px-6 py-6 sm:py-8 space-y-8">
        <SettingsContent onLock={() => undefined} />
      </main>
    </div>
  );
}
