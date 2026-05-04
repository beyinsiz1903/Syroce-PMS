export function formatCurrency(amount: number | undefined | null, currency = 'TRY'): string {
  const n = typeof amount === 'number' ? amount : 0;
  try {
    return new Intl.NumberFormat('tr-TR', { style: 'currency', currency }).format(n);
  } catch {
    return `${n.toFixed(2)} ${currency}`;
  }
}

export function formatDate(value: string | Date | undefined | null): string {
  if (!value) return '-';
  try {
    const d = typeof value === 'string' ? new Date(value) : value;
    return d.toLocaleDateString('tr-TR', { day: '2-digit', month: 'short', year: 'numeric' });
  } catch {
    return String(value);
  }
}

export function formatTime(value: string | Date | undefined | null): string {
  if (!value) return '-';
  try {
    const d = typeof value === 'string' ? new Date(value) : value;
    return d.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
  } catch {
    return String(value);
  }
}
