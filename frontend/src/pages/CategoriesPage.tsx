import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { CategoryChip, CategoryPicker } from "../components/CategoryPicker";
import { SourceLogo } from "../components/SourceLogo";
import { formatMoney, formatOccurredAt } from "../lib/format";
import type { CategoryItem, PendingEntry, Vocabulary } from "../types";

export function CategoriesPage() {
  const [pending, setPending] = useState<PendingEntry[]>([]);
  const [vocab, setVocab] = useState<Vocabulary | null>(null);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [pickerEntry, setPickerEntry] = useState<PendingEntry | null>(null);
  const [batchMsg, setBatchMsg] = useState("");

  const load = useCallback(() => {
    return Promise.all([
      api<{ entries: PendingEntry[] }>("/api/v1/categories/pending"),
      api<Vocabulary>("/api/v1/categories"),
    ]).then(([p, v]) => {
      setPending(p.entries);
      setVocab(v);
    });
  }, []);

  useEffect(() => {
    load().catch(() => setError("加载失败"));
  }, [load]);

  async function selectCategory(categoryId: string | null) {
    if (!pickerEntry) return;
    setBusyId(pickerEntry.id);
    setError("");
    try {
      await api(`/api/v1/entries/${pickerEntry.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          category_id: categoryId,
          confirm: Boolean(categoryId),
        }),
      });
      setPickerEntry(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "确认失败");
    } finally {
      setBusyId(null);
    }
  }

  async function runBatch() {
    setBatchMsg("排队分类中…");
    setError("");
    try {
      const res = await api<{ job_id?: string; classified?: number; status?: string }>(
        "/api/v1/categories/classify",
        {
          method: "POST",
          body: JSON.stringify({
            // Re-run current pending rows (name may have been fixed to merchant).
            entry_ids: pending.map((e) => e.id),
            only_unclassified: false,
            limit: Math.max(pending.length, 40),
            async: true,
          }),
        },
      );
      if (res.job_id) {
        setBatchMsg(`已排队 job ${res.job_id}，稍后刷新`);
      } else {
        setBatchMsg(`已分类 ${res.classified ?? 0} 条`);
        await load();
      }
    } catch (err) {
      setBatchMsg("");
      setError(err instanceof ApiError ? err.message : "批量分类失败");
    }
  }

  const catLabel = (id: string | null | undefined) =>
    vocab?.categories.find((c) => c.id === id)?.label || id || "未分类";

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl text-ink-800">分类待确认</h1>
          <p className="mt-2 text-ink-500">
            Jev 低置信度建议，点击分类改选并确认
          </p>
        </div>
        <button type="button" className="btn-ghost" onClick={runBatch}>
          对未分类条目跑 Jev
        </button>
      </div>

      {batchMsg && <p className="text-sm text-ink-500">{batchMsg}</p>}
      {error && <p className="text-sm text-red-700">{error}</p>}

      <ul className="divide-y divide-ink-100">
        {pending.map((e) => (
          <PendingRow
            key={e.id}
            entry={e}
            label={catLabel(e.category_id)}
            onOpenPicker={() => setPickerEntry(e)}
          />
        ))}
      </ul>
      {pending.length === 0 && !error && (
        <p className="text-ink-400">没有待确认的分类</p>
      )}

      <CategoryPicker
        open={Boolean(pickerEntry)}
        onClose={() => setPickerEntry(null)}
        categories={(vocab?.categories || []) as CategoryItem[]}
        value={pickerEntry?.category_id}
        onSelect={selectCategory}
        busy={busyId === pickerEntry?.id}
      />
    </div>
  );
}

function PendingRow({
  entry,
  label,
  onOpenPicker,
}: {
  entry: PendingEntry;
  label: string;
  onOpenPicker: () => void;
}) {
  const conf = entry.category_confidence
    ? `${(Number(entry.category_confidence) * 100).toFixed(0)}%`
    : "—";

  return (
    <li className="py-6">
      <div className="flex flex-wrap items-start gap-4">
        {entry.bill && (
          <SourceLogo source={entry.bill.source_type} className="mt-1 h-8 w-8" />
        )}
        <div className="min-w-0 flex-1 space-y-2">
          <div>
            <p className="font-medium text-ink-800">{entry.name}</p>
            <p className="mt-1 text-sm text-ink-400">
              {entry.bill ? (
                <>
                  <Link
                    to={`/bills/${entry.bill.id}`}
                    className="text-ink-600 hover:text-ink-800"
                  >
                    {entry.bill.merchant || "账单"}
                  </Link>
                  {" · "}
                  {formatOccurredAt(entry.bill.occurred_at)}
                  {" · "}
                  {formatMoney(entry.amount, entry.bill.currency)}
                </>
              ) : (
                formatMoney(entry.amount, entry.currency)
              )}
            </p>
            <p className="mt-1 text-sm text-ink-400">置信度 {conf}</p>
          </div>
          <CategoryChip
            categoryId={entry.category_id}
            label={label}
            pending
            onClick={onOpenPicker}
          />
        </div>
      </div>
    </li>
  );
}
