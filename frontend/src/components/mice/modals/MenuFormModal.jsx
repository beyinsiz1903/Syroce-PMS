import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Field, Modal } from '../_shared';

const MenuFormModal = ({
  editingMenu,
  menuForm, setMenuForm,
  toggleTag,
  submitMenu,
  onClose,
}) => (
  <Modal title={editingMenu ? 'Menü / Paket Düzenle' : 'Yeni Menü / Paket'} onClose={onClose}>
    <form onSubmit={submitMenu} className="space-y-3">
      <Field label="Ad">
        <Input required value={menuForm.name}
          onChange={(e) => setMenuForm({ ...menuForm, name: e.target.value })} />
      </Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Tip">
          <select className="w-full border rounded px-2 py-1.5"
                  value={menuForm.type}
                  onChange={(e) => setMenuForm({ ...menuForm, type: e.target.value })}>
            <option value="fb">F&B (yiyecek-içecek)</option>
            <option value="av">AV (görsel-işitsel)</option>
            <option value="decor">Dekorasyon</option>
            <option value="ddr">DDR (Daily Delegate Rate)</option>
          </select>
        </Field>
        <Field label="Para Birimi">
          <Input value={menuForm.currency}
            onChange={(e) => setMenuForm({ ...menuForm, currency: e.target.value.toUpperCase() })} />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Kişi Başı Fiyat (₺)">
          <Input type="number" min="0" step="0.01"
            value={menuForm.price_per_person}
            onChange={(e) => setMenuForm({ ...menuForm, price_per_person: e.target.value })} />
        </Field>
        <Field label="Sabit Fiyat (₺)">
          <Input type="number" min="0" step="0.01"
            value={menuForm.flat_price}
            onChange={(e) => setMenuForm({ ...menuForm, flat_price: e.target.value })} />
        </Field>
      </div>
      <p className="text-xs text-gray-500 -mt-1">
        Sadece birini doldurun. Kişi başı dolu ise pax ile çarpılır; sabit ise toplam tek seferdir.
      </p>
      <Field label="Açıklama (opsiyonel)">
        <textarea className="w-full border rounded px-2 py-1.5 text-sm min-h-[60px]"
          value={menuForm.description}
          onChange={(e) => setMenuForm({ ...menuForm, description: e.target.value })} />
      </Field>
      <Field label="Diyet Etiketleri">
        <div className="flex flex-wrap gap-1.5">
          {['vegan', 'vegetarian', 'halal', 'kosher', 'gluten_free'].map((t) => (
            <button type="button" key={t}
              onClick={() => toggleTag('dietary_tags', t)}
              className={`px-2 py-1 text-xs rounded border ${
                menuForm.dietary_tags.includes(t)
                  ? 'bg-emerald-100 border-emerald-400 text-emerald-800'
                  : 'bg-white border-gray-300 text-gray-600'
              }`}>{t}</button>
          ))}
        </div>
      </Field>
      <Field label="Alerjenler">
        <div className="flex flex-wrap gap-1.5">
          {['nuts', 'gluten', 'dairy', 'egg', 'soy', 'fish', 'shellfish', 'sesame'].map((t) => (
            <button type="button" key={t}
              onClick={() => toggleTag('allergens', t)}
              className={`px-2 py-1 text-xs rounded border ${
                menuForm.allergens.includes(t)
                  ? 'bg-red-100 border-red-400 text-red-800'
                  : 'bg-white border-gray-300 text-gray-600'
              }`}>{t}</button>
          ))}
        </div>
      </Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Min. Kişi Sayısı">
          <Input type="number" min="0" value={menuForm.min_guests}
            onChange={(e) => setMenuForm({ ...menuForm, min_guests: e.target.value })} />
        </Field>
        <Field label="Mutfak Hazırlık (dk)">
          <Input type="number" min="0" value={menuForm.prep_lead_minutes}
            onChange={(e) => setMenuForm({ ...menuForm, prep_lead_minutes: e.target.value })} />
        </Field>
      </div>
      <Field label="Durum">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={menuForm.active}
            onChange={(e) => setMenuForm({ ...menuForm, active: e.target.checked })} />
          Aktif (etkinliklerde seçilebilir)
        </label>
      </Field>
      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="ghost" onClick={onClose}>İptal</Button>
        <Button type="submit">{editingMenu ? 'Güncelle' : 'Oluştur'}</Button>
      </div>
    </form>
  </Modal>
);

export default MenuFormModal;
