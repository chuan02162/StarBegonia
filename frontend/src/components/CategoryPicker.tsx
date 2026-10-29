import { useEffect, useRef } from "react";
import { CategoryIcon } from "./CategoryIcon";
import type { CategoryItem } from "../types";

type Props = {
  open: boolean;
  onClose: () => void;
  categories: CategoryItem[];
  value: string | null | undefined;
  onSelect: (categoryId: string | null) => void;
  busy?: boolean;
};

export function CategoryPicker({
  open,
  onClose,
  categories,
  value,
  onSelect,
  busy,
}: Props) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-ink-900/30 p-4 sm:items-center"
      onClick={onClose}
      role="presentation"
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal
        aria-label="选择分类"
        className="max-h-[80vh] w-full max-w-md overflow-hidden rounded-xl bg-white shadow-lg ring-1 ring-ink-100 animate-[fadeIn_0.2s_ease]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-ink-100 px-4 py-3">
          <p className="font-display text-lg text-ink-800">选择分类</p>
          <button
            type="button"
            className="text-sm text-ink-400 hover:text-ink-700"
            onClick={onClose}
          >
            关闭
          </button>
        </div>
        <ul className="max-h-[min(60vh,28rem)] overflow-y-auto py-1">
          <li>
            <button
              type="button"
              disabled={busy}
              onClick={() => onSelect(null)}
              className={`flex w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-ink-50 ${
                !value ? "bg-ink-50 text-ink-800" : "text-ink-600"
              }`}
            >
              <span className="flex h-9 w-9 items-center justify-center rounded-md bg-ink-50 text-ink-400 ring-1 ring-ink-100">
                <CategoryIcon id={null} className="h-5 w-5" />
              </span>
              <span>未分类</span>
            </button>
          </li>
          {categories.map((c) => {
            const selected = value === c.id;
            return (
              <li key={c.id}>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => onSelect(c.id)}
                  className={`flex w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-ink-50 ${
                    selected ? "bg-ink-50 text-ink-800" : "text-ink-700"
                  }`}
                >
                  <span className="flex h-9 w-9 items-center justify-center rounded-md bg-ink-50 text-ink-700 ring-1 ring-ink-100">
                    <CategoryIcon id={c.id} className="h-5 w-5" />
                  </span>
                  <span className="font-medium">{c.label}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

export function CategoryChip({
  categoryId,
  label,
  onClick,
  pending,
}: {
  categoryId: string | null | undefined;
  label: string;
  onClick: () => void;
  pending?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="mt-1 inline-flex max-w-full items-center gap-1.5 rounded-md bg-ink-50 px-2 py-1 text-sm text-ink-700 ring-1 ring-ink-100 transition hover:bg-ink-100 hover:ring-ink-200"
    >
      <CategoryIcon id={categoryId} className="h-4 w-4 shrink-0 text-ink-600" />
      <span className="truncate">{label}</span>
      {pending && <span className="shrink-0 text-xs text-amber-700">待确认</span>}
    </button>
  );
}
