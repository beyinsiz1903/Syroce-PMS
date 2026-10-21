import { formatCurrency } from '@/lib/currency';

export default function QuoteTotals({ totals = {}, currency }) {
  return <dl className="space-y-1 text-sm">
    {[
      ['space_total', 'Salon'], ['resources_total', 'Kaynaklar'],
      ['subtotal', 'Ara toplam'], ['discount_total', 'İndirim (−)'],
      ['net_total', 'İndirim sonrası net'], ['service_total', 'Servis (+)'],
      ['tax_total', 'Vergi (+)'], ['grand_total', 'Ödenecek toplam'],
    ].filter(([key]) => totals[key] != null).map(([key, label]) => <div key={key} className={`flex justify-between gap-4 ${key === 'grand_total' ? 'border-t pt-2 font-bold' : ''}`}>
      <dt>{label}</dt><dd>{formatCurrency(totals[key], currency)}</dd>
    </div>)}
  </dl>;
}
