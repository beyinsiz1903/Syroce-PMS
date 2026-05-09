import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Plus, Trash2 } from 'lucide-react';
import { Field } from './_shared';
import { useTranslation } from 'react-i18next';

const STAFF_ROLES = [
  ['chef', 'Aşçı'], ['server', 'Servis'], ['technician', 'Teknisyen'],
  ['host', 'Host/Hostes'], ['security', 'Güvenlik'], ['other', 'Diğer'],
];
const ENT_TYPES = [
  ['none', 'Yok'], ['dj', 'DJ'], ['live_band', 'Canlı Grup'],
  ['solo_artist', 'Solo Sanatçı'], ['show', 'Show'],
];
const TECH_BOOLS = [
  ['projector', 'Projeksiyon'], ['screen', 'Perde'],
  ['sound_system', 'Ses Sistemi'], ['stage', 'Sahne'],
  ['lighting', 'Işık'], ['livestream', 'Canlı Yayın'],
];

const OperationsPanel = ({ form, setForm }) => {
  const { t } = useTranslation();
  const tr = form.technical_requirements || {};
  const ent = form.entertainment || {};
  const setTr = (patch) =>
    setForm({ ...form, technical_requirements: { ...tr, ...patch } });
  const setEnt = (patch) =>
    setForm({ ...form, entertainment: { ...ent, ...patch } });
  const addStaff = () =>
    setForm({ ...form, staff_assignments: [
      ...(form.staff_assignments || []),
      { role: 'server', name: '', notes: '' },
    ]});
  const setStaff = (i, patch) => {
    const next = [...(form.staff_assignments || [])];
    next[i] = { ...next[i], ...patch };
    setForm({ ...form, staff_assignments: next });
  };
  const rmStaff = (i) => setForm({ ...form,
    staff_assignments: (form.staff_assignments || []).filter((_, j) => j !== i) });

  return (
    <div className="space-y-4">
      <section>
        <Label className="text-sm font-semibold">Teknik Beklentiler</Label>
        <div className="grid grid-cols-3 gap-2 mt-2">
          {TECH_BOOLS.map(([k, lbl]) => (
            <label key={k} className="flex items-center gap-2 text-xs border rounded px-2 py-1.5">
              <input type="checkbox" checked={!!tr[k]}
                     onChange={(e) => setTr({ [k]: e.target.checked })} />
              {lbl}
            </label>
          ))}
        </div>
        <div className="grid grid-cols-4 gap-2 mt-2">
          <Field label="Kablolu Mikrofon">
            <Input type="number" min="0" value={tr.microphone_wired || 0}
                   onChange={(e) => setTr({ microphone_wired: +e.target.value })} />
          </Field>
          <Field label="Kablosuz Mikrofon">
            <Input type="number" min="0" value={tr.microphone_wireless || 0}
                   onChange={(e) => setTr({ microphone_wireless: +e.target.value })} />
          </Field>
          <Field label={t('cm.components_mice_OperationsPanel.internet_mbps')}>
            <Input type="number" min="0" value={tr.internet_mbps || 0}
                   onChange={(e) => setTr({ internet_mbps: +e.target.value })} />
          </Field>
          <Field label={t('cm.components_mice_OperationsPanel.ceviri_kabin_sayisi')}>
            <Input type="number" min="0" value={tr.translation_booths || 0}
                   onChange={(e) => setTr({ translation_booths: +e.target.value })} />
          </Field>
        </div>
        <Field label="Teknik Notlar">
          <Input value={tr.notes || ''}
                 onChange={(e) => setTr({ notes: e.target.value })}
                 placeholder={t('cm.components_mice_OperationsPanel.ozel_kurulum_jenerator_vb')} />
        </Field>
      </section>

      <section>
        <div className="flex items-center justify-between">
          <Label className="text-sm font-semibold">
            {t('cm.components_mice_OperationsPanel.gorevli_personel')}{(form.staff_assignments || []).length})
          </Label>
          <Button type="button" size="sm" variant="outline" onClick={addStaff}>
            <Plus className="w-3 h-3 mr-1" /> {t('cm.components_mice_OperationsPanel.personel_ekle')}
          </Button>
        </div>
        {(form.staff_assignments || []).length === 0 && (
          <p className="text-xs text-gray-500 text-center p-3 border rounded mt-2">
            {t('cm.components_mice_OperationsPanel.etkinlikte_gorevli_olacak_personeli_ekle')}
          </p>
        )}
        {(form.staff_assignments || []).map((s, i) => (
          <div key={i} className="grid grid-cols-12 gap-1 mt-1.5 items-center">
            <select className="col-span-3 text-xs border rounded px-2 py-1.5"
                    value={s.role}
                    onChange={(e) => setStaff(i, { role: e.target.value })}>
              {STAFF_ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <Input className="col-span-4 text-xs" placeholder={t('cm.components_mice_OperationsPanel.isim')}
                   value={s.name || ''}
                   onChange={(e) => setStaff(i, { name: e.target.value })} required />
            <Input className="col-span-4 text-xs" placeholder="Not (opsiyonel)"
                   value={s.notes || ''}
                   onChange={(e) => setStaff(i, { notes: e.target.value })} />
            <Button type="button" size="sm" variant="ghost" className="col-span-1"
                    onClick={() => rmStaff(i)}><Trash2 className="w-3 h-3" /></Button>
          </div>
        ))}
      </section>

      <section>
        <Label className="text-sm font-semibold">{t('cm.components_mice_OperationsPanel.muzik_eglence')}</Label>
        <div className="grid grid-cols-3 gap-2 mt-2">
          <Field label="Tip">
            <select className="w-full border rounded px-2 py-1.5"
                    value={ent.type || 'none'}
                    onChange={(e) => setEnt({ type: e.target.value })}>
              {ENT_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </Field>
          <Field label={t('cm.components_mice_OperationsPanel.isim_sanatci')}>
            <Input value={ent.name || ''}
                   onChange={(e) => setEnt({ name: e.target.value })}
                   disabled={ent.type === 'none'} />
          </Field>
          <Field label={t('cm.components_mice_OperationsPanel.iletisim')}>
            <Input value={ent.contact || ''}
                   onChange={(e) => setEnt({ contact: e.target.value })}
                   disabled={ent.type === 'none'} />
          </Field>
          <Field label={t('cm.components_mice_OperationsPanel.baslama')}>
            <Input type="datetime-local" value={ent.start_at || ''}
                   onChange={(e) => setEnt({ start_at: e.target.value })}
                   disabled={ent.type === 'none'} />
          </Field>
          <Field label={t('cm.components_mice_OperationsPanel.bitis')}>
            <Input type="datetime-local" value={ent.end_at || ''}
                   onChange={(e) => setEnt({ end_at: e.target.value })}
                   disabled={ent.type === 'none'} />
          </Field>
          <Field label={t('cm.components_mice_OperationsPanel.ucret')}>
            <Input type="number" min="0" value={ent.fee || 0}
                   onChange={(e) => setEnt({ fee: +e.target.value })}
                   disabled={ent.type === 'none'} />
          </Field>
        </div>
        <Field label={t('cm.components_mice_OperationsPanel.teknik_ihtiyaclar_notlar')}>
          <Input value={ent.requirements || ''}
                 onChange={(e) => setEnt({ requirements: e.target.value })}
                 disabled={ent.type === 'none'}
                 placeholder={t('cm.components_mice_OperationsPanel.hoparlor_sayisi_sahne_olcusu_vb')} />
        </Field>
      </section>
    </div>
  );
};

export default OperationsPanel;
