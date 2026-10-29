import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Home, RefreshCw } from 'lucide-react';
import { cachedTenantCurrency, formatCurrency } from '@/lib/currency';
import { localIsoDate } from '@/hooks/useBusinessDate';

const FindRoomDialog = ({ open, onClose, findRoomCriteria = {}, setFindRoomCriteria, onRoomSelected, businessDate }) => {
  const { t } = useTranslation();
  const [availableRooms, setAvailableRooms] = useState([]);
  const [loading, setLoading] = useState(false);
  const requestRef = useRef(0);
  useEffect(() => {
    requestRef.current += 1;
    setAvailableRooms([]);
    setLoading(false);
    return () => { requestRef.current += 1; };
  }, [open, findRoomCriteria.check_in, findRoomCriteria.check_out, findRoomCriteria.room_type, findRoomCriteria.guests]);

  const handleSearch = async () => {
    if (!findRoomCriteria.check_in || !findRoomCriteria.check_out) {
      toast.error('Giriş ve çıkış tarihlerini seçin');
      return;
    }
    if (findRoomCriteria.check_out <= findRoomCriteria.check_in) {
      toast.error(t('pms.roomSearchInvalidDates', 'Çıkış tarihi giriş tarihinden sonra olmalı.'));
      return;
    }
    const request = ++requestRef.current;
    setLoading(true);
    try {
      const params = new URLSearchParams({
        check_in: findRoomCriteria.check_in,
        check_out: findRoomCriteria.check_out
      });
      if (findRoomCriteria.room_type && findRoomCriteria.room_type !== 'any') {
        params.append('room_type', findRoomCriteria.room_type);
      }
      const response = await axios.get(`/frontdesk/available-rooms?${params.toString()}`);
      if (request !== requestRef.current) return;
      const rooms = (response.data.available_rooms || []).filter(room => Number(room.capacity || room.max_occupancy || 2) >= Number(findRoomCriteria.guests || 1));
      setAvailableRooms(rooms);
      if (rooms.length === 0) {
        toast.info(t('pms.roomSearchEmpty', 'Seçilen tarihler ve kişi sayısı için müsait oda bulunamadı.'));
      } else {
        toast.success(t('pms.roomSearchFound', { count: rooms.length, defaultValue: '{{count}} müsait oda bulundu.' }));
      }
    } catch (error) {
      if (request !== requestRef.current) return;
      toast.error('Oda arama başarısız');
      console.error(error);
    } finally {
      if (request === requestRef.current) setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Home className="w-5 h-5" />
            {t('calendar.findRoom')}
          </DialogTitle>
          <DialogDescription>{t('pms.roomSearchDescription', 'Tarih, oda tipi ve kişi sayısına göre müsait odaları bulun.')}</DialogDescription>
        </DialogHeader>
        
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 p-4 bg-gray-50 rounded-lg">
            <div>
              <Label>{t('booking.checkInDate')} *</Label>
              <Input aria-label={t('booking.checkInDate')} type="date" value={findRoomCriteria.check_in || ''}
                onChange={(e) => setFindRoomCriteria({...findRoomCriteria, check_in: e.target.value})}
                min={businessDate || localIsoDate()} />
            </div>
            <div>
              <Label>{t('booking.checkOutDate')} *</Label>
              <Input aria-label={t('booking.checkOutDate')} type="date" value={findRoomCriteria.check_out || ''}
                onChange={(e) => setFindRoomCriteria({...findRoomCriteria, check_out: e.target.value})}
                min={findRoomCriteria.check_in || businessDate || localIsoDate()} />
            </div>
            <div>
              <Label>{t('booking.roomType')}</Label>
              <Select value={findRoomCriteria.room_type} onValueChange={(v) => setFindRoomCriteria({...findRoomCriteria, room_type: v})}>
                <SelectTrigger><SelectValue placeholder={t('pms.anyRoomType', 'Tüm oda tipleri')} /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="any">{t('pms.anyRoomType', 'Tüm oda tipleri')}</SelectItem>
                  <SelectItem value="standard">Standard</SelectItem>
                  <SelectItem value="deluxe">Deluxe</SelectItem>
                  <SelectItem value="suite">Suite</SelectItem>
                  <SelectItem value="presidential">Presidential</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{t('common.guests')}</Label>
              <Input type="number" min="1" max="6" value={findRoomCriteria.guests}
                onChange={(e) => setFindRoomCriteria({...findRoomCriteria, guests: parseInt(e.target.value)})} />
            </div>
          </div>

          <Button onClick={handleSearch} disabled={loading} className="w-full">
            {loading ? (<><RefreshCw className="w-4 h-4 mr-2 animate-spin" />{t('common.loading')}</>) 
              : (<><Home className="w-4 h-4 mr-2" />{t('common.search')}</>)}
          </Button>

          {availableRooms.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center justify-between border-b pb-2">
                <h3 className="font-semibold text-lg">{t('dashboard.availableRooms')} ({availableRooms.length})</h3>
                <Badge variant="secondary">{findRoomCriteria.check_in} – {findRoomCriteria.check_out}</Badge>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-96 overflow-y-auto">
                {availableRooms.map((room) => (
                  <Card key={room.id} className="border-l-4 border-l-green-500">
                    <CardContent className="p-4">
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-lg font-semibold">{t('common.room')} {room.room_number}</span>
                          <Badge>{room.room_type}</Badge>
                        </div>
                        <div className="text-sm text-gray-600 space-y-1">
                          <div className="flex justify-between"><span>{t('pms.roomFloor', 'Kat')}</span><span className="font-medium">{room.floor ?? '—'}</span></div>
                          <div className="flex justify-between"><span>{t('pms.roomBasePrice', 'Gecelik baz fiyat')}</span><span className="font-medium text-blue-600">{room.base_price == null ? '—' : formatCurrency(room.base_price, room.currency || cachedTenantCurrency())}</span></div>
                          <div className="flex justify-between"><span>{t('pms.roomCapacity', 'Kapasite')}</span><span className="font-medium">{room.capacity || room.max_occupancy || 2} {t('common.guests')}</span></div>
                          {room.amenities?.length > 0 && (
                            <div className="pt-2 border-t">
                              <span className="text-xs text-gray-500">{t('pms.roomAmenities', 'Oda özellikleri')}: {room.amenities.slice(0, 3).join(', ')}</span>
                            </div>
                          )}
                        </div>
                        {onRoomSelected && <Button size="sm" className="w-full mt-2" onClick={() => {
                          onRoomSelected(room);
                          toast.success(`Oda ${room.room_number} seçildi`);
                        }}>
                          {t('pms.selectRoom', 'Bu odayla rezervasyon oluştur')}
                        </Button>}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default FindRoomDialog;
