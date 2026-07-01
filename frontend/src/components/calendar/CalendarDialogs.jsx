import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { useTranslation } from 'react-i18next';

export function NewBookingDialog({ open, onOpenChange, newBooking, setNewBooking, guests, selectedRoom, selectedDate, handleCreateBooking }) {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Quick Booking</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleCreateBooking} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Room</Label>
              <Input value={selectedRoom?.room_number || ''} disabled />
            </div>
            <div>
              <Label>{t('cm.components_calendar_CalendarDialogs.misafir')}</Label>
              <div className="flex gap-2">
                <select
                  className="flex-1 border rounded-md p-2"
                  value={newBooking.guest_id}
                  onChange={(e) => {
                    if (e.target.value === 'NEW') {
                      setNewBooking({...newBooking, guest_id: '', guest_name: '', guest_email: '', guest_phone: ''});
                    } else {
                      setNewBooking({...newBooking, guest_id: e.target.value});
                    }
                  }}
                >
                  <option value="">{t('cm.components_calendar_CalendarDialogs.misafir_secin')}</option>
                  <option value="NEW" className="font-bold text-blue-600">{t('cm.components_calendar_CalendarDialogs.yeni_misafir_ekle')}</option>
                  {guests.map(guest => (
                    <option key={guest.id} value={guest.id}>{guest.name}</option>
                  ))}
                </select>
              </div>
              {newBooking.guest_id === '' && newBooking.guest_name !== undefined && (
                <div className="mt-3 p-3 border rounded-md bg-blue-50 space-y-2">
                  <div className="text-sm font-semibold text-blue-900 mb-2">{t('cm.components_calendar_CalendarDialogs.yeni_misafir_bilgileri')}</div>
                  <Input placeholder="Isim Soyisim *" value={newBooking.guest_name || ''} onChange={(e) => setNewBooking({...newBooking, guest_name: e.target.value})} required />
                  <Input type="email" placeholder="E-posta" value={newBooking.guest_email || ''} onChange={(e) => setNewBooking({...newBooking, guest_email: e.target.value})} />
                  <Input type="tel" placeholder="Telefon" value={newBooking.guest_phone || ''} onChange={(e) => setNewBooking({...newBooking, guest_phone: e.target.value})} />
                </div>
              )}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>{t('cm.components_calendar_CalendarDialogs.giris')}</Label>
              <Input type="date" value={newBooking.check_in} min={new Date().toISOString().split('T')[0]} onChange={(e) => setNewBooking({...newBooking, check_in: e.target.value})} required />
            </div>
            <div>
              <Label>{t('cm.components_calendar_CalendarDialogs.cikis')}</Label>
              <Input type="date" value={newBooking.check_out} onChange={(e) => setNewBooking({...newBooking, check_out: e.target.value})} required />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <Label>{t('cm.components_calendar_CalendarDialogs.tutar_tl')}</Label>
              <Input type="number" value={newBooking.total_amount} onChange={(e) => setNewBooking({...newBooking, total_amount: e.target.value})} />
            </div>
            <div>
              <Label>Yetiskin</Label>
              <Input type="number" min="1" value={newBooking.adults} onChange={(e) => setNewBooking({...newBooking, adults: parseInt(e.target.value) || 1})} />
            </div>
            <div>
              <Label>Cocuk</Label>
              <Input type="number" min="0" value={newBooking.children} onChange={(e) => setNewBooking({...newBooking, children: parseInt(e.target.value) || 0})} />
            </div>
          </div>
          <div>
            <Label>{t('cm.components_calendar_CalendarDialogs.ozel_istekler')}</Label>
            <Input value={newBooking.special_requests || ''} onChange={(e) => setNewBooking({...newBooking, special_requests: e.target.value})} placeholder="Opsiyonel" />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" type="button" onClick={() => onOpenChange(false)}>{t('cm.components_calendar_CalendarDialogs.iptal')}</Button>
            <Button type="submit" className="bg-amber-500 hover:bg-amber-600 text-white">{t('cm.components_calendar_CalendarDialogs.rezervasyon_olustur')}</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function MoveReasonDialog({ open, onOpenChange, moveData, moveReason, setMoveReason, handleConfirmMove }) {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('cm.components_calendar_CalendarDialogs.oda_tasima_sebep_gerekli')}</DialogTitle>
        </DialogHeader>
        {moveData && (
          <div className="space-y-4">
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
              <div className="text-sm text-blue-900">
                <div className="font-semibold mb-2">Tasima Bilgileri:</div>
                <div>{t('cm.components_calendar_CalendarDialogs.misafir_7377d')} <strong>{moveData.booking.guest_name}</strong></div>
                <div>{t('cm.components_calendar_CalendarDialogs.oda')} <strong>{moveData.oldRoom}</strong> → <strong>{moveData.newRoom}</strong></div>
                <div>{t('cm.components_calendar_CalendarDialogs.tarih')} <strong>{moveData.newCheckIn}</strong> - <strong>{moveData.newCheckOut}</strong></div>
              </div>
            </div>
            <div>
              <Label>Tasima Sebebi *</Label>
              <select className="w-full border rounded-md p-2 mb-2" value={moveReason} onChange={(e) => setMoveReason(e.target.value)}>
                <option value="">{t('cm.components_calendar_CalendarDialogs.sebep_seciniz')}</option>
                <option value="Guest Request">{t('cm.components_calendar_CalendarDialogs.misafir_istegi')}</option>
                <option value="Room Maintenance">{t('cm.components_calendar_CalendarDialogs.oda_bakimi')}</option>
                <option value="Upgrade">Upgrade</option>
                <option value="Downgrade">Downgrade</option>
                <option value="Overbooking">Overbooking</option>
                <option value="VIP Guest">{t('cm.components_calendar_CalendarDialogs.vip_misafir')}</option>
                <option value="Room Issue">{t('cm.components_calendar_CalendarDialogs.oda_sorunu')}</option>
                <option value="Operational">Operasyonel</option>
                <option value="Other">Diger</option>
              </select>
              {moveReason === 'Other' && <Input placeholder={t('cm.components_calendar_CalendarDialogs.aciklama')} onChange={(e) => setMoveReason(e.target.value)} />}
            </div>
            <div className="text-xs text-gray-600 bg-gray-50 p-3 rounded">
              <strong>Not:</strong> {t('cm.components_calendar_CalendarDialogs.bu_islem_gecmise_kaydedilecektir')}
            </div>
            <div className="flex space-x-2">
              <Button onClick={handleConfirmMove} className="flex-1">{t('cm.components_calendar_CalendarDialogs.onayla')}</Button>
              <Button variant="outline" onClick={() => { onOpenChange(false); setMoveReason(''); }}>{t('cm.components_calendar_CalendarDialogs.iptal_25174')}</Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function FindRoomDialog({ open, onOpenChange, findRoomCriteria, setFindRoomCriteria, availableRooms, handleFindRoom, rooms }) {
  const { t } = useTranslation();
  const roomTypes = [...new Set(rooms.map(r => r.room_type || 'standard'))];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{t('cm.components_calendar_CalendarDialogs.musait_oda_ara')}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-4 gap-4">
            <div>
              <Label>{t('cm.components_calendar_CalendarDialogs.giris_1ffbd')}</Label>
              <Input type="date" value={findRoomCriteria.check_in} onChange={(e) => setFindRoomCriteria({...findRoomCriteria, check_in: e.target.value})} />
            </div>
            <div>
              <Label>{t('cm.components_calendar_CalendarDialogs.cikis_b9015')}</Label>
              <Input type="date" value={findRoomCriteria.check_out} onChange={(e) => setFindRoomCriteria({...findRoomCriteria, check_out: e.target.value})} />
            </div>
            <div>
              <Label>{t('cm.components_calendar_CalendarDialogs.oda_tipi')}</Label>
              <select className="w-full border rounded-md p-2" value={findRoomCriteria.room_type} onChange={(e) => setFindRoomCriteria({...findRoomCriteria, room_type: e.target.value})}>
                <option value="all">Tumu</option>
                {roomTypes.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div className="flex items-end">
              <Button onClick={handleFindRoom} className="w-full">{t('cm.components_calendar_CalendarDialogs.ara')}</Button>
            </div>
          </div>
          {availableRooms.length > 0 && (
            <div className="border rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="text-left p-2 font-medium">{t('cm.components_calendar_CalendarDialogs.oda_e4b47')}</th>
                    <th className="text-left p-2 font-medium">Tip</th>
                    <th className="text-left p-2 font-medium">Kat</th>
                    <th className="text-left p-2 font-medium">{t('cm.components_calendar_CalendarDialogs.durum')}</th>
                  </tr>
                </thead>
                <tbody>
                  {availableRooms.map(r => (
                    <tr key={r.id} className="border-t hover:bg-blue-50 cursor-pointer">
                      <td className="p-2 font-semibold">{r.room_number}</td>
                      <td className="p-2">{r.room_type}</td>
                      <td className="p-2">{r.floor || '-'}</td>
                      <td className="p-2"><Badge className="bg-emerald-100 text-emerald-700 text-xs">{t('cm.components_calendar_CalendarDialogs.musait')}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
