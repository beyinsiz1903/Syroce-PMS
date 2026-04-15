import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  CreditCard, Eye, EyeOff, Lock, Shield, AlertTriangle,
  Plus, Trash2, Loader2, Check, Info
} from 'lucide-react';
import { API } from './helpers';

export function OnlinePaymentTab({ booking, onRefresh }) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [revealing, setRevealing] = useState(false);
  const [revealedCard, setRevealedCard] = useState(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [form, setForm] = useState({
    card_holder: '', card_number: '', expiry: '', cvv: '', card_type: 'virtual'
  });

  const loadStatus = useCallback(async () => {
    try {
      const res = await axios.get(`/pms/reservations/${booking.id}/vcc/status`);
      setStatus(res.data);
    } catch {
      setStatus({ has_vcc: false });
    }
    setLoading(false);
  }, [booking.id]);

  useEffect(() => { loadStatus(); }, [loadStatus]);

  const handleReveal = async () => {
    if (revealing) return;
    const vcc = status?.vcc;
    if (!vcc || vcc.locked) return;

    const remaining = vcc.max_views - vcc.view_count;
    if (remaining <= 0) return;

    if (!window.confirm(
      `Kart bilgilerini görüntülemek istediğinize emin misiniz?\n\nKalan hak: ${remaining}/${vcc.max_views}\nBu işlem geri alınamaz.`
    )) return;

    setRevealing(true);
    try {
      const res = await axios.post(`/pms/reservations/${booking.id}/vcc/reveal`);
      setRevealedCard(res.data);
      // Update local status
      setStatus(prev => ({
        ...prev,
        vcc: {
          ...prev.vcc,
          view_count: res.data.view_count,
          locked: res.data.locked,
        },
      }));
      toast.success(`Kart bilgileri görüntülendi (${res.data.view_count}/${res.data.max_views})`);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Kart bilgileri görüntülenemiyor');
    }
    setRevealing(false);
  };

  const handleStore = async () => {
    if (!form.card_holder || !form.card_number || !form.expiry) {
      toast.error('Kart sahibi, kart numarası ve son kullanım tarihi zorunludur');
      return;
    }
    setSaving(true);
    try {
      await axios.post(`/pms/reservations/${booking.id}/vcc`, form);
      toast.success('Kart bilgileri kaydedildi');
      setShowAddForm(false);
      setForm({ card_holder: '', card_number: '', expiry: '', cvv: '', card_type: 'virtual' });
      await loadStatus();
      onRefresh?.();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Kart kaydedilemedi');
    }
    setSaving(false);
  };

  const handleDelete = async () => {
    if (!window.confirm('Kart bilgileri kalıcı olarak silinecek. Emin misiniz?')) return;
    setDeleting(true);
    try {
      await axios.delete(`/pms/reservations/${booking.id}/vcc`);
      toast.success('Kart bilgileri silindi');
      setStatus({ has_vcc: false });
      setRevealedCard(null);
      onRefresh?.();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Silinemedi');
    }
    setDeleting(false);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12" data-testid="online-payment-loading">
        <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
      </div>
    );
  }

  const vcc = status?.vcc;
  const hasCard = status?.has_vcc;
  const isLocked = vcc?.locked || (vcc?.view_count >= vcc?.max_views);
  const remaining = hasCard ? (vcc.max_views - vcc.view_count) : 0;

  return (
    <div className="space-y-6" data-testid="online-payment-tab">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <CreditCard className="w-5 h-5 text-indigo-600" />
          <h3 className="text-sm font-semibold text-gray-800">Online Ödeme / Sanal Kart</h3>
        </div>
        {!hasCard && !showAddForm && (
          <Button
            size="sm"
            onClick={() => setShowAddForm(true)}
            className="bg-indigo-600 hover:bg-indigo-700 text-white h-8 text-xs"
            data-testid="btn-add-vcc"
          >
            <Plus className="w-3 h-3 mr-1" /> Kart Ekle
          </Button>
        )}
      </div>

      {/* Info Banner */}
      <div className="flex items-start gap-2 bg-blue-50 border border-blue-200 rounded-lg px-3 py-2">
        <Info className="w-4 h-4 text-blue-500 mt-0.5 flex-shrink-0" />
        <p className="text-xs text-blue-700">
          OTA ve acente sanal kart bilgileri sifrelenerek saklanir.
          Guvenlik nedeniyle kart detayları <strong>en fazla 3 kez</strong> goruntulenebilir.
        </p>
      </div>

      {/* Add Card Form */}
      {showAddForm && !hasCard && (
        <div className="border-2 border-dashed border-indigo-200 rounded-lg p-4 bg-indigo-50/30 space-y-3" data-testid="vcc-add-form">
          <div className="text-sm font-semibold text-indigo-800">Yeni Kart Bilgisi Ekle</div>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <Label className="text-xs">Kart Sahibi *</Label>
              <Input
                value={form.card_holder}
                onChange={e => setForm(p => ({ ...p, card_holder: e.target.value }))}
                placeholder="Ad Soyad"
                className="h-8 text-sm"
                data-testid="input-card-holder"
              />
            </div>
            <div className="col-span-2">
              <Label className="text-xs">Kart Numarasi *</Label>
              <Input
                value={form.card_number}
                onChange={e => setForm(p => ({ ...p, card_number: e.target.value }))}
                placeholder="4111 1111 1111 1111"
                className="h-8 text-sm font-mono"
                data-testid="input-card-number"
              />
            </div>
            <div>
              <Label className="text-xs">Son Kullanim *</Label>
              <Input
                value={form.expiry}
                onChange={e => setForm(p => ({ ...p, expiry: e.target.value }))}
                placeholder="MM/YY"
                className="h-8 text-sm"
                data-testid="input-card-expiry"
              />
            </div>
            <div>
              <Label className="text-xs">CVV</Label>
              <Input
                value={form.cvv}
                onChange={e => setForm(p => ({ ...p, cvv: e.target.value }))}
                placeholder="***"
                type="password"
                className="h-8 text-sm"
                data-testid="input-card-cvv"
              />
            </div>
            <div className="col-span-2">
              <Label className="text-xs">Kart Tipi</Label>
              <select
                value={form.card_type}
                onChange={e => setForm(p => ({ ...p, card_type: e.target.value }))}
                className="w-full h-8 text-sm border rounded-md px-2 bg-white"
                data-testid="select-card-type"
              >
                <option value="virtual">Sanal Kart</option>
                <option value="credit">Kredi Karti</option>
                <option value="debit">Banka Karti</option>
              </select>
            </div>
          </div>
          <div className="flex gap-2 pt-1">
            <Button
              size="sm"
              onClick={handleStore}
              disabled={saving}
              className="bg-indigo-600 hover:bg-indigo-700 text-white h-8 text-xs"
              data-testid="btn-save-vcc"
            >
              {saving ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Check className="w-3 h-3 mr-1" />}
              Sifrele ve Kaydet
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setShowAddForm(false)}
              className="h-8 text-xs"
            >
              İptal
            </Button>
          </div>
        </div>
      )}

      {/* Card Status */}
      {hasCard && (
        <div className="border rounded-xl overflow-hidden" data-testid="vcc-card-status">
          {/* Card visual */}
          <div className="bg-gradient-to-br from-slate-800 via-slate-700 to-slate-900 p-5 text-white relative">
            <div className="flex items-center justify-between mb-4">
              <Badge className={`text-[10px] border ${
                vcc.card_type === 'virtual'
                  ? 'bg-violet-500/20 text-violet-200 border-violet-400/30'
                  : vcc.card_type === 'credit'
                    ? 'bg-amber-500/20 text-amber-200 border-amber-400/30'
                    : 'bg-emerald-500/20 text-emerald-200 border-emerald-400/30'
              }`}>
                {vcc.card_type === 'virtual' ? 'Sanal Kart' : vcc.card_type === 'credit' ? 'Kredi Karti' : 'Banka Karti'}
              </Badge>
              <CreditCard className="w-6 h-6 text-white/40" />
            </div>
            <div className="font-mono text-lg tracking-widest mb-3" data-testid="vcc-card-mask">
              {vcc.card_mask || '**** **** **** ****'}
            </div>
            <div className="flex items-center justify-between text-xs text-white/60">
              <span>{vcc.source || 'Manuel'}</span>
              <span>{vcc.created_at ? new Date(vcc.created_at).toLocaleDateString('tr-TR') : ''}</span>
            </div>
          </div>

          {/* View counter and actions */}
          <div className="p-4 space-y-3 bg-white">
            {/* View counter bar */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {isLocked ? (
                  <Lock className="w-4 h-4 text-red-500" />
                ) : (
                  <Shield className="w-4 h-4 text-emerald-500" />
                )}
                <span className="text-sm font-medium text-gray-700">
                  Goruntuleme: {vcc.view_count}/{vcc.max_views}
                </span>
              </div>
              <Badge className={`text-xs ${
                isLocked
                  ? 'bg-red-100 text-red-700 border-red-200'
                  : remaining === 1
                    ? 'bg-amber-100 text-amber-700 border-amber-200'
                    : 'bg-emerald-100 text-emerald-700 border-emerald-200'
              }`} data-testid="vcc-remaining-badge">
                {isLocked ? 'Kilitlendi' : `${remaining} hak kaldi`}
              </Badge>
            </div>

            {/* Progress bar */}
            <div className="w-full bg-gray-100 rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all ${
                  isLocked ? 'bg-red-500' : remaining === 1 ? 'bg-amber-500' : 'bg-emerald-500'
                }`}
                style={{ width: `${(vcc.view_count / vcc.max_views) * 100}%` }}
                data-testid="vcc-progress-bar"
              />
            </div>

            {/* Warning when 1 view left */}
            {remaining === 1 && !isLocked && (
              <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0" />
                <span className="text-xs text-amber-700">Son goruntuleme hakkiniz kaldi!</span>
              </div>
            )}

            {/* Locked message */}
            {isLocked && (
              <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2" data-testid="vcc-locked-msg">
                <Lock className="w-4 h-4 text-red-500 flex-shrink-0" />
                <span className="text-xs text-red-700">
                  Kart bilgileri kalici olarak kilitlendi. Goruntuleme hakki dolmustur.
                </span>
              </div>
            )}

            {/* Action buttons */}
            <div className="flex gap-2 pt-1">
              {!isLocked && (
                <Button
                  size="sm"
                  onClick={handleReveal}
                  disabled={revealing}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white h-9 text-xs flex-1"
                  data-testid="btn-reveal-vcc"
                >
                  {revealing ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />
                  ) : (
                    <Eye className="w-3.5 h-3.5 mr-1.5" />
                  )}
                  Kart Bilgilerini Goruntule ({remaining} hak)
                </Button>
              )}
              <Button
                size="sm"
                variant="outline"
                onClick={handleDelete}
                disabled={deleting}
                className="h-9 text-xs text-red-600 border-red-200 hover:bg-red-50"
                data-testid="btn-delete-vcc"
              >
                {deleting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Revealed Card Details */}
      {revealedCard && (
        <div className="border-2 border-indigo-200 rounded-xl p-4 bg-indigo-50/30 space-y-3" data-testid="vcc-revealed-details">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Eye className="w-4 h-4 text-indigo-600" />
              <span className="text-sm font-semibold text-indigo-800">Kart Detaylari</span>
            </div>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setRevealedCard(null)}
              className="h-7 text-xs text-gray-500"
              data-testid="btn-hide-vcc"
            >
              <EyeOff className="w-3 h-3 mr-1" /> Gizle
            </Button>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <Label className="text-xs text-gray-500">Kart Sahibi</Label>
              <div className="bg-white border rounded-lg px-3 py-2 text-sm font-medium" data-testid="revealed-card-holder">
                {revealedCard.card?.card_holder}
              </div>
            </div>
            <div className="col-span-2">
              <Label className="text-xs text-gray-500">Kart Numarasi</Label>
              <div className="bg-white border rounded-lg px-3 py-2 text-sm font-mono tracking-wider" data-testid="revealed-card-number">
                {revealedCard.card?.card_number}
              </div>
            </div>
            <div>
              <Label className="text-xs text-gray-500">Son Kullanim</Label>
              <div className="bg-white border rounded-lg px-3 py-2 text-sm" data-testid="revealed-card-expiry">
                {revealedCard.card?.expiry}
              </div>
            </div>
            {revealedCard.card?.cvv && (
              <div>
                <Label className="text-xs text-gray-500">CVV</Label>
                <div className="bg-white border rounded-lg px-3 py-2 text-sm font-mono" data-testid="revealed-card-cvv">
                  {revealedCard.card?.cvv}
                </div>
              </div>
            )}
          </div>
          <div className="flex items-center gap-2 text-xs text-gray-500 pt-1">
            <Shield className="w-3 h-3" />
            <span>
              Goruntuleme: {revealedCard.view_count}/{revealedCard.max_views}
              {revealedCard.remaining_views > 0 && ` — ${revealedCard.remaining_views} hak kaldi`}
              {revealedCard.locked && ' — Kilitlendi'}
            </span>
          </div>
        </div>
      )}

      {/* No card state */}
      {!hasCard && !showAddForm && (
        <div className="text-center py-8 border-2 border-dashed border-gray-200 rounded-xl" data-testid="vcc-empty-state">
          <CreditCard className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="text-sm text-gray-500 mb-1">Kayıtlı kart bilgisi bulunamadı</p>
          <p className="text-xs text-gray-400">OTA veya acente tarafindan gonderilen sanal kart bilgilerini ekleyebilirsiniz</p>
        </div>
      )}
    </div>
  );
}
