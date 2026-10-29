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
