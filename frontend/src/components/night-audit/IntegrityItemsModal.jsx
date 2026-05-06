import React from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { ArrowRight, AlertTriangle } from 'lucide-react';

const fmtMoney = (v) => {
  if (v == null) return '';
  try {
    return new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY' }).format(v);
  } catch {
    return `${v} TL`;
  }
};

function itemSubtitle(it, checkKey) {
  if (checkKey === 'negative_balance_folios') {
    return it.overpayment != null
      ? `Fazla ödeme: ${fmtMoney(it.overpayment)}`
      : it.balance != null ? `Bakiye: ${fmtMoney(it.balance)}` : '';
  }
  if (checkKey === 'voided_charges' || checkKey === 'closed_folio_charges') {
    const parts = [];
    if (it.amount != null) parts.push(fmtMoney(it.amount));
    if (it.description) parts.push(it.description);
    if (it.reason) parts.push(`Sebep: ${it.reason}`);
    return parts.join(' · ');
  }
  if (checkKey === 'room_rate_consistency') {
    return `Oda fiyatı: ${fmtMoney(it.rate || 0)}`;
  }
  return '';
}

function itemTitle(it) {
  if (it.guest_name) return it.guest_name;
  if (it.confirmation_code) return it.confirmation_code;
  const id = it.folio_id || it.booking_id;
  return id ? `#${String(id).slice(0, 8)}` : '—';
}

export default function IntegrityItemsModal({ open, onOpenChange, check, onPick }) {
  if (!check) return null;
  const items = check.items || [];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <AlertTriangle className="w-4 h-4 text-amber-500" />
            {check.label}
          </DialogTitle>
          <p className="text-xs text-gray-600 mt-1">{check.detail}</p>
          {check.count > items.length && (
            <p className="text-[11px] text-gray-400 mt-0.5">
              İlk {items.length} kayıt gösteriliyor (toplam {check.count})
            </p>
          )}
        </DialogHeader>
        <div className="max-h-[60vh] overflow-y-auto space-y-1.5 mt-2">
          {items.length === 0 ? (
            <p className="text-xs text-gray-500 text-center py-6">
              Detay bilgisi bulunamadı.
            </p>
          ) : items.map((it, idx) => {
            const sub = itemSubtitle(it, check.check);
            return (
              <button
                type="button"
                key={`${idx}-${it.folio_id || it.booking_id || ''}`}
                onClick={() => onPick && onPick(it)}
                data-testid={`integrity-item-${check.check}-${idx}`}
                className="w-full text-left flex items-center justify-between gap-2 px-3 py-2 rounded-md border bg-white hover:bg-indigo-50 hover:border-indigo-200 transition-colors"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-gray-900 truncate">
                      {itemTitle(it)}
                    </span>
                    {it.room_no && (
                      <span className="text-[11px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-700">
                        Oda {it.room_no}
                      </span>
                    )}
                  </div>
                  {sub && <p className="text-[11px] text-gray-500 mt-0.5 truncate">{sub}</p>}
                </div>
                <ArrowRight className="w-4 h-4 text-indigo-500 shrink-0" />
              </button>
            );
          })}
        </div>
      </DialogContent>
    </Dialog>
  );
}
