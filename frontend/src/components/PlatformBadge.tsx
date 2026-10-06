/**
 * Platform chip with a simplified SVG mark. These are generic shapes drawn for this app,
 * not the official brand artwork. Official logos can replace the marks below.
 */
import type { ReactNode } from "react";

const LABEL: Record<string, string> = {
  linkedin: "LinkedIn",
  facebook: "Facebook",
  instagram: "Instagram",
  reddit: "Reddit",
  substack: "Substack",
};

const TONE: Record<string, string> = {
  linkedin: "bg-sky-950/60 text-sky-300 border-sky-800",
  facebook: "bg-blue-950/60 text-blue-300 border-blue-800",
  instagram: "bg-fuchsia-950/50 text-fuchsia-300 border-fuchsia-800",
  reddit: "bg-orange-950/50 text-orange-300 border-orange-800",
  substack: "bg-amber-950/50 text-amber-300 border-amber-800",
};

const MARKS: Record<string, ReactNode> = {
  linkedin: (
    <>
      <rect width="24" height="24" rx="4" fill="#0A66C2" />
      <rect x="5" y="9" width="3" height="10" fill="#fff" />
      <circle cx="6.5" cy="5.6" r="1.9" fill="#fff" />
      <path d="M10 9h2.9v1.4c.5-.9 1.6-1.7 3.2-1.7 3 0 3.6 2 3.6 4.5V19h-3v-5c0-1.2 0-2.7-1.7-2.7S13 13 13 14.2V19h-3z" fill="#fff" />
    </>
  ),
  facebook: (
    <>
      <circle cx="12" cy="12" r="12" fill="#1877F2" />
      <path d="M13.3 19v-6.2h2.1l.3-2.5h-2.4V8.9c0-.7.2-1.2 1.2-1.2h1.3V5.5c-.2 0-1-.1-1.9-.1-1.9 0-3.2 1.2-3.2 3.3v1.8H8.5v2.5h2.2V19z" fill="#fff" />
    </>
  ),
  instagram: (
    <>
      <defs>
        <linearGradient id="ig-grad" x1="0" y1="24" x2="24" y2="0" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#FBC02D" />
          <stop offset="0.5" stopColor="#E1306C" />
          <stop offset="1" stopColor="#833AB4" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="22" height="22" rx="6" fill="url(#ig-grad)" />
      <rect x="5.2" y="5.2" width="13.6" height="13.6" rx="4" fill="none" stroke="#fff" strokeWidth="1.8" />
      <circle cx="12" cy="12" r="3.3" fill="none" stroke="#fff" strokeWidth="1.8" />
      <circle cx="16.4" cy="7.6" r="1" fill="#fff" />
    </>
  ),
  reddit: (
    <>
      <circle cx="12" cy="12" r="12" fill="#FF4500" />
      <ellipse cx="12" cy="14" rx="6" ry="4" fill="#fff" />
      <circle cx="9.2" cy="13.6" r="1" fill="#FF4500" />
      <circle cx="14.8" cy="13.6" r="1" fill="#FF4500" />
      <path d="M9 16.2c1.8 1.2 4.2 1.2 6 0" fill="none" stroke="#FF4500" strokeWidth="1" strokeLinecap="round" />
      <circle cx="17.8" cy="6.4" r="1.4" fill="#fff" />
      <path d="M12 7.4 13.4 4l3.6.8" fill="none" stroke="#fff" strokeWidth="1" />
    </>
  ),
  substack: (
    <>
      <rect width="24" height="24" rx="3" fill="#FF6719" />
      <rect x="5" y="5" width="14" height="3" fill="#fff" />
      <rect x="5" y="10.5" width="14" height="3" fill="#fff" />
      <path d="M5 16l7 3.5 7-3.5v2.5L12 22l-7-3.5z" fill="#fff" />
    </>
  ),
};

export function platformLabel(key: string): string {
  return LABEL[key] ?? key;
}

export function PlatformLogo({ platform, size = 14 }: { platform: string; size?: number }) {
  const mark = MARKS[platform];
  if (!mark) return null;
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true" className="shrink-0">
      {mark}
    </svg>
  );
}

export function PlatformBadge({ platform, muted = false }: { platform: string; muted?: boolean }) {
  const tone = TONE[platform] ?? "bg-raised text-body border-line-strong";
  return (
    <span
      data-testid="platform-badge"
      data-platform={platform}
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded border text-[11px] font-semibold ${tone} ${muted ? "opacity-60" : ""}`}
    >
      <PlatformLogo platform={platform} size={13} />
      {platformLabel(platform)}
    </span>
  );
}
