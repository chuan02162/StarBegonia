import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import type { CategoryItem } from "../types";

type DraftEntry = {
  name: string;
  amount: string;
  category_id: string;
};

export function NewBillPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [merchant, setMerchant] = useState("");
  const [occurredAt, setOccurredAt] = useState(
    () => new Date().toISOString().slice(0, 16),
  );
  const [currency, setCurrency] = useState("AUD");
  const [note, setNote] = useState("");
  const [entries, setEntries] = useState<DraftEntry[]>([
    { name: "", amount: "", category_id: "" },
  ]);
  const [categories, setCategories] = useState<CategoryItem[]>([]);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api<{ categories: CategoryItem[] }>("/api/v1/categories").then((d) =>
      setCategories(d.categories || []),
    );
  }, []);

  function updateEntry(i: number, patch: Partial<DraftEntry>) {
    setEntries((prev) => prev.map((e, idx) => (idx === i ? { ...e, ...patch } : e)));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await api("/api/v1/bills", {
        method: "POST",
        body: JSON.stringify({
          person_id: user?.person?.id,
          merchant: merchant || null,
          occurred_at: new Date(occurredAt).toISOString(),
          currency,
          note: note || null,
          entries: entries.map((en) => ({
            name: en.name,
            amount: en.amount,
            category_id: en.category_id || null,
          })),
        }),
      });
      navigate("/bills");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "保存失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-xl space-y-8">
      <div>
        <h1 className="font-display text-3xl text-ink-800">手动记账</h1>
        <p className="mt-2 text-ink-500">一笔账单，可含多条明细</p>
      </div>

      <form onSubmit={onSubmit} className="space-y-6">
        <label className="block">
          <span className="mb-1.5 block text-sm text-ink-600">商户</span>
          <input className="field" value={merchant} onChange={(e) => setMerchant(e.target.value)} />
        </label>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1.5 block text-sm text-ink-600">时间</span>
            <input
              className="field"
              type="datetime-local"
              value={occurredAt}
              onChange={(e) => setOccurredAt(e.target.value)}
              required
            />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-sm text-ink-600">币种</span>
            <input
              className="field"
              value={currency}
              onChange={(e) => setCurrency(e.target.value.toUpperCase())}
              required
            />
          </label>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-ink-600">明细</span>
            <button
              type="button"
              className="text-sm text-ink-700"
              onClick={() =>
                setEntries((prev) => [...prev, { name: "", amount: "", category_id: "" }])
              }
            >
              + 添加行
            </button>
          </div>
          {entries.map((en, i) => (
            <div key={i} className="grid gap-2 sm:grid-cols-[1fr_7rem_9rem_auto]">
              <input
                className="field"
                placeholder="名称"
                value={en.name}
                onChange={(e) => updateEntry(i, { name: e.target.value })}
                required
              />
              <input
                className="field"
                placeholder="金额"
                inputMode="decimal"
                value={en.amount}
                onChange={(e) => updateEntry(i, { amount: e.target.value })}
                required
              />
              <select
                className="field"
                value={en.category_id}
                onChange={(e) => updateEntry(i, { category_id: e.target.value })}
              >
                <option value="">分类（可选）</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="text-sm text-ink-400 hover:text-red-700"
                onClick={() => setEntries((prev) => prev.filter((_, idx) => idx !== i))}
                disabled={entries.length === 1}
              >
                移除
              </button>
            </div>
          ))}
        </div>

        <label className="block">
          <span className="mb-1.5 block text-sm text-ink-600">备注</span>
          <textarea
            className="field min-h-[5rem]"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>

        {error && <p className="text-sm text-red-700">{error}</p>}
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? "保存中…" : "保存"}
        </button>
      </form>
    </div>
  );
}
