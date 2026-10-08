"use client";

import { useState } from "react";

/** A password field with a show/hide toggle. */
export function PasswordInput({
  value,
  onChange,
  autoComplete,
  placeholder,
  testId,
}: {
  value: string;
  onChange: (v: string) => void;
  autoComplete?: string;
  placeholder?: string;
  testId?: string;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="relative">
      <input
        type={visible ? "text" : "password"}
        autoComplete={autoComplete}
        placeholder={placeholder}
        required
        data-testid={testId}
        className="cos-input pr-16"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? "Hide password" : "Show password"}
        className="absolute right-2 top-1/2 -translate-y-1/2 px-2 py-1 text-[11px] font-semibold text-subtle hover:text-body-strong"
      >
        {visible ? "Hide" : "Show"}
      </button>
    </div>
  );
}
