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
  return Number.isFinite(amount) && amount > 0 ? Math.round(amount * 100) / 100 : null;
}

export function paymentTypeForAmount(amount: number, balance: number): 'interim' | 'final' {
  return amount + 0.005 >= balance ? 'final' : 'interim';
}

export function paymentAmountError(
  amount: number | null,
  balance: number,
): 'invalid' | 'overpayment' | null {
  if (amount === null || amount <= 0) return 'invalid';
  if (balance > 0 && amount - balance > 0.005) return 'overpayment';
  return null;
}
