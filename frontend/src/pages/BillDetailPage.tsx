import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { CategoryChip, CategoryPicker } from "../components/CategoryPicker";
import { SourceLogo } from "../components/SourceLogo";
import { formatEntryQty, formatMoney } from "../lib/format";
import type { Bill, CategoryItem, Entry, Vocabulary } from "../types";

export function BillDetailPage() {
  const { billId } = useParams();
  const navigate = useNavigate();
  const [bill, setBill] = useState<Bill | null>(null);
  const [vocab, setVocab] = useState<Vocabulary | null>(null);
  const [error, setError] = useState("");

  const reload = useCallback(() => {
    if (!billId) return Promise.resolve();
    return api<{ bill: Bill }>(`/api/v1/bills/${billId}`).then((d) => setBill(d.bill));
  }, [billId]);

  useEffect(() => {
    reload().catch(() => setError("账单不存在或加载失败"));
    api<Vocabulary>("/api/v1/categories")
      .then(setVocab)
      .catch(() => undefined);
  }, [reload]);

  async function remove() {
    if (!bill || bill.source_type !== "manual") return;
    if (!confirm("删除这笔账单？")) return;
    await api(`/api/v1/bills/${bill.id}`, { method: "DELETE" });
    navigate("/bills");
  }

  if (error) {
    return (
      <div className="space-y-4">
        <Link to="/bills" className="text-sm text-ink-600 hover:text-ink-800">
          ← 返回流水
        </Link>
        <p className="text-red-700">{error}</p>
      </div>
    );
  }

  if (!bill) {
    return <p className="text-ink-400">加载中…</p>;
  }

  const catMap = Object.fromEntries(
    (vocab?.categories || []).map((c) => [c.id, c.label]),
  );

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link to="/bills" className="text-sm text-ink-600 hover:text-ink-800">
            ← 返回流水
          </Link>
          <div className="mt-3 flex items-center gap-3">
            <SourceLogo source={bill.source_type} className="h-9 w-9" />
            <h1 className="font-display text-3xl text-ink-800">
              {bill.merchant || "未命名商户"}
            </h1>
          </div>
          <p className="mt-2 text-ink-500">
            {new Date(bill.occurred_at).toLocaleString()}
          </p>
          {bill.note && <p className="mt-2 text-sm text-ink-400">{bill.note}</p>}
        </div>
        <div className="text-right">
          <p className="font-display text-3xl text-ink-700">
            {formatMoney(bill.total_amount, bill.currency)}
          </p>
          {bill.source_type === "manual" && (
            <button
              type="button"
              onClick={remove}
              className="mt-3 text-sm text-ink-400 hover:text-red-700"
            >
              删除
            </button>
          )}
        </div>
      </div>

      <section>
        <h2 className="font-display text-xl text-ink-800">明细</h2>
        <ul className="mt-2 divide-y divide-ink-100">
          {bill.entries.map((e) => (
            <EntryRow
              key={e.id}
              entry={e}
              currency={bill.currency}
              categories={vocab?.categories || []}
              catMap={catMap}
              onUpdated={reload}
            />
          ))}
        </ul>
        {bill.entries.length === 0 && (
          <p className="mt-4 text-ink-400">没有明细条目</p>
        )}
      </section>
    </div>
  );
}

function EntryRow({
  entry,
  currency,
  categories,
  catMap,
  onUpdated,
}: {
  entry: Entry;
  currency: string;
  categories: CategoryItem[];
  catMap: Record<string, string>;
  onUpdated: () => Promise<void>;
}) {
  const onSpecial = Number(entry.discount) > 0;
  const [pickerOpen, setPickerOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function selectCategory(categoryId: string | null) {
    setBusy(true);
    setErr("");
    try {
      await api(`/api/v1/entries/${entry.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          category_id: categoryId,
          confirm: Boolean(categoryId),
        }),
      });
      setPickerOpen(false);
      await onUpdated();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  const label = entry.category_id
    ? catMap[entry.category_id] || entry.category_id
    : "未分类";
  const pending = entry.classification_status === "pending";

  return (
    <li className="py-5">
      <div className="flex items-start gap-3 sm:items-center sm:gap-5">
        <ProductThumb src={entry.image_url} alt={entry.name} />
        <div className="min-w-0 flex-1">
          <p className="font-medium text-ink-800">{entry.name}</p>
          <p className="mt-1 text-sm text-ink-400">{formatEntryQty(entry.quantity)}</p>
          <CategoryChip
            categoryId={entry.category_id}
            label={label}
            pending={pending}
            onClick={() => setPickerOpen(true)}
          />
          {err && <p className="mt-1 text-sm text-red-700">{err}</p>}
        </div>
        <div className="shrink-0 text-right">
          <p className="font-medium tabular-nums text-ink-800">
            {formatMoney(entry.amount, currency)}
          </p>
          {onSpecial && (
            <span className="mt-1 inline-block rounded bg-[#FFE600] px-2 py-0.5 text-xs font-semibold text-ink-900">
              Special
            </span>
          )}
        </div>
      </div>

      <CategoryPicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        categories={categories}
        value={entry.category_id}
        onSelect={selectCategory}
        busy={busy}
      />
    </li>
  );
}

function ProductThumb({ src, alt }: { src?: string | null; alt: string }) {
  return (
    <div className="h-20 w-20 shrink-0 overflow-hidden rounded-md bg-ink-50 ring-1 ring-ink-100 sm:h-28 sm:w-28">
      {src ? (
        <img src={src} alt={alt} className="h-full w-full object-contain" loading="lazy" />
      ) : (
        <div className="flex h-full w-full items-center justify-center text-xs text-ink-300">
          —
        </div>
      )}
    </div>
  );
}
