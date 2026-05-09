import { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Plus, Trash2, Briefcase, Check } from 'lucide-react';
import { Field, Modal } from './_shared';
import { confirmDialog } from '@/lib/dialogs';
import { useTranslation } from 'react-i18next';

const AccountsView = ({ accounts, reload }) => {
  const { t } = useTranslation();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', tax_no: '', city: '', industry: 'corporate',
                                     credit_limit: 0, payment_terms_days: 30 });
  const [expandedId, setExpandedId] = useState(null);
  const [contactsCache, setContactsCache] = useState({});
  const [contactForm, setContactForm] = useState(null);

  const create = async (e) => {
    e.preventDefault();
    try {
      await axios.post('/mice/accounts', form);
      toast.success('Hesap oluşturuldu');
      setShowForm(false);
      setForm({ name: '', tax_no: '', city: '', industry: 'corporate',
                credit_limit: 0, payment_terms_days: 30 });
      await reload();
    } catch (err) { toast.error(err.response?.data?.detail || 'Hata'); }
  };
  const remove = async (id) => {
    if (!await confirmDialog({ message: 'Hesap silinsin mi?', variant: 'danger' })) return;
    try { await axios.delete(`/mice/accounts/${id}`); await reload(); }
    catch (err) { toast.error(err.response?.data?.detail || 'Silinemedi'); }
  };
  const expand = async (id) => {
    if (expandedId === id) { setExpandedId(null); return; }
    setExpandedId(id);
    if (!contactsCache[id]) {
      try {
        const r = await axios.get(`/mice/accounts/${id}/contacts`);
        setContactsCache((c) => ({ ...c, [id]: r.data.contacts }));
      } catch { toast.error('Kişiler yüklenemedi'); }
    }
  };
  const addContact = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`/mice/accounts/${contactForm.account_id}/contacts`, contactForm);
      const r = await axios.get(`/mice/accounts/${contactForm.account_id}/contacts`);
      setContactsCache((c) => ({ ...c, [contactForm.account_id]: r.data.contacts }));
      setContactForm(null);
      toast.success('Kişi eklendi');
    } catch (err) { toast.error(err.response?.data?.detail || 'Eklenemedi'); }
  };

  return (
    <Card><CardContent className="p-3">
      <div className="flex justify-between items-center mb-3">
        <h3 className="font-semibold">{t('cm.components_mice_AccountsView.kurumsal_musteriler')}{accounts.length})</h3>
        <Button size="sm" onClick={() => setShowForm(true)}>
          <Plus className="w-3 h-3 mr-1" /> {t('cm.components_mice_AccountsView.yeni_hesap')}
        </Button>
      </div>
      {accounts.length === 0 && <p className="text-center text-gray-500 p-4">{t('cm.components_mice_AccountsView.henuz_hesap_yok')}</p>}
      <div className="space-y-1">
        {accounts.map((a) => (
          <div key={a.id} className="border rounded">
            <div className="flex items-center gap-2 p-2 hover:bg-slate-50 cursor-pointer"
                 onClick={() => expand(a.id)}>
              <Briefcase className="w-4 h-4 text-indigo-600" />
              <div className="flex-1">
                <div className="font-semibold text-sm">{a.name}</div>
                <div className="text-xs text-gray-500">
                  {a.tax_no && `VKN ${a.tax_no} • `}{a.city || ''} • {a.industry}
                  {a.credit_limit > 0 && ` • Kredi limiti ₺${a.credit_limit.toLocaleString('tr-TR')}`}
                </div>
              </div>
              <Badge variant="outline" className="text-xs">
                {a.payment_terms_days}{t('cm.components_mice_AccountsView.gun_vade')}
              </Badge>
              <Button size="sm" variant="ghost" onClick={(e) => {
                e.stopPropagation();
                setContactForm({ account_id: a.id, name: '', title: '', email: '', phone: '', is_primary: false });
              }}>
                <Plus className="w-3 h-3" /> {t('cm.components_mice_AccountsView.kisi')}
              </Button>
              <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); remove(a.id); }}>
                <Trash2 className="w-3 h-3" />
              </Button>
            </div>
            {expandedId === a.id && (
              <div className="bg-slate-50 p-2 border-t">
                {(contactsCache[a.id] || []).length === 0 ? (
                  <p className="text-xs text-gray-500">{t('cm.components_mice_AccountsView.henuz_kisi_yok')}</p>
                ) : (
                  <table className="w-full text-xs">
                    <thead><tr className="text-gray-500">
                      <th className="text-left p-1">Ad</th>
                      <th className="text-left p-1">Unvan</th>
                      <th className="text-left p-1">E-posta</th>
                      <th className="text-left p-1">Telefon</th>
                      <th>Birincil</th>
                    </tr></thead>
                    <tbody>
                      {(contactsCache[a.id] || []).map((c) => (
                        <tr key={c.id} className="border-t">
                          <td className="p-1 font-medium">{c.name}</td>
                          <td className="p-1">{c.title}</td>
                          <td className="p-1">{c.email}</td>
                          <td className="p-1">{c.phone}</td>
                          <td className="p-1 text-center">{c.is_primary ? <Check className="w-4 h-4 inline text-emerald-600" /> : null}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {showForm && (
        <Modal title={t('cm.components_mice_AccountsView.yeni_kurumsal_hesap')} onClose={() => setShowForm(false)}>
          <form onSubmit={create} className="space-y-2">
            <Field label={t('cm.components_mice_AccountsView.sirket_adi')}><Input required value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Vergi No"><Input value={form.tax_no}
                onChange={(e) => setForm({ ...form, tax_no: e.target.value })} /></Field>
              <Field label={t('cm.components_mice_AccountsView.sehir')}><Input value={form.city}
                onChange={(e) => setForm({ ...form, city: e.target.value })} /></Field>
              <Field label={t('cm.components_mice_AccountsView.sektor')}>
                <select className="w-full border rounded px-2 py-1.5" value={form.industry}
                        onChange={(e) => setForm({ ...form, industry: e.target.value })}>
                  {['corporate', 'travel_agency', 'government', 'ngo', 'other'].map((x) => <option key={x}>{x}</option>)}
                </select>
              </Field>
              <Field label={t('cm.components_mice_AccountsView.vade_gun')}><Input type="number" value={form.payment_terms_days}
                onChange={(e) => setForm({ ...form, payment_terms_days: +e.target.value })} /></Field>
              <Field label="Kredi Limiti ₺"><Input type="number" value={form.credit_limit}
                onChange={(e) => setForm({ ...form, credit_limit: +e.target.value })} /></Field>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>{t('cm.components_mice_AccountsView.iptal')}</Button>
              <Button type="submit">{t('cm.components_mice_AccountsView.olustur')}</Button>
            </div>
          </form>
        </Modal>
      )}
      {contactForm && (
        <Modal title={t('cm.components_mice_AccountsView.yeni_kisi')} onClose={() => setContactForm(null)}>
          <form onSubmit={addContact} className="space-y-2">
            <Field label="Ad Soyad"><Input required value={contactForm.name}
              onChange={(e) => setContactForm({ ...contactForm, name: e.target.value })} /></Field>
            <Field label="Unvan"><Input value={contactForm.title}
              onChange={(e) => setContactForm({ ...contactForm, title: e.target.value })} /></Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="E-posta"><Input type="email" value={contactForm.email}
                onChange={(e) => setContactForm({ ...contactForm, email: e.target.value })} /></Field>
              <Field label="Telefon"><Input value={contactForm.phone}
                onChange={(e) => setContactForm({ ...contactForm, phone: e.target.value })} /></Field>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={contactForm.is_primary}
                     onChange={(e) => setContactForm({ ...contactForm, is_primary: e.target.checked })} />
              {t('cm.components_mice_AccountsView.birincil_kisi')}
            </label>
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="ghost" onClick={() => setContactForm(null)}>{t('cm.components_mice_AccountsView.iptal_25174')}</Button>
              <Button type="submit">{t('cm.components_mice_AccountsView.ekle')}</Button>
            </div>
          </form>
        </Modal>
      )}
    </CardContent></Card>
  );
};

export default AccountsView;
