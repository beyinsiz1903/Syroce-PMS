import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import {
  CreditCard,
  Eye,
  EyeOff,
  Trash2,
  Lock,
  ShieldAlert,
  Plus,
  Loader2,
  Copy,
  CheckCircle2,
} from 'lucide-react';

const MAX_VIEWS = 3;

function formatCardNumber(num) {
  if (!num) return '';
  return num.replace(/\s/g, '').replace(/(.{4})/g, '$1 ').trim();
}

export function VCCTab({ booking, onRefresh }) {
  const bookingId = booking?.id;
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const [revealed, setRevealed] = useState(null);
  const [revealInfo, setRevealInfo] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    card_holder: '',
    card_number: '',
    expiry: '',
    cvv: '',
    card_type: 'virtual',
  });

  const load = useCallback(async () => {
    if (!bookingId) return;
    setLoading(true);
    try {
      const res = await axios.get(`/pms/reservations/${bookingId}/vcc/status`);
      setStatus(res.data);
    } catch (e) {
      toast.error('Kart durumu alınamadı: ' + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  }, [bookingId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleStore = async () => {
    if (!form.card_holder || !form.card_number || !form.expiry) {
      toast.error('Kart sahibi, numara ve son kullanma zorunludur');
      return;
    }
    setBusy(true);
    try {
      await axios.post(`/pms/reservations/${bookingId}/vcc`, form);
      toast.success('Kart güvenli şekilde kaydedildi');
      setShowForm(false);
      setForm({ card_holder: '', card_number: '', expiry: '', cvv: '', card_type: 'virtual' });
      await load();
      onRefresh?.();
    } catch (e) {
      toast.error('Kayıt hatası: ' + (e.response?.data?.detail || e.message));
    } finally {
      setBusy(false);
    }
  };

  const handleReveal = async () => {
    setShowConfirm(false);
    setBusy(true);
    try {
      const res = await axios.post(`/pms/reservations/${bookingId}/vcc/reveal`);
      setRevealed(res.data?.card || null);
      setRevealInfo({
        view_count: res.data?.view_count,
        remaining_views: res.data?.remaining_views,
        locked: res.data?.locked,
      });
      await load();
    } catch (e) {
      toast.error('Görüntüleme hatası: ' + (e.response?.data?.detail || e.message));
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    setShowDelete(false);
    setBusy(true);
    try {
      await axios.delete(`/pms/reservations/${bookingId}/vcc`);
      toast.success('Kart bilgisi kalıcı olarak silindi');
      setRevealed(null);
      setRevealInfo(null);
      await load();
      onRefresh?.();
    } catch (e) {
      toast.error('Silme hatası: ' + (e.response?.data?.detail || e.message));
    } finally {
      setBusy(false);
    }
  };

  const copyToClipboard = (text, label) => {
    if (!text) return;
    navigator.clipboard?.writeText(String(text).replace(/\s/g, ''));
    toast.success(`${label} panoya kopyalandı`);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-gray-500">
        <Loader2 className="w-5 h-5 animate-spin mr-2" /> Yükleniyor...
      </div>
    );
  }

  const hasVcc = !!status?.has_vcc;
  const vcc = status?.vcc || {};
  const viewCount = vcc.view_count ?? 0;
  const maxViews = vcc.max_views ?? MAX_VIEWS;
  const remaining = Math.max(0, maxViews - viewCount);
  const locked = !!vcc.locked;

  return (
    <div className="max-w-3xl space-y-4" data-testid="vcc-tab">
      {/* Warning banner */}
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-start gap-2 text-sm text-amber-800">
        <ShieldAlert className="w-4 h-4 mt-0.5 flex-shrink-0" />
        <div>
          <div className="font-medium">Hassas veri — PCI kontrollü alan</div>
          <div className="text-xs mt-0.5">
            Kart numarası AES-256-GCM ile şifreli saklanır. Her görüntüleme denetim kaydına işlenir ve{' '}
            <strong>maksimum 3 kez</strong> görüntülenebilir. Sonrasında kart kalıcı olarak kilitlenir.
          </div>
        </div>
      </div>

      {!hasVcc ? (
        <Card>
          <CardContent className="p-6 text-center">
            <CreditCard className="w-10 h-10 text-gray-300 mx-auto mb-2" />
            <div className="text-sm text-gray-600 mb-4">
              Bu rezervasyon için kayıtlı sanal kart yok.
            </div>
            {!showForm ? (
              <Button onClick={() => setShowForm(true)} variant="outline">
                <Plus className="w-4 h-4 mr-2" /> Manuel Kart Ekle
              </Button>
            ) : (
              <div className="text-left space-y-3 max-w-md mx-auto">
                <div>
                  <Label className="text-xs">Kart Sahibi *</Label>
                  <Input
                    value={form.card_holder}
                    onChange={(e) => setForm({ ...form, card_holder: e.target.value })}
                    placeholder="AD SOYAD"
                  />
                </div>
                <div>
                  <Label className="text-xs">Kart Numarası *</Label>
                  <Input
                    value={form.card_number}
                    onChange={(e) => setForm({ ...form, card_number: e.target.value })}
                    placeholder="4111 1111 1111 1111"
                    maxLength={25}
                  />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <Label className="text-xs">Son Kullanma (AA/YY) *</Label>
                    <Input
                      value={form.expiry}
                      onChange={(e) => setForm({ ...form, expiry: e.target.value })}
                      placeholder="12/28"
                      maxLength={7}
                    />
                  </div>
                  <div>
                    <Label className="text-xs">CVV</Label>
                    <Input
                      value={form.cvv}
                      onChange={(e) => setForm({ ...form, cvv: e.target.value })}
                      placeholder="123"
                      maxLength={4}
                      type="password"
                    />
                  </div>
                </div>
                <div>
                  <Label className="text-xs">Kart Türü</Label>
                  <select
                    className="w-full border rounded px-3 py-2 text-sm"
                    value={form.card_type}
                    onChange={(e) => setForm({ ...form, card_type: e.target.value })}
                  >
                    <option value="virtual">Sanal (VCC)</option>
                    <option value="credit">Kredi</option>
                    <option value="debit">Banka</option>
                  </select>
                </div>
                <div className="flex gap-2 justify-end pt-2">
                  <Button variant="outline" onClick={() => setShowForm(false)} disabled={busy}>
                    İptal
                  </Button>
                  <Button onClick={handleStore} disabled={busy}>
                    {busy && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                    Güvenli Kaydet
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <CreditCard className="w-5 h-5" /> Kayıtlı Kart
              </CardTitle>
              <div className="flex items-center gap-2">
                {locked && (
                  <Badge className="bg-red-100 text-red-700 border-red-300">
                    <Lock className="w-3 h-3 mr-1" /> Kilitli
                  </Badge>
                )}
                <Badge variant="outline" className="font-mono text-xs">
                  {viewCount}/{maxViews} görüntüleme
                </Badge>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Masked card display */}
            <div className="bg-gradient-to-br from-slate-800 to-slate-600 text-white rounded-xl p-5 shadow-lg">
              <div className="flex justify-between items-start mb-6">
                <CreditCard className="w-8 h-8 opacity-70" />
                <Badge className="bg-white/20 text-white border-0 text-[10px] uppercase">
                  {vcc.source || 'manual'}
                </Badge>
              </div>
              <div className="font-mono text-xl tracking-wider mb-4">
                {formatCardNumber(vcc.card_mask) || '•••• •••• •••• ••••'}
              </div>
              <div className="flex justify-between text-xs opacity-80">
                <span>
                  Kayıt: {vcc.created_at ? new Date(vcc.created_at).toLocaleDateString('tr-TR') : '—'}
                </span>
                <span>Kalan: {remaining}</span>
              </div>
            </div>

            {/* View counter progress */}
            <div>
              <div className="flex justify-between text-xs text-gray-600 mb-1">
                <span>Kalan görüntüleme</span>
                <span>
                  {remaining} / {maxViews}
                </span>
              </div>
              <div className="flex gap-1">
                {Array.from({ length: maxViews }).map((_, i) => (
                  <div
                    key={i}
                    className={`h-2 flex-1 rounded ${
                      i < viewCount ? 'bg-red-400' : 'bg-green-400'
                    }`}
                  />
                ))}
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-2 justify-end flex-wrap">
              <Button
                variant="destructive"
                size="sm"
                onClick={() => setShowDelete(true)}
                disabled={busy}
              >
                <Trash2 className="w-4 h-4 mr-2" /> Sil
              </Button>
              <Button
                onClick={() => setShowConfirm(true)}
                disabled={busy || locked || remaining === 0}
                size="sm"
              >
                {locked || remaining === 0 ? (
                  <>
                    <EyeOff className="w-4 h-4 mr-2" /> Görüntülenemez
                  </>
                ) : (
                  <>
                    <Eye className="w-4 h-4 mr-2" /> Kartı Görüntüle ({remaining} kaldı)
                  </>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Confirm reveal */}
      <AlertDialog open={showConfirm} onOpenChange={setShowConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <ShieldAlert className="w-5 h-5 text-amber-600" />
              Kart bilgilerini görüntülemek istiyor musunuz?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Bu işlem görüntüleme hakkınızdan <strong>1 adet</strong> tüketecek. İşlem denetim
              kaydına adınız ve zamanınızla birlikte yazılacak. Kalan hak: <strong>{remaining}</strong>
              . Sıfıra ulaşınca kart kalıcı olarak kilitlenir.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Vazgeç</AlertDialogCancel>
            <AlertDialogAction onClick={handleReveal}>Evet, göster</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Confirm delete */}
      <AlertDialog open={showDelete} onOpenChange={setShowDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Kartı kalıcı olarak silmek istiyor musunuz?</AlertDialogTitle>
            <AlertDialogDescription>
              Bu işlem geri alınamaz. Şifrelenmiş kart verisi veri tabanından silinecek.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Vazgeç</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-red-600 hover:bg-red-700">
              Sil
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Revealed card modal */}
      <Dialog
        open={!!revealed}
        onOpenChange={(o) => {
          if (!o) {
            setRevealed(null);
            setRevealInfo(null);
          }
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-green-600" />
              Kart Bilgileri
            </DialogTitle>
          </DialogHeader>
          {revealed && (
            <div className="space-y-3">
              <div className="bg-gradient-to-br from-blue-600 to-indigo-700 text-white rounded-xl p-5">
                <div className="text-xs opacity-80 mb-1">Kart Sahibi</div>
                <div className="font-semibold uppercase mb-4">{revealed.card_holder}</div>
                <div className="text-xs opacity-80 mb-1">Kart Numarası</div>
                <div className="font-mono text-lg tracking-wider flex items-center justify-between">
                  <span>{formatCardNumber(revealed.card_number)}</span>
                  <button
                    onClick={() => copyToClipboard(revealed.card_number, 'Kart numarası')}
                    className="opacity-70 hover:opacity-100"
                    title="Kopyala"
                  >
                    <Copy className="w-4 h-4" />
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-4 mt-4">
                  <div>
                    <div className="text-xs opacity-80 mb-1">Son Kullanma</div>
                    <div className="font-mono flex items-center gap-2">
                      {revealed.expiry}
                      <button onClick={() => copyToClipboard(revealed.expiry, 'Son kullanma')}>
                        <Copy className="w-3 h-3 opacity-70" />
                      </button>
                    </div>
                  </div>
                  <div>
                    <div className="text-xs opacity-80 mb-1">CVV</div>
                    <div className="font-mono flex items-center gap-2">
                      {revealed.cvv || '—'}
                      {revealed.cvv && (
                        <button onClick={() => copyToClipboard(revealed.cvv, 'CVV')}>
                          <Copy className="w-3 h-3 opacity-70" />
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </div>
              <div className="bg-amber-50 border border-amber-200 rounded p-2 text-xs text-amber-800">
                <strong>Uyarı:</strong> Bu bilgi tarayıcıda saklanmaz. Pencereyi kapattığınızda
                silinecektir. Kalan görüntüleme hakkı: <strong>{revealInfo?.remaining_views ?? 0}</strong>.
                {revealInfo?.locked && (
                  <div className="mt-1 text-red-700 font-medium">
                    Kart artık kilitlendi, bir daha görüntülenemez.
                  </div>
                )}
              </div>
            </div>
          )}
          <DialogFooter>
            <Button
              onClick={() => {
                setRevealed(null);
                setRevealInfo(null);
              }}
            >
              Kapat
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
