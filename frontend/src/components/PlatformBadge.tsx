/** Platform chip with a letter mark. Not a brand logo. Same look on the Ideas and Analytics pages. */
const MARK: Record<string, { letter: string; tone: string }> = {
  linkedin: { letter: "in", tone: "bg-sky-950/60 text-sky-300 border-sky-800" },
  facebook: { letter: "f", tone: "bg-blue-950/60 text-blue-300 border-blue-800" },
  instagram: { letter: "ig", tone: "bg-fuchsia-950/50 text-fuchsia-300 border-fuchsia-800" },
  reddit: { letter: "r", tone: "bg-orange-950/50 text-orange-300 border-orange-800" },
  substack: { letter: "s", tone: "bg-amber-950/50 text-amber-300 border-amber-800" },
};
const LABEL: Record<string, string> = {
  linkedin: "LinkedIn",
  facebook: "Facebook",
  instagram: "Instagram",
  reddit: "Reddit",
  substack: "Substack",
};

export function platformLabel(key: string): string {
  return LABEL[key] ?? key;
}

export function PlatformBadge({ platform, muted = false }: { platform: string; muted?: boolean }) {
  const mark = MARK[platform] ?? { letter: platform.slice(0, 2).toLowerCase(), tone: "bg-slate-800 text-slate-300 border-slate-700" };
  return (
    <span
      data-testid="platform-badge"
      data-platform={platform}
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded border text-[11px] font-semibold ${mark.tone} ${muted ? "opacity-60" : ""}`}
    >
      <span aria-hidden className="font-mono text-[10px] uppercase">{mark.letter}</span>
      {platformLabel(platform)}
    </span>
  );
}
