"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchAuthProviders,
  fetchMe,
  GOOGLE_LOGIN_URL,
  loginAccount,
  registerAccount,
  requestPasswordReset,
  resetPassword,
  verifyResetCode,
} from "@/lib/api";
import { PasswordInput } from "@/components/PasswordInput";

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

function ForgotPasswordCard({ initialEmail, onDone }: { initialEmail: string; onDone: () => void }) {
  // Three steps: email -> code (checked before anything else shows) -> new password + confirm.
  const [step, setStep] = useState<"email" | "code" | "password">("email");
  const [email, setEmail] = useState(initialEmail);
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const request = useMutation({
    mutationFn: () => requestPasswordReset(email),
    onSuccess: () => {
      setError(null);
      setCode("");
      setStep("code");
      setNotice("If that email has an account, a 6-digit code is on its way. It expires in 10 minutes.");
    },
    onError: (e: any) => setError(e.message),
  });

  const verify = useMutation({
    mutationFn: () => verifyResetCode(email, code),
    onSuccess: () => {
      setError(null);
      setStep("password");
    },
    onError: (e: any) => setError(e.message),
  });

  const confirm = useMutation({
    mutationFn: () => resetPassword(email, code, newPassword),
    onSuccess: () => {
      setError(null);
      onDone();
    },
    onError: (e: any) => setError(e.message),
  });

  return (
    <div className="cos-card p-5 space-y-3" data-testid="forgot-password-form">
      <h2 className="text-sm font-semibold text-body-strong">Reset your password</h2>

      {step === "email" && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            request.mutate();
          }}
          className="space-y-3"
        >
          <div>
            <span className="cos-label">Email</span>
            <input type="email" required autoComplete="email" className="cos-input mt-1" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          {error && <p className="text-xs text-bad">{error}</p>}
          <button type="submit" className="cos-btn-primary w-full" disabled={request.isPending}>
            {request.isPending ? "Sending…" : "Send reset code"}
          </button>
          <button type="button" onClick={onDone} className="text-xs text-muted hover:text-body-strong w-full text-center">
            Back to log in
          </button>
        </form>
      )}

      {step === "code" && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            verify.mutate();
          }}
          className="space-y-3"
        >
          {notice && <p className="text-xs text-muted">{notice}</p>}
          <div>
            <span className="cos-label">6-digit code</span>
            <input
              inputMode="numeric"
              pattern="\d{6}"
              maxLength={6}
              required
              autoComplete="one-time-code"
              className="cos-input mt-1 font-mono tracking-[0.3em] text-center"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
            />
          </div>
          {error && <p className="text-xs text-bad">{error}</p>}
          <button type="submit" className="cos-btn-primary w-full" disabled={verify.isPending || code.length !== 6}>
            {verify.isPending ? "Checking…" : "Verify code"}
          </button>
          <div className="flex items-center justify-between text-xs">
            <button type="button" onClick={() => setStep("email")} className="text-muted hover:text-body-strong">
              Use a different email
            </button>
            <button
              type="button"
              disabled={request.isPending}
              onClick={() => request.mutate()}
              className="text-muted hover:text-body-strong"
            >
              {request.isPending ? "Sending…" : "Resend code"}
            </button>
          </div>
        </form>
      )}

      {step === "password" && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            if (newPassword !== confirmPassword) {
              setError("The new password and its confirmation don't match.");
              return;
            }
            confirm.mutate();
          }}
          className="space-y-3"
        >
          <p className="text-xs text-good">Code verified. Choose a new password.</p>
          <div>
            <span className="cos-label">New password</span>
            <div className="mt-1">
              <PasswordInput value={newPassword} onChange={setNewPassword} autoComplete="new-password" testId="reset-new-password" />
            </div>
            <p className="mt-1 text-[11px] text-faint">At least 10 characters.</p>
          </div>
          <div>
            <span className="cos-label">Confirm new password</span>
            <div className="mt-1">
              <PasswordInput value={confirmPassword} onChange={setConfirmPassword} autoComplete="new-password" testId="reset-confirm-password" />
            </div>
          </div>
          {error && <p className="text-xs text-bad">{error}</p>}
          <button type="submit" className="cos-btn-primary w-full" disabled={confirm.isPending || !newPassword || !confirmPassword}>
            {confirm.isPending ? "Resetting…" : "Reset password"}
          </button>
          <button type="button" onClick={() => setStep("code")} className="text-xs text-muted hover:text-body-strong w-full text-center">
            Back
          </button>
        </form>
      )}
    </div>
  );
}

function LoginScreen() {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [forgot, setForgot] = useState(false);
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

        {forgot ? (
          <ForgotPasswordCard initialEmail={email} onDone={() => setForgot(false)} />
        ) : (
          <>
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
                <div className="flex items-center justify-between">
                  <span className="cos-label">Password</span>
                  {mode === "login" && (
                    <button type="button" onClick={() => setForgot(true)} className="text-[11px] text-accent-text hover:underline">
                      Forgot password?
                    </button>
                  )}
                </div>
                <div className="mt-1">
                  <PasswordInput
                    value={password}
                    onChange={setPassword}
                    autoComplete={mode === "login" ? "current-password" : "new-password"}
                    testId="login-password"
                  />
                </div>
                {mode === "register" && <p className="mt-1 text-[11px] text-faint">At least 10 characters.</p>}
              </div>
              {error && <p className="text-xs text-bad">{error}</p>}
              <button type="submit" className="cos-btn-primary w-full" disabled={submit.isPending}>
                {submit.isPending ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}
              </button>
            </form>
          </>
        )}

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
