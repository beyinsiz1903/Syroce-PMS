import { finiteMoney, reservationCollectedAmount, reservationCurrency } from './reservationPresentation';

type Movement = { amount?: unknown; total?: unknown; currency?: string; voided?: boolean; method?: string; status?: string; payment_type?: string };
export type FolioEntry = {
  id?: string; status?: string; currency?: string; balance?: unknown;
  charges?: Movement[]; payments?: Movement[];
};

// The server balance is authoritative. Missing data is never a settled zero,
// and a mixed-currency scalar is not a safe amount to collect on a phone.
export function folioEntrySummary(folio?: FolioEntry | null) {
  const currency = reservationCurrency(folio?.currency);
  const movements = [...(folio?.charges || []), ...(folio?.payments || [])].filter(x => !x.voided);
  const currencyConflict = movements.some(x => x.currency != null && reservationCurrency(x.currency) !== currency);
  const balance = currencyConflict ? undefined : finiteMoney(folio?.balance);
  const activeCharges = folio?.charges?.filter(x => !x.voided);
  const amounts = activeCharges?.map(x => finiteMoney(x.total ?? x.amount));
  const chargesTotal = !currencyConflict && amounts && amounts.every(x => x !== undefined)
    ? amounts.reduce<number>((sum, x) => sum + (x as number), 0) : undefined;
  const paymentsTotal = currencyConflict ? undefined : reservationCollectedAmount(folio?.payments, currency);
  return { currency, balance, currencyConflict, chargesTotal, paymentsTotal,
    writable: !!folio?.id && folio.status?.toLowerCase() === 'open' && !!currency && balance !== undefined && !currencyConflict };
}

export type WriteAttempt = { fingerprint: string; key: string };

// Preserve a committed-but-lost response's key across sheet close/reopen;
// changed input is a different intent and must not replay the former write.
export function folioWriteAttempt(previous: WriteAttempt | null, input: object, makeKey: () => string): WriteAttempt {
  const fingerprint = JSON.stringify(input);
  return previous?.fingerprint === fingerprint ? previous : { fingerprint, key: makeKey() };
}
