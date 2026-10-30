/** Whole-number quantity → count; fractional → weighed (3 dp). */
export function isWeighedQuantity(quantity: string | number): boolean {
  const n = Number(quantity);
  if (!Number.isFinite(n)) return false;
  return Math.abs(n - Math.round(n)) > 1e-9;
}

export function formatEntryQty(quantity: string | number): string {
  const n = Number(quantity);
  if (!Number.isFinite(n)) return String(quantity);
  if (isWeighedQuantity(n)) {
    return `Weight: ${n.toFixed(3)}`;
  }
  return `Quantity: ${Math.round(n)}`;
}

export function formatMoney(
  amount: string | number,
  currency = "AUD",
): string {
  const n = Number(amount);
  if (!Number.isFinite(n)) return String(amount);
  return n.toLocaleString("en-AU", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/**
 * Date-only values are stored as midnight UTC → calendar date only.
 * Otherwise show local date + time (BankSync providerPostingDateTime, Coles, etc.).
 */
export function formatOccurredAt(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const isDateOnlyUtc =
    d.getUTCHours() === 0 &&
    d.getUTCMinutes() === 0 &&
    d.getUTCSeconds() === 0 &&
    d.getUTCMilliseconds() === 0;
  if (isDateOnlyUtc) {
    return d.toLocaleDateString("en-AU", {
      timeZone: "UTC",
      year: "numeric",
      month: "numeric",
      day: "numeric",
    });
  }
  return d.toLocaleString("en-AU", {
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** Income category ids — keep in sync with config/categories.yaml + analytics.INCOME_IDS */
export const INCOME_CATEGORY_IDS = new Set([
  "salary",
  "interest",
  // Legacy ids until rows are reclassified
  "income",
  "income_other",
]);

export function isIncomeCategory(categoryId?: string | null): boolean {
  return Boolean(categoryId && INCOME_CATEGORY_IDS.has(categoryId));
}

/** Bill is income when every entry with a category is income (or sole entry is income). */
export function billLooksLikeIncome(
  entries: { category_id?: string | null }[] | undefined,
): boolean {
  if (!entries?.length) return false;
  const withCat = entries.filter((e) => e.category_id);
  if (withCat.length === 0) return false;
  return withCat.every((e) => isIncomeCategory(e.category_id));
}

export function moneyClass(isIncome: boolean): string {
  return isIncome ? "text-emerald-700" : "text-ink-800";
}

export function formatMoneySigned(
  amount: string | number,
  currency = "AUD",
  opts: { income: boolean },
): string {
  const base = formatMoney(amount, currency);
  return opts.income ? `+${base}` : base;
}
