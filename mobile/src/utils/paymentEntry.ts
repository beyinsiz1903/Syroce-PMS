export type SimplePaymentMethod = 'cash' | 'card' | 'bank_transfer' | 'online';

export const SIMPLE_PAYMENT_METHODS: readonly SimplePaymentMethod[] = [
  'cash',
  'card',
  'bank_transfer',
  'online',
];

export function parsePaymentAmount(value: string): number | null {
  const normalized = value.trim().replace(/\s/g, '').replace(',', '.');
  if (!normalized) return null;
  const amount = Number(normalized);
  if (!/^\d+(?:\.\d{1,2})?$/.test(normalized) || !Number.isFinite(amount) || amount <= 0) return null;
  return Math.round(amount * 100) / 100;
}

export function paymentTypeForAmount(amount: number, balance: number): 'interim' | 'final' {
  return amount + 0.005 >= balance ? 'final' : 'interim';
}

export type PaymentAttempt = {
  fingerprint: string;
  key: string;
  paymentType: 'interim' | 'final';
};

// A response can be lost after the payment is committed. Its new balance must
// not turn an interim retry into a new final-payment request/key.
export function paymentAttemptForInput(
  previous: PaymentAttempt | null,
  input: { bookingId: string; amount: number; method: SimplePaymentMethod; currency: string; balance: number },
  makeKey: () => string,
): PaymentAttempt {
  const fingerprint = `${input.bookingId}|${input.currency}|${input.amount}|${input.method}`;
  if (previous?.fingerprint === fingerprint) return previous;
  return { fingerprint, key: makeKey(), paymentType: paymentTypeForAmount(input.amount, input.balance) };
}

export function paymentAmountError(
  amount: number | null,
  balance: number | undefined,
): 'invalid' | 'unknown_balance' | 'no_balance' | 'overpayment' | null {
  if (amount === null || !Number.isFinite(amount) || amount <= 0) return 'invalid';
  if (balance === undefined || !Number.isFinite(balance)) return 'unknown_balance';
  if (balance <= 0) return 'no_balance';
  if (amount - balance > 0.005) return 'overpayment';
  return null;
}
