import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Plus, Trash2 } from 'lucide-react';
import { Field, Modal } from '../_shared';
import OperationsPanel from '../OperationsPanel';
import QuoteTotals from '../QuoteTotals';
import { STATUS, SETUPS, EVENT_TYPES, EVENT_TYPE_LABELS, AGENDA_KINDS } from './constants';
import { cachedTenantCurrency, formatCurrency } from '@/lib/currency';
const EventFormModal = ({
  editing,
  form,
  setForm,
  eventTab,
  setEventTab,
  accounts,
  accountById,
  spaces,
  menus,
  resources,
  psTotal,
  addSb,
  setSb,
  rmSb,
  addRes,
  setRes,
  rmRes,
  addAg,
  setAg,
  rmAg,
  addPs,
  setPs,
  rmPs,
  submit,
  saving = false,
  previewQuote,
  quotePreview,
  onClose
}) => <Modal title={editing ? 'Etkinlik Düzenle' : 'Yeni Etkinlik'} onClose={onClose} wide>
    <form noValidate onSubmit={submit} className="space-y-3">
      {editing && form.space_bookings.some(b => b.space_id && !b.rate_snapshot) && <p className="rounded border p-2 text-xs text-muted-foreground">Bu eski kaydın bazı salon tarifeleri saklanmamış. Düzenlemede güncel katalog tarifesi uygulanır; kaydetmeden önce Tutarı Hesapla ile kontrol edin.</p>}
      <Tabs value={eventTab} onValueChange={setEventTab}>
        <TabsList className="h-auto flex-wrap">
          <TabsTrigger value="basics">Temel</TabsTrigger>
          <TabsTrigger value="spaces">Mekan & Kaynak</TabsTrigger>
          <TabsTrigger value="agenda">Fonksiyon Sheet</TabsTrigger>
          <TabsTrigger value="operations">Operasyon</TabsTrigger>
          <TabsTrigger value="payment">Ödeme Takvimi</TabsTrigger>
          <TabsTrigger value="pricing">Fiyatlandırma</TabsTrigger>
        </TabsList>

        <TabsContent value="basics" className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <Field label="Etkinlik Adı"><Input required value={form.name} onChange={e => setForm({
              ...form,
              name: e.target.value
            })} /></Field>
            <Field label="Müşteri Adı"><Input required value={form.client_name} onChange={e => setForm({
              ...form,
              client_name: e.target.value
            })} /></Field>
            <Field label="Kurumsal Hesap (opsiyonel)">
              <select className="w-full border rounded px-2 py-1.5" value={form.client_account_id} onChange={e => {
              const id = e.target.value;
              const acct = accountById[id];
              setForm({
                ...form,
                client_account_id: id,
                client_name: acct?.name || form.client_name
              });
            }}>
                <option value="">— Seçilmedi —</option>
                {accounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </Field>
            <Field label="Organizatör Kullanıcı"><Input value={form.organizer_user} onChange={e => setForm({
              ...form,
              organizer_user: e.target.value
            })} /></Field>
            <Field label="Müşteri E-posta"><Input value={form.client_email} onChange={e => setForm({
              ...form,
              client_email: e.target.value
            })} /></Field>
            <Field label="Müşteri Telefon"><Input value={form.client_phone} onChange={e => setForm({
              ...form,
              client_phone: e.target.value
            })} /></Field>
            <Field label="Tip">
              <select className="w-full border rounded px-2 py-1.5" value={form.event_type} onChange={e => setForm({
              ...form,
              event_type: e.target.value
            })}>
                {EVENT_TYPES.map(t => <option key={t} value={t}>{EVENT_TYPE_LABELS[t] || t}</option>)}
              </select>
            </Field>
            <Field label="Durum">
              <select disabled={Boolean(editing)} className="w-full border rounded px-2 py-1.5" value={form.status} onChange={e => setForm({
              ...form,
              status: e.target.value
            })}>
                {Object.entries(STATUS).filter(([key]) => editing || !['completed', 'cancelled'].includes(key)).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </select>
              {editing && <p className="text-xs text-muted-foreground">Durum, etkinlik listesindeki geçerli adımlarla değiştirilir.</p>}
            </Field>
            <Field label="Beklenen Pax"><Input type="number" min="0" required value={form.expected_pax} onChange={e => setForm({
              ...form,
              expected_pax: +e.target.value
            })} /></Field>
            <Field label="Para Birimi">
              <Input required maxLength={3} value={form.currency || cachedTenantCurrency()} onChange={e => setForm({
                ...form,
                currency: e.target.value.toUpperCase()
              })} />
            </Field>
            <Field label="PMS Rezervasyon ID"><Input value={form.reservation_id} onChange={e => setForm({
              ...form,
              reservation_id: e.target.value
            })} /></Field>
            <Field label="Başlangıç Tarihi"><Input type="date" required value={form.start_date} onChange={e => setForm({
              ...form,
              start_date: e.target.value
            })} /></Field>
            <Field label="Bitiş Tarihi"><Input type="date" min={form.start_date} required value={form.end_date} onChange={e => setForm({
              ...form,
              end_date: e.target.value
            })} /></Field>
          </div>
          <Field label="Notlar">
            <textarea className="w-full border rounded px-2 py-1.5 text-sm min-h-[60px]" value={form.notes} onChange={e => setForm({
            ...form,
            notes: e.target.value
          })} />
          </Field>
        </TabsContent>

        <TabsContent value="spaces" className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
          <div>
            <div className="flex items-center justify-between mb-2">
              <Label className="text-sm font-semibold">Mekan Rezervasyonları</Label>
              <Button type="button" size="sm" variant="outline" onClick={addSb}>
                <Plus className="w-3 h-3 mr-1" /> Mekan Ekle
              </Button>
            </div>
            <p className="mb-2 text-xs text-muted-foreground">Kurulum ve söküm tamponları salon/stok müsaitliğini bloke eder; kira yalnız servis süresinden hesaplanır. Saatleri tesisin yerel saatine göre girin.</p>
            {form.space_bookings.map((sb, i) => <div key={sb.id || i} className="grid grid-cols-12 gap-1 mb-3 items-center rounded border p-2">
                <select className="col-span-3 border rounded px-1 py-1 text-xs" value={sb.space_id} onChange={e => setSb(i, {
              space_id: e.target.value
            })}>
                  <option value="">Mekan…</option>
                  {spaces.filter(s => s.active !== false || s.id === sb.space_id).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
                <Input className="col-span-3 text-xs" type="datetime-local" value={sb.starts_at?.slice(0, 16) || ''} onChange={e => setSb(i, {
              starts_at: e.target.value
            })} />
                <Input className="col-span-2 text-xs" type="datetime-local" min={sb.starts_at?.slice(0, 16)} value={sb.ends_at?.slice(0, 16) || ''} onChange={e => setSb(i, {
              ends_at: e.target.value
            })} />
                <select className="col-span-2 border rounded px-1 py-1 text-xs" value={sb.setup_style} onChange={e => setSb(i, {
              setup_style: e.target.value
            })}>
                  {SETUPS.map(s => <option key={s}>{s}</option>)}
                </select>
                <Input className="col-span-1 text-xs" aria-label={`Salon ${i + 1} kişi sayısı`} type="number" min="0" value={sb.expected_pax ?? form.expected_pax} onChange={e => setSb(i, { expected_pax: Number(e.target.value) })} />
                <Button type="button" size="sm" variant="ghost" className="col-span-1" onClick={() => rmSb(i)}><Trash2 className="w-3 h-3" /></Button>
                {[['setup_minutes', 'Kurulum (dk)'], ['teardown_minutes', 'Söküm (dk)']].map(([key, label]) => <label key={key} className="col-span-6 text-xs">{label}<Input type="number" min="0" max="1440" step="1" value={sb[key] || 0} onChange={e => setSb(i, { [key]: Number(e.target.value) })} /></label>)}
              </div>)}
          </div>
          <div>
            <div className="flex items-center justify-between mb-2">
              <Label className="text-sm font-semibold">Kaynak / Menü Hatları</Label>
              <Button type="button" size="sm" variant="outline" onClick={addRes}>
                <Plus className="w-3 h-3 mr-1" /> Kaynak Ekle
              </Button>
            </div>
            {form.resources.map((r, i) => <div key={r.id || i} className="grid grid-cols-12 gap-1 mb-1.5 items-center">
                <select className="col-span-3 border rounded px-1 py-1 text-xs" value={r.menu_id || ''} onChange={e => {
              const m = menus.find(x => x.id === e.target.value);
              setRes(i, {
                menu_id: e.target.value,
                inventory_id: '',
                name: m?.name || r.name,
                type: m?.type || r.type,
                unit_price: m ? Number(m.price_per_person || m.flat_price || 0) : r.unit_price,
                quantity: m?.price_per_person > 0 ? form.expected_pax : r.quantity,
                unit: m?.price_per_person > 0 ? 'pax' : 'unit'
              });
            }}>
                  <option value="">— Menü —</option>
                  {menus.filter(m => m.active !== false).map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
                </select>
                <select className="col-span-3 border rounded px-1 py-1 text-xs" value={r.inventory_id || ''} onChange={e => {
              const inv = resources.find(x => x.id === e.target.value);
              setRes(i, {
                inventory_id: e.target.value,
                menu_id: '',
                name: inv?.name || r.name,
                type: inv?.type || r.type,
                unit_price: inv ? Number(inv.unit_price || 0) : r.unit_price
              });
            }}>
                  <option value="">— Envanter —</option>
                  {resources.filter(x => x.active !== false).map(x => <option key={x.id} value={x.id}>{x.name} (stok {x.total_stock})</option>)}
                </select>
                <Input className="col-span-2 text-xs" placeholder="Ad" value={r.name} onChange={e => setRes(i, {
              name: e.target.value
            })} />
                <Input className="col-span-1 text-xs" type="number" min="0" step="0.01" placeholder="Adet" value={r.quantity} onChange={e => setRes(i, {
              quantity: +e.target.value
            })} />
                <Input disabled={Boolean(r.menu_id || r.inventory_id)} title={r.menu_id || r.inventory_id ? 'Katalog fiyatı sunucuda uygulanır; serbest satır dışında doğrudan değiştirilemez' : ''} className="col-span-2 text-xs" type="number" min="0" step="0.01" placeholder={`Birim ${form.currency || cachedTenantCurrency()}`} value={r.unit_price} onChange={e => setRes(i, {
              unit_price: +e.target.value
            })} />
                <Button type="button" size="sm" variant="ghost" className="col-span-1" onClick={() => rmRes(i)}><Trash2 className="w-3 h-3" /></Button>
              </div>)}
            {form.resources.length > 0 && <p className="text-xs text-gray-500">
                Envanter seçilirse sistem tüm aktif etkinliklerdeki kullanım toplanır; stok aşılırsa 409.
              </p>}
          </div>
        </TabsContent>

        <TabsContent value="agenda" className="space-y-2 max-h-[60vh] overflow-y-auto pr-1">
          <div className="flex items-center justify-between mb-2">
            <Label className="text-sm font-semibold">
              Dakika Bazlı Fonksiyon Sheet ({form.agenda.length} kalem)
            </Label>
            <Button type="button" size="sm" variant="outline" onClick={addAg}>
              <Plus className="w-3 h-3 mr-1" /> Satır Ekle
            </Button>
          </div>
          {form.agenda.length === 0 && <p className="text-xs text-gray-500 text-center p-4 border rounded">
              Karşılama, açılış, ana yemek, AV testi gibi kalemleri ekleyerek tam fonksiyon sheet oluşturun.
            </p>}
          {form.agenda.map((a, i) => <div key={a.id || i} className="grid grid-cols-12 gap-1 mb-1.5 items-center">
              <Input className="col-span-2 text-xs" type="datetime-local" value={a.starts_at?.slice(0, 16) || ''} onChange={e => setAg(i, {
            starts_at: e.target.value
          })} required />
              <Input className="col-span-2 text-xs" type="datetime-local" value={a.ends_at?.slice(0, 16) || ''} onChange={e => setAg(i, {
            ends_at: e.target.value
          })} required />
              <Input className="col-span-3 text-xs" placeholder="Başlık" value={a.title} onChange={e => setAg(i, {
            title: e.target.value
          })} required />
              <select className="col-span-2 border rounded px-1 py-1 text-xs" value={a.kind} onChange={e => setAg(i, {
            kind: e.target.value
          })}>
                {AGENDA_KINDS.map(k => <option key={k}>{k}</option>)}
              </select>
              <Input className="col-span-2 text-xs" placeholder="Sorumlu" value={a.owner || ''} onChange={e => setAg(i, {
            owner: e.target.value
          })} />
              <Button type="button" size="sm" variant="ghost" className="col-span-1" onClick={() => rmAg(i)}><Trash2 className="w-3 h-3" /></Button>
            </div>)}
        </TabsContent>

        <TabsContent value="operations" className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
          <OperationsPanel form={form} setForm={setForm} />
        </TabsContent>

        <TabsContent value="payment" className="space-y-2 max-h-[60vh] overflow-y-auto pr-1">
          <div className="flex items-center justify-between mb-2">
            <Label className="text-sm font-semibold">
              Ödeme Takvimi ({form.payment_schedule.length} satır, toplam {formatCurrency(psTotal, form.currency || cachedTenantCurrency())})
            </Label>
            <Button type="button" size="sm" variant="outline" onClick={addPs}>
              <Plus className="w-3 h-3 mr-1" /> Taksit Ekle
            </Button>
          </div>
          {form.payment_schedule.length === 0 && <p className="text-xs text-gray-500 text-center p-4 border rounded">
              Depozito + bakiye taksit planı ekleyebilirsiniz.
            </p>}
          {form.payment_schedule.map((p, i) => <div key={p.id || i} className="grid grid-cols-12 gap-1 mb-1.5 items-center">
              <Input disabled={p.paid} className="col-span-3 text-xs" type="date" value={p.due_date || ''} onChange={e => setPs(i, {
            due_date: e.target.value
          })} required />
              <Input disabled={p.paid} className="col-span-4 text-xs" placeholder="Etiket (Depozito %30)" value={p.label} onChange={e => setPs(i, {
            label: e.target.value
          })} required />
              <Input disabled={p.paid} className="col-span-3 text-xs" type="number" min="0" step="0.01" placeholder={`Tutar ${form.currency || cachedTenantCurrency()}`} value={p.amount} onChange={e => setPs(i, {
            amount: +e.target.value
          })} required />
              <label className="col-span-1 text-xs text-center flex items-center gap-1">
                <input type="checkbox" disabled checked={p.paid || false} readOnly />
                Öd.
              </label>
              <Button disabled={form.payment_schedule.some(x => x.paid)} type="button" size="sm" variant="ghost" className="col-span-1" onClick={() => rmPs(i)}><Trash2 className="w-3 h-3" /></Button>
            </div>)}
        </TabsContent>
        <TabsContent value="pricing" className="space-y-4">
          <p className="text-sm text-muted-foreground">Katalog ve serbest satır fiyatları net kabul edilir. Sıra: ara toplam − indirim + servis + vergi. Bu oranlar yasal vergi tavsiyesi değildir; tesisin geçerli oranlarını girin. Karma vergi oranlı fatura için muhasebe modülünü kullanın.</p>
          <label className="flex gap-2 text-sm"><input type="checkbox" checked={form.pricing != null} onChange={e => setForm({ ...form, pricing: e.target.checked ? { discount_percent: 0, service_percent: 0, tax_percent: 0, tax_on_service: true } : null })} />İndirim / servis / vergi dökümü kullan</label>
          {form.pricing && <div className="grid gap-3 sm:grid-cols-3">
            {[['discount_percent', 'İndirim (%)'], ['service_percent', 'Servis (%)'], ['tax_percent', 'Vergi (%)']].map(([key, label]) => <Field key={key} label={label}><Input type="number" min="0" max="100" step="0.01" value={form.pricing[key]} onChange={e => setForm({ ...form, pricing: { ...form.pricing, [key]: Number(e.target.value) } })} /></Field>)}
            <label className="flex gap-2 text-sm sm:col-span-3"><input type="checkbox" checked={form.pricing.tax_on_service} onChange={e => setForm({ ...form, pricing: { ...form.pricing, tax_on_service: e.target.checked } })} />Servis bedeli vergi matrahına dahil</label>
          </div>}
        </TabsContent>
      </Tabs>

      {quotePreview && <div role="status" className="rounded-lg border bg-muted p-3 text-sm">
        <QuoteTotals totals={quotePreview.totals} currency={quotePreview.currency} />
        <strong>Hesaplanan satış bedeli: {formatCurrency(quotePreview.totals.grand_total, quotePreview.currency)}</strong>
        <p className="mt-1 text-xs text-muted-foreground">{quotePreview.notice}</p>
      </div>}
      <div className="flex flex-wrap justify-end gap-2 pt-2 border-t">
        <Button type="button" variant="outline" disabled={saving} onClick={previewQuote}>Tutarı Hesapla</Button>
        <Button type="button" variant="ghost" disabled={saving} onClick={onClose}>İptal</Button>
        <Button type="submit" disabled={saving}>{saving ? 'Kaydediliyor…' : editing ? 'Güncelle' : 'Oluştur'}</Button>
      </div>
    </form>
  </Modal>;
export default EventFormModal;
