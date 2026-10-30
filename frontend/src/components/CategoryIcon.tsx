/** Simple line icons for category ids (Lucide/Heroicons-style paths). */

import type { ReactNode } from "react";

type Props = {
  id: string | null | undefined;
  className?: string;
};

const stroke = {
  fill: "none" as const,
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

function Svg({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className || "h-5 w-5"}
      aria-hidden
      {...stroke}
    >
      {children}
    </svg>
  );
}

/** Unified mark for unclassified / unclear bank lines. */
function UnclearIcon({ className }: { className?: string }) {
  return (
    <Svg className={className}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
      <path d="M14 2v6h6" />
      <path d="M9 13h6" />
      <path d="M9 17h4" />
      <circle cx="9.5" cy="9.5" r="0.6" fill="currentColor" stroke="none" />
    </Svg>
  );
}

export function CategoryIcon({ id, className }: Props) {
  switch (id) {
    case "groceries":
      return (
        <Svg className={className}>
          <path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z" />
          <path d="M3 6h18" />
          <path d="M16 10a4 4 0 0 1-8 0" />
        </Svg>
      );
    case "household":
      return (
        <Svg className={className}>
          <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
          <path d="M9 22V12h6v10" />
        </Svg>
      );
    case "dining":
      return (
        <Svg className={className}>
          <path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2" />
          <path d="M7 2v20" />
          <path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7" />
        </Svg>
      );
    case "transport":
      return (
        <Svg className={className}>
          <path d="M19 17h2l.64-2.54A3 3 0 0 0 18.74 11H5.26a3 3 0 0 0-2.9 3.46L3 17h2" />
          <path d="M14 17H9" />
          <circle cx="7.5" cy="17.5" r="2.5" />
          <circle cx="16.5" cy="17.5" r="2.5" />
          <path d="M5 11V6a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v5" />
        </Svg>
      );
    case "rent":
      // Apartment / lease — not a key (old paths looked like ♂)
      return (
        <Svg className={className}>
          <path d="M3 21h18" />
          <path d="M5 21V8l7-5 7 5v13" />
          <path d="M9 21v-6h6v6" />
          <path d="M9 10h.01" />
          <path d="M15 10h.01" />
          <path d="M9 14h.01" />
          <path d="M15 14h.01" />
        </Svg>
      );
    case "utilities":
      return (
        <Svg className={className}>
          <path d="M13 2 3 14h9l-1 8 10-12h-9l1-8Z" />
        </Svg>
      );
    case "health":
      return (
        <Svg className={className}>
          <path d="M11 2a2 2 0 0 1 2 2v5h5a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2h-5v5a2 2 0 0 1-2 2h-2a2 2 0 0 1-2-2v-5H4a2 2 0 0 1-2-2v-2a2 2 0 0 1 2-2h5V4a2 2 0 0 1 2-2Z" />
        </Svg>
      );
    case "education":
      return (
        <Svg className={className}>
          <path d="M22 10 12 5 2 10l10 5 10-5Z" />
          <path d="M6 12v5c0 1.7 2.7 3 6 3s6-1.3 6-3v-5" />
          <path d="M22 10v6" />
        </Svg>
      );
    case "subscriptions":
      return (
        <Svg className={className}>
          <rect x="2" y="5" width="20" height="14" rx="2" />
          <path d="M2 10h20" />
        </Svg>
      );
    case "salary":
      return (
        <Svg className={className}>
          <rect x="2" y="7" width="20" height="14" rx="2" />
          <path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" />
          <path d="M12 12v4" />
          <path d="M10 14h4" />
        </Svg>
      );
    case "interest":
      return (
        <Svg className={className}>
          <path d="M12 2v4" />
          <path d="m4.9 4.9 2.8 2.8" />
          <path d="M2 12h4" />
          <path d="m4.9 19.1 2.8-2.8" />
          <path d="M12 18v4" />
          <path d="m19.1 19.1-2.8-2.8" />
          <path d="M18 12h4" />
          <path d="m19.1 4.9-2.8 2.8" />
          <circle cx="12" cy="12" r="3" />
        </Svg>
      );
    case "transfer":
      return (
        <Svg className={className}>
          <path d="m17 3 4 4-4 4" />
          <path d="M3 7h18" />
          <path d="m7 21-4-4 4-4" />
          <path d="M21 17H3" />
        </Svg>
      );
    case "other":
    case null:
    case undefined:
    case "":
      return <UnclearIcon className={className} />;
    default:
      return <UnclearIcon className={className} />;
  }
}
