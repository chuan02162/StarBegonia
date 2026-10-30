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
 * Otherwise show local date + time (provider posting date, Coles, etc.).
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

/** Money-in when amount &gt; 0 (bank sign). Category is separate (Jev). */
export function isIncomeAmount(amount?: string | number | null): boolean {
  const n = Number(amount);
  return Number.isFinite(n) && n > 0;
}

/** Bill is income when net total &gt; 0. */
export function billLooksLikeIncome(
  entries: { amount?: string | number | null }[] | undefined,
  totalAmount?: string | number | null,
): boolean {
  if (totalAmount != null && totalAmount !== "") {
    return isIncomeAmount(totalAmount);
  }
  if (!entries?.length) return false;
  const sum = entries.reduce((acc, e) => acc + (Number(e.amount) || 0), 0);
  return sum > 0;
}

export function moneyClass(isIncome: boolean): string {
  return isIncome ? "text-emerald-700" : "text-ink-800";
}

/** Show signed money: +$x for credits, -$x for debits (abs formatting + sign). */
export function formatMoneySigned(
  amount: string | number,
  currency = "AUD",
  opts?: { income?: boolean },
): string {
  const n = Number(amount);
  if (!Number.isFinite(n)) return String(amount);
  const income = opts?.income ?? n > 0;
  const base = formatMoney(Math.abs(n), currency);
  if (n === 0) return base;
  return income ? `+${base}` : `-${base}`;
}
