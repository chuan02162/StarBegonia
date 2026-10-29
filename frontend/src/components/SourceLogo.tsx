type Props = { source: string; className?: string };

const LOGO_SRC: Record<string, string> = {
  coles: "/coles.png",
  commbank: "/commbank.png",
};

export function SourceLogo({ source, className = "h-10 w-10" }: Props) {
  const src = LOGO_SRC[source];
  if (src) {
    return (
      <img
        src={src}
        alt=""
        className={`shrink-0 rounded-md object-contain ${className}`}
      />
    );
  }
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-md bg-ink-100 font-display text-sm font-semibold text-ink-700 ${className}`}
      aria-hidden
    >
      {source.slice(0, 1).toUpperCase()}
    </span>
  );
}

export const SOURCE_LABELS: Record<string, string> = {
  coles: "Coles",
  commbank: "CommBank",
  manual: "手动记账",
};
