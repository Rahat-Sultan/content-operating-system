"use client";

import { useState } from "react";

function EyeOpenIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function EyeClosedIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M9.9 4.24A10.9 10.9 0 0 1 12 4c7 0 11 7 11 7a18.5 18.5 0 0 1-2.16 3.19M6.6 6.6C3.1 8.73 1 12 1 12s4 7 11 7a10.6 10.6 0 0 0 5.4-1.6M9.9 9.9a3 3 0 1 0 4.2 4.2" />
      <path d="M1 1l22 22" />
    </svg>
  );
}

/**
 * A text field hidden behind a masked display by default (like a password field, but for
 * an identifier rather than a secret). An eye icon shows or hides it — open when visible,
 * closed when hidden.
 */
export function RevealInput({
  value,
  onChange,
  placeholder,
  disabled,
  className = "",
  testId,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  testId?: string;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="relative">
      <input
        type={visible ? "text" : "password"}
        autoComplete="off"
        placeholder={placeholder}
        disabled={disabled}
        data-testid={testId}
        className={`pr-9 ${className}`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? "Hide" : "Show"}
        aria-pressed={visible}
        className="absolute right-2 top-1/2 -translate-y-1/2 text-subtle hover:text-body-strong"
      >
        {visible ? <EyeOpenIcon /> : <EyeClosedIcon />}
      </button>
    </div>
  );
}
