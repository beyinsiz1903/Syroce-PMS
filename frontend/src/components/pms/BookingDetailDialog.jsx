import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { DollarSign, FileText, Loader2, Save, X, XCircle } from 'lucide-react';

const toDateInput = (val) => {
  if (!val) return '';
  try { return new Date(val).toISOString().slice(0, 10); } catch { return ''; }
};

const BookingDetailDialog = ({ open, onClose, booking, guests, rooms, companies, onViewFolio, onBookingUpdated }) => {
  const { t } = useTranslation();
  const [cancelling, setCancelling] = useState(false);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(null);

  useEffect(() => {
    if (booking) {
      setForm({
        check_in: toDateInput(booking.check_in),
        check_out: toDateInput(booking.check_out),
        adults: booking.adults ?? 1,
        children: booking.children ?? 0,
        total_amount: booking.total_amount ?? 0,
        notes: booking.notes || '',
      });
    }
    if (!open) setEditing(false);
  }, [booking, open]);

  if (!booking) return null;

  const guest = guests.find(g => g.id === booking.guest_id);
  const room = rooms.find(r => r.id === booking.room_id);
  const company = booking.company_id ? companies.find(c => c.id === booking.company_id) : null;

  const updateField = (k, v) => setForm(prev => ({ ...prev, [k]: v }));

  const resetForm = () => {
    if (!booking) return;
    setForm({
      check_in: toDateInput(booking.check_in),
      check_out: toDateInput(booking.check_out),
      adults: booking.adults ?? 1,
      children: booking.children ?? 0,
      total_amount: booking.total_amount ?? 0,
      notes: booking.notes || '',
    });
  };

  const handleSave = async () => {
    if (!form) return;
    if (!form.check_in || !form.check_out) {
      toast.error('Giriş ve çıkış tarihleri zorunludur');
      return;
    }
    if (new Date(form.check_out) <= new Date(form.check_in)) {
      toast.error('Çıkış tarihi giriş tarihinden sonra olmalıdır');
      return;
    }
    setSaving(true);
    try {
      await axios.put(`/pms/bookings/${booking.id}`, {
        check_in: form.check_in,
        check_out: form.check_out,
        adults: Number(form.adults) || 1,
        children: Number(form.children) || 0,
        total_amount: Number(form.total_amount) || 0,
        notes: form.notes || '',
      });
      toast.success('Rezervasyon güncellendi');
      setEditing(false);
      if (onBookingUpdated) onBookingUpdated();
      onClose();
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : detail?.error || 'Güncelleme başarısız';
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('booking.bookingDetails')}</DialogTitle>
          <DialogDescription>Full reservation information and actions</DialogDescription>
        </DialogHeader>
        
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">{t('guest.guestProfile')}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">{t('common.name')}:</span>
                  <span className="font-semibold">{guest?.name || 'N/A'}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">{t('common.email')}:</span>
                  <span className="text-xs">{guest?.email || 'N/A'}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">{t('common.phone')}:</span>
                  <span className="text-xs">{guest?.phone || 'N/A'}</span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">{t('common.room')} & {t('common.date')}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">{t('common.room')}:</span>
                  <span className="font-semibold">{room?.room_number || 'N/A'}</span>
                </div>
                {editing ? (
                  <>
                    <div className="space-y-1">
                      <Label className="text-xs text-gray-600">{t('booking.checkInDate')}</Label>
                      <Input type="date" value={form?.check_in || ''} onChange={e => updateField('check_in', e.target.value)} className="h-8 text-sm" />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs text-gray-600">{t('booking.checkOutDate')}</Label>
                      <Input type="date" value={form?.check_out || ''} onChange={e => updateField('check_out', e.target.value)} className="h-8 text-sm" />
                    </div>
                  </>
                ) : (
                  <>
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">{t('booking.checkInDate')}:</span>
                      <span className="font-semibold">{new Date(booking.check_in).toLocaleDateString()}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">{t('booking.checkOutDate')}:</span>
                      <span className="font-semibold">{new Date(booking.check_out).toLocaleDateString()}</span>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>
          </div>

          <Card className="bg-gradient-to-r from-green-50 to-emerald-50">
            <CardContent className="pt-4 space-y-3">
              {editing ? (
                <div className="grid grid-cols-3 gap-3">
                  <div className="space-y-1">
                    <Label className="text-xs text-gray-600">{t('booking.totalAmount')} (₺)</Label>
                    <Input type="number" min="0" step="0.01" value={form?.total_amount ?? 0} onChange={e => updateField('total_amount', e.target.value)} className="h-9" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs text-gray-600">{t('booking.adults')}</Label>
                    <Input type="number" min="1" value={form?.adults ?? 1} onChange={e => updateField('adults', e.target.value)} className="h-9" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs text-gray-600">Çocuk</Label>
                    <Input type="number" min="0" value={form?.children ?? 0} onChange={e => updateField('children', e.target.value)} className="h-9" />
                  </div>
                  <div className="col-span-3 space-y-1">
                    <Label className="text-xs text-gray-600">Notlar</Label>
                    <Input value={form?.notes ?? ''} onChange={e => updateField('notes', e.target.value)} className="h-9" placeholder="Opsiyonel" />
                  </div>
                </div>
              ) : (
                <div className="grid grid-cols-3 gap-4 text-center">
                  <div>
                    <div className="text-2xl font-bold text-green-700">${booking.total_amount || 0}</div>
                    <div className="text-xs text-gray-600">{t('booking.totalAmount')}</div>
                  </div>
                  <div>
                    <div className="text-2xl font-bold text-blue-700">{booking.adults || 1}</div>
                    <div className="text-xs text-gray-600">{t('booking.adults')}</div>
                  </div>
                  <div>
                    <div className="text-2xl font-bold text-purple-700">{booking.status?.toUpperCase() || 'N/A'}</div>
                    <div className="text-xs text-gray-600">{t('common.status')}</div>
                  </div>
                </div>
              )}

              {company && !editing && (
                <div className="grid grid-cols-2 gap-4 text-xs text-left bg-white/60 p-3 rounded border border-emerald-100">
                  <div className="space-y-1">
                    <div className="text-[11px] font-semibold text-gray-700">Corporate</div>
                    <div className="text-gray-800 font-medium">{company.name}</div>
                    <div className="text-[11px] text-gray-500">Code: {company.corporate_code || 'N/A'}</div>
                  </div>
                  <div className="space-y-1">
                    <div className="text-[11px] font-semibold text-gray-700">Rate Details</div>
                    <div className="text-[11px] text-gray-600">Contracted: <span className="font-medium">{booking.contracted_rate || 'N/A'}</span></div>
                    <div className="text-[11px] text-gray-600">Segment: <span className="font-medium">{booking.market_segment || 'corporate'}</span></div>
                    <div className="text-[11px] text-gray-600">Policy: <span className="font-medium">{booking.cancellation_policy || 'standard'}</span></div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {editing ? (
            <div className="grid grid-cols-2 gap-2">
              <Button
                size="sm"
                onClick={handleSave}
                disabled={saving}
                className="bg-blue-600 hover:bg-blue-700"
              >
                {saving ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Save className="w-4 h-4 mr-1" />}
                Kaydet
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => { resetForm(); setEditing(false); }}
                disabled={saving}
              >
                <X className="w-4 h-4 mr-1" />
                İptal
              </Button>
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-2">
              <Button 
                size="sm"
                onClick={() => { onViewFolio(booking.id); onClose(); }}
                className="bg-green-600 hover:bg-green-700"
              >
                <DollarSign className="w-4 h-4 mr-1" />
                {t('folio.title')}
              </Button>
              <Button 
                size="sm"
                variant="outline"
                onClick={() => setEditing(true)}
                disabled={booking.status === 'cancelled' || booking.status === 'checked_out'}
              >
                <FileText className="w-4 h-4 mr-1" />
                {t('common.edit')}
              </Button>
              <Button 
                size="sm"
                variant="outline"
                className="border-red-400 text-red-700 hover:bg-red-50"
                disabled={cancelling || booking.status === 'cancelled' || booking.status === 'checked_in' || booking.status === 'checked_out'}
                data-testid="cancel-booking-btn"
                onClick={async () => {
                  if (!confirm(t('booking.cancelBooking') + '?')) return;
                  setCancelling(true);
                  try {
                    await axios.post('/pms-core/cancel', {
                      booking_id: booking.id,
                      reason: 'Kullanıcı tarafından iptal edildi'
                    });
                    toast.success('Rezervasyon başarıyla iptal edildi');
                    if (onBookingUpdated) onBookingUpdated();
                    onClose();
                  } catch (err) {
                    const detail = err.response?.data?.detail;
                    const msg = typeof detail === 'string' ? detail : detail?.error || 'İptal işlemi başarısız';
                    toast.error(msg);
                  } finally {
                    setCancelling(false);
                  }
                }}
              >
                {cancelling ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <XCircle className="w-4 h-4 mr-1" />}
                {booking.status === 'cancelled' ? 'İptal Edildi' : t('booking.cancelBooking')}
              </Button>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default BookingDetailDialog;
