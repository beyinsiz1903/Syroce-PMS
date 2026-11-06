import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Loader2, Save, ShieldCheck } from 'lucide-react';

const priceLabel = price => {
  if (price.kind === 'adult_main') return `${price.number_of_guests} yetişkin · oda/gece`;
  const age = price.min_age === undefined ? '' : ` · ${price.min_age}–${price.max_age - 1} yaş`;
  if (price.kind === 'child_main') return `Çocuk · ana yatak${age} · çocuk/gece`;
  if (price.kind === 'adult_extra') return 'Yetişkin · ek yatak · kişi/gece';
  if (price.kind === 'child_extra') return `Çocuk · ek yatak${age} · çocuk/gece`;
  if (price.kind === 'child_without_bed') return `Çocuk · yataksız${age} · çocuk/gece`;
  return 'Oda/gece';
};
const amountLabel = (amount, currency) => `${new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2 }).format(amount)}${currency ? ` ${currency}` : ''}`;
const dateLabel = value => {
  const date = new Date(`${value}T12:00:00Z`);
  return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(date);
};

export const RatePublishReview = ({ review, saving, onClose, onPublish }) => (
  <Card className="mt-4 border-slate-200 bg-white" role="dialog" aria-labelledby="rate-review-title" data-testid="rate-publish-review">
    <CardHeader className="pb-2">
      <div className="flex items-start justify-between gap-3">
        <div>
          <CardTitle id="rate-review-title" className="flex items-center gap-2 text-base text-slate-900">
            <ShieldCheck className="h-5 w-5 text-blue-600" /> Gönderim özeti
          </CardTitle>
          <p className="mt-1 text-xs text-slate-600">Seçtiğiniz odaları, tarihleri ve değişiklikleri kontrol edin.</p>
          <p className="mt-2 text-sm font-medium text-slate-800">{dateLabel(review.dateFrom)} – {dateLabel(review.dateTo)}</p>
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>Kapat</Button>
      </div>
    </CardHeader>
    <CardContent className="space-y-4">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        {[
          ['Gece', review.dateCount], ['Oda tipi', review.roomCount], ['Fiyat planı', review.planCount],
          ['Güncellenecek alan', review.fieldCount], ['Gönderim', review.targetLabel],
        ].map(([label, value]) => (
          <div key={label} className="min-w-0 rounded-lg bg-slate-50 px-3 py-2">
            <div className="text-[11px] text-slate-500">{label}</div><div className="mt-1 break-words text-sm font-semibold text-slate-900">{value}</div>
          </div>
        ))}
      </div>
      {review.priceSummaries.length > 0 && <div className="grid gap-3 sm:grid-cols-2" aria-label="Güncellenecek fiyatlar">
        {review.priceSummaries.map(room => <section key={room.roomCode} className="min-w-0 rounded-lg border border-slate-200 p-3" aria-label={`${room.roomName} fiyat özeti`}>
          <h4 className="break-words text-sm font-semibold text-slate-900">{room.roomName}</h4>
          <p className="mt-1 break-words text-xs text-slate-500">{room.planNames.length ? room.planNames.join(' · ') : `${room.planCount} fiyat planı`}</p>
          <ul className="mt-3 space-y-2">
            {room.prices.map((price, index) => <li key={index} className="flex items-start justify-between gap-3 text-sm">
              <span className="min-w-0 text-slate-600">{priceLabel(price)}</span>
              <span className="shrink-0 font-semibold tabular-nums text-slate-900">{amountLabel(price.amount, room.currency)}</span>
            </li>)}
          </ul>
        </section>)}
      </div>}
      {review.notes.length > 0 && <ul className="space-y-1 text-xs leading-5 text-slate-600" aria-label="Gönderim kapsamı">
        {review.notes.map(note => <li key={note}>{note}</li>)}
      </ul>}
      {review.errors.length > 0 && <div className="rounded-lg border border-red-200 bg-red-50 p-3" role="alert">
        <div className="text-sm font-semibold text-red-800">Yayınlamadan önce düzeltin</div>
        <ul className="mt-1 list-disc space-y-1 pl-5 text-xs text-red-700">{review.errors.map(error => <li key={error}>{error}</li>)}</ul>
      </div>}
      {review.warnings.length > 0 && <div className="rounded-lg border border-amber-200 bg-amber-50 p-3" data-testid="rate-review-warnings">
        <div className="text-sm font-semibold text-amber-900">Dikkat edilmesi gerekenler</div>
        <ul className="mt-1 list-disc space-y-1 pl-5 text-xs text-amber-800">{review.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
      </div>}
      <div className="flex flex-wrap items-center justify-end gap-3 border-t border-slate-100 pt-3">
        <Button type="button" className="w-full bg-blue-700 text-white hover:bg-blue-800 sm:w-auto"
          disabled={saving || review.errors.length > 0} onClick={onPublish} data-testid="rate-confirm-publish">
          {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Save className="mr-1.5 h-4 w-4" />}
          Kontrol ettim, yayınla
        </Button>
      </div>
    </CardContent>
  </Card>
);
