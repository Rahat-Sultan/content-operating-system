"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchVaultStatus, lockVault, setVaultPassword, unlockVault } from "@/lib/api";
import { PasswordInput } from "@/components/PasswordInput";

/**
 * Gates its children behind a second password, separate from the login password.
 * Unlocking is per browser session and lasts 15 minutes; the protected query (API
 * keys, Platforms) is never fetched until the gate reports unlocked, so the data
 * itself is never requested while locked.
 */
export function VaultGate({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const { data: status, isLoading } = useQuery({
    queryKey: ["vault-status"],
    queryFn: fetchVaultStatus,
    // Keep checking while unlocked, so the UI re-locks on its own at the 15 minute mark.
    refetchInterval: (query) => (query.state.data?.unlocked ? 15000 : false),
  });

  if (isLoading || !status) {
    return <p className="text-sm text-subtle">Loading…</p>;
  }
  if (!status.configured) {
    return <SetupForm onDone={() => queryClient.invalidateQueries({ queryKey: ["vault-status"] })} />;
  }
  if (!status.unlocked) {
    return <UnlockForm onDone={() => queryClient.invalidateQueries({ queryKey: ["vault-status"] })} />;
  }
  return (
    <div className="space-y-4">
      <UnlockedBar unlockedUntil={status.unlocked_until} />
      {children}
    </div>
  );
}

function UnlockedBar({ unlockedUntil }: { unlockedUntil: string | null }) {
  const queryClient = useQueryClient();
  const [label, setLabel] = useState("");

  useEffect(() => {
    if (!unlockedUntil) return;
    const update = () => {
      const ms = new Date(unlockedUntil).getTime() - Date.now();
      if (ms <= 0) {
        setLabel("Locking…");
        queryClient.invalidateQueries({ queryKey: ["vault-status"] });
        return;
      }
      setLabel(`Unlocked for ${Math.ceil(ms / 60000)} more min`);
    };
    update();
    const id = setInterval(update, 5000);
    return () => clearInterval(id);
  }, [unlockedUntil, queryClient]);

  const lock = useMutation({
    mutationFn: lockVault,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["vault-status"] }),
  });

  const [changing, setChanging] = useState(false);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3 rounded-lg border border-line bg-raised/40 px-3 py-2 text-xs text-muted">
        <span>🔓 {label}</span>
        <div className="flex items-center gap-3">
          <button type="button" onClick={() => setChanging((v) => !v)} className="font-semibold text-accent-text hover:underline">
            {changing ? "Cancel" : "Change password"}
          </button>
          <button type="button" onClick={() => lock.mutate()} disabled={lock.isPending} className="font-semibold text-accent-text hover:underline">
            {lock.isPending ? "Locking…" : "Lock now"}
          </button>
        </div>
      </div>
      {changing && <ChangeVaultPasswordForm onDone={() => setChanging(false)} />}
    </div>
  );
}

function ChangeVaultPasswordForm({ onDone }: { onDone: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const save = useMutation({
    mutationFn: () => setVaultPassword(current, next),
    onSuccess: () => {
      setError(null);
      setDone(true);
      setTimeout(onDone, 1200);
    },
    onError: (e: any) => setError(e.message),
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        if (next !== confirm) {
          setError("The new password and its confirmation don't match.");
          return;
        }
        save.mutate();
      }}
      className="cos-card p-4 space-y-3 max-w-sm"
      data-testid="vault-change-password-form"
    >
      <h4 className="text-sm font-semibold text-body-strong">Change settings password</h4>
      <div>
        <span className="cos-label">Current settings password</span>
        <div className="mt-1">
          <PasswordInput value={current} onChange={setCurrent} autoComplete="current-password" testId="vault-change-current" />
        </div>
      </div>
      <div>
        <span className="cos-label">New settings password</span>
        <div className="mt-1">
          <PasswordInput value={next} onChange={setNext} autoComplete="new-password" testId="vault-change-new" />
        </div>
        <p className="mt-1 text-[11px] text-faint">At least 10 characters.</p>
      </div>
      <div>
        <span className="cos-label">Confirm new password</span>
        <div className="mt-1">
          <PasswordInput value={confirm} onChange={setConfirm} autoComplete="new-password" testId="vault-change-confirm" />
        </div>
      </div>
      {error && <p className="text-xs text-bad">{error}</p>}
      <button type="submit" className="cos-btn-primary w-full" disabled={save.isPending || !current || !next || !confirm}>
        {save.isPending ? "Saving…" : done ? "Saved" : "Change password"}
      </button>
    </form>
  );
}

function SetupForm({ onDone }: { onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () => setVaultPassword(null, password),
    onSuccess: onDone,
    onError: (e: any) => setError(e.message),
  });

  return (
    <div className="cos-card p-5 space-y-3 max-w-sm" data-testid="vault-setup-form">
      <h3 className="text-sm font-semibold text-body-strong">Set a settings password</h3>
      <p className="text-xs text-muted">
        API keys and platform credentials are sensitive. Set a separate password to protect them — different from
        your login password. You'll unlock with it for 15 minutes at a time.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          if (password !== confirm) {
            setError("The password and its confirmation don't match.");
            return;
          }
          save.mutate();
        }}
        className="space-y-3"
      >
        <div>
          <span className="cos-label">Settings password</span>
          <div className="mt-1">
            <PasswordInput value={password} onChange={setPassword} autoComplete="new-password" testId="vault-new-password" />
          </div>
          <p className="mt-1 text-[11px] text-faint">At least 10 characters.</p>
        </div>
        <div>
          <span className="cos-label">Confirm</span>
          <div className="mt-1">
            <PasswordInput value={confirm} onChange={setConfirm} autoComplete="new-password" testId="vault-confirm-password" />
          </div>
        </div>
        {error && <p className="text-xs text-bad">{error}</p>}
        <button type="submit" className="cos-btn-primary w-full" disabled={save.isPending || !password || !confirm}>
          {save.isPending ? "Saving…" : "Set password and unlock"}
        </button>
      </form>
    </div>
  );
}

function UnlockForm({ onDone }: { onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const unlock = useMutation({
    mutationFn: () => unlockVault(password),
    onSuccess: onDone,
    onError: (e: any) => setError(e.message),
  });

  return (
    <div className="cos-card p-5 space-y-3 max-w-sm" data-testid="vault-unlock-form">
      <h3 className="text-sm font-semibold text-body-strong">Settings are locked</h3>
      <p className="text-xs text-muted">Enter your settings password to view API keys and platform credentials.</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          unlock.mutate();
        }}
        className="space-y-3"
      >
        <div>
          <span className="cos-label">Settings password</span>
          <div className="mt-1">
            <PasswordInput value={password} onChange={setPassword} autoComplete="current-password" testId="vault-unlock-password" />
          </div>
        </div>
        {error && <p className="text-xs text-bad">{error}</p>}
        <button type="submit" className="cos-btn-primary w-full" disabled={unlock.isPending || !password}>
          {unlock.isPending ? "Unlocking…" : "Unlock"}
        </button>
      </form>
    </div>
  );
}
