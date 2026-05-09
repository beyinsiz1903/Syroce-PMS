import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import {
  Mail, MessageSquare, Phone, Plus, Send, Loader2,
  Clock, CreditCard, Home, History
} from 'lucide-react';
import { API, fmtTs, EmptyState, FormField, SelectField } from './helpers';
import { useTranslation } from 'react-i18next';

export function CommunicationTab({ booking, onRefresh, communicationLogs }) {
  const { t } = useTranslation();
  const [logs, setLogs] = useState(communicationLogs || []);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ channel: 'email', direction: 'outbound', subject: '', content: '', recipient: '' });
  const [loading, setLoading] = useState(false);

  useEffect(() => { setLogs(communicationLogs || []); }, [communicationLogs]);

  const handleAdd = async () => {
    if (!form.content.trim()) { toast.error('Mesaj icerigi zorunlu'); return; }
    setLoading(true);
    try {
      await axios.post(`/pms/reservations/${booking.id}/communication`, form);
      toast.success('İletişim kaydedildi'); setShowForm(false); setForm({ channel: 'email', direction: 'outbound', subject: '', content: '', recipient: '' }); onRefresh?.();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    setLoading(false);
  };

  const channelIcons = { email: Mail, sms: MessageSquare, phone: Phone, whatsapp: MessageSquare };
  const channelLabels = { email: 'E-posta', sms: 'SMS', phone: 'Telefon', whatsapp: 'WhatsApp' };
  const dirLabels = { inbound: 'Gelen', outbound: 'Giden' };

  return (
    <div data-testid="communication-tab" className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-gray-700">{t('cm.pages_reservationdetail_GuestServiceTabs.iletisim_gecmisi')}</span>
        <Button size="sm" onClick={() => setShowForm(!showForm)} className="h-7 text-xs bg-sky-600 hover:bg-sky-700 text-white"><Plus className="w-3 h-3 mr-1" /> {t('cm.pages_reservationdetail_GuestServiceTabs.kayit_ekle')}</Button>
      </div>

      {showForm && (
        <div className="border rounded-lg p-4 bg-sky-50/50 space-y-3">
          <div className="grid grid-cols-3 gap-3">
            <SelectField label="Kanal" value={form.channel} onChange={v => setForm(p => ({ ...p, channel: v }))}
              options={[['email','E-posta'],['sms','SMS'],['phone','Telefon'],['whatsapp','WhatsApp']]} />
            <SelectField label="Yon" value={form.direction} onChange={v => setForm(p => ({ ...p, direction: v }))}
              options={[['outbound','Giden'],['inbound','Gelen']]} />
            <FormField label="Alici" value={form.recipient} onChange={v => setForm(p => ({ ...p, recipient: v }))} placeholder="E-posta/Tel" />
          </div>
          <FormField label="Konu" value={form.subject} onChange={v => setForm(p => ({ ...p, subject: v }))} placeholder="Konu (opsiyonel)" />
          <div>
            <Label className="text-xs">Icerik</Label>
            <textarea value={form.content} onChange={e => setForm(p => ({ ...p, content: e.target.value }))} className="w-full h-20 text-sm border rounded-lg p-2 resize-none bg-white" placeholder="Mesaj icerigi..." />
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={handleAdd} disabled={loading} className="bg-sky-600 hover:bg-sky-700 text-white h-8 text-xs">
              {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3 mr-1" />} {t('cm.pages_reservationdetail_GuestServiceTabs.kaydet')}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setShowForm(false)} className="h-8 text-xs">{t('cm.pages_reservationdetail_GuestServiceTabs.iptal')}</Button>
          </div>
        </div>
      )}

      <div className="space-y-2">
        {logs.length === 0 ? <EmptyState icon={Mail} text="Henüz iletişim kaydi yok" /> : (
          logs.map((log, i) => {
            const Icon = channelIcons[log.channel] || Mail;
            return (
              <div key={log.id || i} className="border rounded-lg p-3 space-y-1">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className={`w-7 h-7 rounded-full flex items-center justify-center ${log.direction === 'inbound' ? 'bg-green-100' : 'bg-blue-100'}`}>
                      <Icon className={`w-3.5 h-3.5 ${log.direction === 'inbound' ? 'text-green-600' : 'text-blue-600'}`} />
                    </div>
                    <Badge className={`text-xs ${log.direction === 'inbound' ? 'bg-green-100 text-green-700' : 'bg-blue-100 text-blue-700'}`}>
                      {dirLabels[log.direction] || log.direction} {channelLabels[log.channel] || log.channel}
                    </Badge>
                    {log.recipient && <span className="text-xs text-gray-500">{log.recipient}</span>}
                  </div>
                  <span className="text-xs text-gray-400">{fmtTs(log.created_at)}</span>
                </div>
                {log.subject && <div className="text-sm font-medium text-gray-700">{log.subject}</div>}
                <div className="text-sm text-gray-600">{log.content}</div>
                <div className="text-xs text-gray-400">- {log.sent_by}</div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

export function NotesTab({ notes, booking, onRefresh }) {
  const [content, setContent] = useState('');
  const [noteType, setNoteType] = useState('general');
  const [loading, setLoading] = useState(false);
  const typeColors = { general: 'bg-gray-100 text-gray-700', important: 'bg-red-100 text-red-700', internal: 'bg-blue-100 text-blue-700', guest_request: 'bg-amber-100 text-amber-700' };
  const typeLabels = { general: 'Genel', important: 'Onemli', internal: 'Dahili', guest_request: 'Misafir Istegi' };

  const handleAdd = async () => {
    if (!content.trim()) return;
    setLoading(true);
    try {
      await axios.post(`/pms/reservations/${booking.id}/add-note`, { content, note_type: noteType });
      toast.success('Not eklendi'); setContent(''); onRefresh?.();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    setLoading(false);
  };

  return (
    <div data-testid="notes-tab" className="space-y-4">
      <div className="border rounded-lg p-4 space-y-3 bg-gray-50/50">
        <textarea value={content} onChange={e => setContent(e.target.value)} className="w-full h-20 text-sm border rounded-lg p-2 resize-none bg-white" placeholder="Not ekleyin..." />
        <div className="flex items-center gap-2">
          <select value={noteType} onChange={e => setNoteType(e.target.value)} className="h-8 text-xs border rounded-md px-2 bg-white">
            {Object.entries(typeLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <Button size="sm" onClick={handleAdd} disabled={loading || !content.trim()} className="h-8 text-xs">{loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3 mr-1" />} {t('cm.pages_reservationdetail_GuestServiceTabs.ekle')}</Button>
        </div>
      </div>
      <div className="space-y-2">
        {(!notes || notes.length === 0) ? <EmptyState icon={MessageSquare} text="Henüz not yok" /> : (
          notes.map((n, i) => (
            <div key={n.id || i} className="border rounded-lg p-3 space-y-1">
              <div className="flex items-center justify-between">
                <Badge className={`${typeColors[n.note_type] || typeColors.general} text-xs`}>{typeLabels[n.note_type] || 'Genel'}</Badge>
                <span className="text-xs text-gray-400">{fmtTs(n.created_at)}</span>
              </div>
              <p className="text-sm text-gray-700">{n.content}</p>
              <div className="text-xs text-gray-400">- {n.created_by}</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export function HistoryTab({ history, roomMoves }) {
  const allEvents = [
    ...(history || []).map(h => ({ ...h, _src: 'activity' })),
    ...(roomMoves || []).map(rm => ({ ...rm, _src: 'room_move', action: 'room_changed', actor: rm.moved_by, created_at: rm.moved_at, details: { from_room: rm.from_room_number, to_room: rm.to_room_number, reason: rm.reason } })),
  ].sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));

  const labels = {
    payment_recorded: 'Ödeme kaydedildi', transferred_to_cari: 'Cariye aktarildi', agency_payment_recorded: 'Acente ödemesi',
    charge_split: 'Masraf bölündü', note_added: 'Not eklendi', room_changed: 'Oda değiştirildi',
    early_checkin: 'Erken giriş', late_checkout: 'Gec çıkış', marked_noshow: 'No-show',
    vip_status_changed: 'VIP durumu', deposit_recorded: 'Depozito', deposit_refunded: 'Depozito iade',
    extra_charge_added: 'Ekstra ücret', daily_rates_updated: 'Fiyat güncelleme', guest_updated: 'Misafir güncelleme',
    communication_logged: 'İletişim', group_checkin: 'Grup giriş', group_checkout: 'Grup çıkış',
  };
  const colors = {
    payment_recorded: 'bg-emerald-100 text-emerald-700', transferred_to_cari: 'bg-amber-100 text-amber-700',
    agency_payment_recorded: 'bg-indigo-100 text-indigo-700', charge_split: 'bg-blue-100 text-blue-700',
    room_changed: 'bg-indigo-100 text-indigo-700', early_checkin: 'bg-teal-100 text-teal-700',
    late_checkout: 'bg-teal-100 text-teal-700', marked_noshow: 'bg-red-100 text-red-700',
    deposit_recorded: 'bg-blue-100 text-blue-700', deposit_refunded: 'bg-red-100 text-red-700',
  };

  return (
    <div data-testid="history-tab" className="space-y-3">
      <div className="text-sm font-semibold text-gray-700">{t('cm.pages_reservationdetail_GuestServiceTabs.islem_gecmisi')}</div>
      {allEvents.length === 0 ? <EmptyState icon={History} text="Henüz işlem geçmişi yok" /> : (
        <div className="relative">
          <div className="absolute left-4 top-0 bottom-0 w-px bg-gray-200" />
          {allEvents.map((ev, i) => (
            <div key={ev.id || i} className="relative flex gap-4 pb-4">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center z-10 ${colors[ev.action] || 'bg-gray-100 text-gray-600'}`}>
                {ev.action === 'room_changed' ? <Home className="w-3.5 h-3.5" /> :
                 ev.action?.includes('payment') || ev.action?.includes('deposit') ? <CreditCard className="w-3.5 h-3.5" /> :
                 ev.action?.includes('communication') ? <Mail className="w-3.5 h-3.5" /> :
                 <Clock className="w-3.5 h-3.5" />}
              </div>
              <div className="flex-1 border rounded-lg p-3 bg-white">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-gray-800">{labels[ev.action] || ev.action}</span>
                  <span className="text-xs text-gray-400">{fmtTs(ev.created_at)}</span>
                </div>
                {ev.actor && <div className="text-xs text-gray-500">Yapan: {ev.actor}</div>}
                {ev.details && Object.keys(ev.details).length > 0 && (
                  <div className="mt-1 text-xs text-gray-500 flex flex-wrap gap-2">
                    {ev.details.from_room && <span>{t('cm.pages_reservationdetail_GuestServiceTabs.eski')} {ev.details.from_room}</span>}
                    {ev.details.to_room && <span>{t('cm.pages_reservationdetail_GuestServiceTabs.yeni')} {ev.details.to_room}</span>}
                    {ev.details.amount && <span>{t('cm.pages_reservationdetail_GuestServiceTabs.tutar')} {ev.details.amount} TL</span>}
                    {ev.details.method && <span>Yontem: {ev.details.method}</span>}
                    {ev.details.reason && <span>Sebep: {ev.details.reason}</span>}
                    {ev.details.cari_account && <span>Cari: {ev.details.cari_account}</span>}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
