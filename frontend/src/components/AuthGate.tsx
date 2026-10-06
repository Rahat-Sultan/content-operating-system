"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchAuthProviders, fetchMe, GOOGLE_LOGIN_URL, loginAccount, registerAccount } from "@/lib/api";

/** Shows the app only to a logged-in account. Everyone else sees the login screen. */
export function AuthGate({ children }: { children: ReactNode }) {
  const { data: me, isLoading, isError, error } = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  if (isLoading) return <div className="min-h-screen bg-canvas" />;
  if (isError) {
    return <div className="min-h-screen bg-canvas p-6 text-sm text-bad">{(error as Error).message}</div>;
  }
  if (!me) return <LoginScreen />;
  return <>{children}</>;
}

function LoginScreen() {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const providers = useQuery({ queryKey: ["auth-providers"], queryFn: fetchAuthProviders });

  const submit = useMutation({
    mutationFn: () => (mode === "login" ? loginAccount(email, password) : registerAccount(email, password, name)),
    onSuccess: () => {
      setError(null);
      setPassword("");
      queryClient.invalidateQueries({ queryKey: ["me"] });
    },
    onError: (e: any) => setError(e.message),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    submit.mutate();
  }

  const google = providers.data?.google.enabled;
  const supabase = providers.data?.supabase;

  return (
    <div className="min-h-screen bg-canvas text-body-strong flex items-center justify-center p-6">
      <div className="w-full max-w-sm space-y-5">
        <div className="flex flex-col items-center gap-3">
          <img src="/logo.svg" alt="Content OS" className="h-12 w-12" />
          <h1 className="text-xl font-semibold text-strong">Content OS</h1>
          <p className="text-xs text-muted">Log in to your account</p>
        </div>

        <div role="tablist" className="grid grid-cols-2 gap-1 rounded-lg border border-line p-1">
          {(["login", "register"] as const).map((m) => (
            <button key={m} role="tab" aria-selected={mode === m} onClick={() => setMode(m)}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold ${mode === m ? "bg-accent text-white" : "text-muted hover:text-body-strong"}`}>
              {m === "login" ? "Log in" : "Create account"}
            </button>
          ))}
        </div>

        <form onSubmit={onSubmit} className="cos-card p-5 space-y-3" data-testid="login-form">
          {mode === "register" && (
            <div>
              <span className="cos-label">Name</span>
              <input className="cos-input mt-1" value={name} onChange={(e) => setName(e.target.value)} placeholder="Optional" />
            </div>
          )}
          <div>
            <span className="cos-label">Email</span>
            <input type="email" autoComplete="email" required className="cos-input mt-1" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <span className="cos-label">Password</span>
            <input type="password" required autoComplete={mode === "login" ? "current-password" : "new-password"}
              className="cos-input mt-1" value={password} onChange={(e) => setPassword(e.target.value)} />
            {mode === "register" && <p className="mt-1 text-[11px] text-faint">At least 10 characters.</p>}
          </div>
          {error && <p className="text-xs text-bad">{error}</p>}
          <button type="submit" className="cos-btn-primary w-full" disabled={submit.isPending}>
            {submit.isPending ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}
          </button>
        </form>

        <div className="flex items-center gap-3 text-[11px] text-faint">
          <span className="h-px flex-1 bg-line" /> or <span className="h-px flex-1 bg-line" />
        </div>

        <div className="space-y-2">
          {google ? (
            <a href={GOOGLE_LOGIN_URL} className="cos-btn w-full" data-testid="login-google">Continue with Google</a>
          ) : (
            <button className="cos-btn w-full opacity-50" disabled title="Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to backend/.env">
              Continue with Google (not configured)
            </button>
          )}
          <button className="cos-btn w-full opacity-50" disabled title={supabase?.reason ?? "Not configured yet"}>
            Continue with Supabase (not configured)
          </button>
        </div>
      </div>
    </div>
  );
}
