import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Plus, Trash2 } from 'lucide-react';
import { Field, Modal } from '../_shared';
import OperationsPanel from '../OperationsPanel';
import { STATUS, SETUPS, EVENT_TYPES, AGENDA_KINDS } from './constants';

const EventFormModal = ({
  editing,
  form, setForm,
  eventTab, setEventTab,
  accounts, accountById,
  spaces, menus, resources,
  psTotal,
  addSb, setSb, rmSb,
  addRes, setRes, rmRes,
  addAg, setAg, rmAg,
  addPs, setPs, rmPs,
  submit,
  onClose,
}) => (
  <Modal title={editing ? 'Etkinlik Düzenle' : 'Yeni Etkinlik'} onClose={onClose} wide>
    <form onSubmit={submit} className="space-y-3">
      <Tabs value={eventTab} onValueChange={setEventTab}>
        <TabsList>
          <TabsTrigger value="basics">Temel</TabsTrigger>
          <TabsTrigger value="spaces">Mekan & Kaynak</TabsTrigger>
          <TabsTrigger value="agenda">Fonksiyon Sheet</TabsTrigger>
          <TabsTrigger value="operations">Operasyon</TabsTrigger>
          <TabsTrigger value="payment">Ödeme Takvimi</TabsTrigger>
        </TabsList>

        <TabsContent value="basics" className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
          <div className="grid grid-cols-2 gap-2">
            <Field label="Etkinlik Adı"><Input required value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Müşteri Adı"><Input required value={form.client_name}
              onChange={(e) => setForm({ ...form, client_name: e.target.value })} /></Field>
            <Field label="Kurumsal Hesap (opsiyonel)">
              <select className="w-full border rounded px-2 py-1.5"
                      value={form.client_account_id}
                      onChange={(e) => {
                        const id = e.target.value;
                        const acct = accountById[id];
                        setForm({ ...form, client_account_id: id,
                          client_name: acct?.name || form.client_name });
                      }}>
                <option value="">— Seçilmedi —</option>
                {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </Field>
            <Field label="Organizatör Kullanıcı"><Input value={form.organizer_user}
              onChange={(e) => setForm({ ...form, organizer_user: e.target.value })} /></Field>
            <Field label="Müşteri E-posta"><Input value={form.client_email}
              onChange={(e) => setForm({ ...form, client_email: e.target.value })} /></Field>
            <Field label="Müşteri Telefon"><Input value={form.client_phone}
              onChange={(e) => setForm({ ...form, client_phone: e.target.value })} /></Field>
            <Field label="Tip">
              <select className="w-full border rounded px-2 py-1.5" value={form.event_type}
                      onChange={(e) => setForm({ ...form, event_type: e.target.value })}>
                {EVENT_TYPES.map((t) => <option key={t}>{t}</option>)}
              </select>
            </Field>
            <Field label="Durum">
              <select className="w-full border rounded px-2 py-1.5" value={form.status}
                      onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {Object.entries(STATUS).map(([k, v]) =>
                  <option key={k} value={k}>{v.label}</option>)}
              </select>
            </Field>
            <Field label="Beklenen Pax"><Input type="number" required value={form.expected_pax}
              onChange={(e) => setForm({ ...form, expected_pax: +e.target.value })} /></Field>
            <Field label="PMS Rezervasyon ID"><Input value={form.reservation_id}
              onChange={(e) => setForm({ ...form, reservation_id: e.target.value })} /></Field>
            <Field label="Başlangıç Tarihi"><Input type="date" required value={form.start_date}
              onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></Field>
            <Field label="Bitiş Tarihi"><Input type="date" required value={form.end_date}
              onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></Field>
          </div>
          <Field label="Notlar">
            <textarea className="w-full border rounded px-2 py-1.5 text-sm min-h-[60px]"
                      value={form.notes}
                      onChange={(e) => setForm({ ...form, notes: e.target.value })} />
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
            {form.space_bookings.map((sb, i) => (
              <div key={i} className="grid grid-cols-12 gap-1 mb-1.5 items-center">
                <select className="col-span-3 border rounded px-1 py-1 text-xs"
                        value={sb.space_id}
                        onChange={(e) => setSb(i, { space_id: e.target.value })}>
                  <option value="">Mekan…</option>
                  {spaces.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
                <Input className="col-span-3 text-xs" type="datetime-local" value={sb.starts_at?.slice(0, 16) || ''}
                       onChange={(e) => setSb(i, { starts_at: e.target.value })} />
                <Input className="col-span-3 text-xs" type="datetime-local" value={sb.ends_at?.slice(0, 16) || ''}
                       onChange={(e) => setSb(i, { ends_at: e.target.value })} />
                <select className="col-span-2 border rounded px-1 py-1 text-xs"
                        value={sb.setup_style}
                        onChange={(e) => setSb(i, { setup_style: e.target.value })}>
                  {SETUPS.map((s) => <option key={s}>{s}</option>)}
                </select>
                <Button type="button" size="sm" variant="ghost" className="col-span-1"
                        onClick={() => rmSb(i)}><Trash2 className="w-3 h-3" /></Button>
              </div>
            ))}
          </div>
          <div>
            <div className="flex items-center justify-between mb-2">
              <Label className="text-sm font-semibold">Kaynak / Menü Hatları</Label>
              <Button type="button" size="sm" variant="outline" onClick={addRes}>
                <Plus className="w-3 h-3 mr-1" /> Kaynak Ekle
              </Button>
            </div>
            {form.resources.map((r, i) => (
              <div key={i} className="grid grid-cols-12 gap-1 mb-1.5 items-center">
                <select className="col-span-3 border rounded px-1 py-1 text-xs"
                        value={r.menu_id || ''}
                        onChange={(e) => {
                          const m = menus.find((x) => x.id === e.target.value);
                          setRes(i, {
                            menu_id: e.target.value,
                            inventory_id: '',
                            name: m?.name || r.name,
                            type: m?.type || r.type,
                          });
                        }}>
                  <option value="">— Menü —</option>
                  {menus.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                </select>
                <select className="col-span-3 border rounded px-1 py-1 text-xs"
                        value={r.inventory_id || ''}
                        onChange={(e) => {
                          const inv = resources.find((x) => x.id === e.target.value);
                          setRes(i, {
                            inventory_id: e.target.value,
                            menu_id: '',
                            name: inv?.name || r.name,
                            type: inv?.type || r.type,
                            unit_price: inv?.unit_price || r.unit_price,
                          });
                        }}>
                  <option value="">— Envanter —</option>
                  {resources.map((x) => <option key={x.id} value={x.id}>{x.name} (stok {x.total_stock})</option>)}
                </select>
                <Input className="col-span-2 text-xs" placeholder="Ad" value={r.name}
                       onChange={(e) => setRes(i, { name: e.target.value })} />
                <Input className="col-span-1 text-xs" type="number" placeholder="Adet" value={r.quantity}
                       onChange={(e) => setRes(i, { quantity: +e.target.value })} />
                <Input className="col-span-2 text-xs" type="number" placeholder="Birim ₺" value={r.unit_price}
                       onChange={(e) => setRes(i, { unit_price: +e.target.value })} />
                <Button type="button" size="sm" variant="ghost" className="col-span-1"
                        onClick={() => rmRes(i)}><Trash2 className="w-3 h-3" /></Button>
              </div>
            ))}
            {form.resources.length > 0 && (
              <p className="text-xs text-gray-500">
                Envanter seçilirse sistem tüm aktif etkinliklerdeki kullanım toplanır; stok aşılırsa 409.
              </p>
            )}
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
          {form.agenda.length === 0 && (
            <p className="text-xs text-gray-500 text-center p-4 border rounded">
              Karşılama, açılış, ana yemek, AV testi gibi kalemleri ekleyerek tam fonksiyon sheet oluşturun.
            </p>
          )}
          {form.agenda.map((a, i) => (
            <div key={i} className="grid grid-cols-12 gap-1 mb-1.5 items-center">
              <Input className="col-span-2 text-xs" type="datetime-local"
                     value={a.starts_at?.slice(0, 16) || ''}
                     onChange={(e) => setAg(i, { starts_at: e.target.value })} required />
              <Input className="col-span-2 text-xs" type="datetime-local"
                     value={a.ends_at?.slice(0, 16) || ''}
                     onChange={(e) => setAg(i, { ends_at: e.target.value })} required />
              <Input className="col-span-3 text-xs" placeholder="Başlık" value={a.title}
                     onChange={(e) => setAg(i, { title: e.target.value })} required />
              <select className="col-span-2 border rounded px-1 py-1 text-xs"
                      value={a.kind}
                      onChange={(e) => setAg(i, { kind: e.target.value })}>
                {AGENDA_KINDS.map((k) => <option key={k}>{k}</option>)}
              </select>
              <Input className="col-span-2 text-xs" placeholder="Sorumlu" value={a.owner || ''}
                     onChange={(e) => setAg(i, { owner: e.target.value })} />
              <Button type="button" size="sm" variant="ghost" className="col-span-1"
                      onClick={() => rmAg(i)}><Trash2 className="w-3 h-3" /></Button>
            </div>
          ))}
        </TabsContent>

        <TabsContent value="operations" className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
          <OperationsPanel form={form} setForm={setForm} />
        </TabsContent>

        <TabsContent value="payment" className="space-y-2 max-h-[60vh] overflow-y-auto pr-1">
          <div className="flex items-center justify-between mb-2">
            <Label className="text-sm font-semibold">
              Ödeme Takvimi ({form.payment_schedule.length} satır, toplam ₺{psTotal.toLocaleString('tr-TR')})
            </Label>
            <Button type="button" size="sm" variant="outline" onClick={addPs}>
              <Plus className="w-3 h-3 mr-1" /> Taksit Ekle
            </Button>
          </div>
          {form.payment_schedule.length === 0 && (
            <p className="text-xs text-gray-500 text-center p-4 border rounded">
              Depozito + bakiye taksit planı ekleyebilirsiniz.
            </p>
          )}
          {form.payment_schedule.map((p, i) => (
            <div key={i} className="grid grid-cols-12 gap-1 mb-1.5 items-center">
              <Input className="col-span-3 text-xs" type="date" value={p.due_date || ''}
                     onChange={(e) => setPs(i, { due_date: e.target.value })} required />
              <Input className="col-span-4 text-xs" placeholder="Etiket (Depozito %30)"
                     value={p.label}
                     onChange={(e) => setPs(i, { label: e.target.value })} required />
              <Input className="col-span-3 text-xs" type="number" placeholder="Tutar ₺"
                     value={p.amount}
                     onChange={(e) => setPs(i, { amount: +e.target.value })} required />
              <label className="col-span-1 text-xs text-center flex items-center gap-1">
                <input type="checkbox" checked={p.paid || false}
                       onChange={(e) => setPs(i, { paid: e.target.checked })} />
                Öd.
              </label>
              <Button type="button" size="sm" variant="ghost" className="col-span-1"
                      onClick={() => rmPs(i)}><Trash2 className="w-3 h-3" /></Button>
            </div>
          ))}
        </TabsContent>
      </Tabs>

      <div className="flex justify-end gap-2 pt-2 border-t">
        <Button type="button" variant="ghost" onClick={onClose}>İptal</Button>
        <Button type="submit">{editing ? 'Güncelle' : 'Oluştur'}</Button>
      </div>
    </form>
  </Modal>
);

export default EventFormModal;
