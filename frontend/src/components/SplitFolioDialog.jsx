import React, { useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Badge } from './ui/badge';
import { Split, CheckCircle, XCircle, AlertTriangle, Plus, Trash2 } from 'lucide-react';

/**
 * SplitFolioDialog
 *  - by_item  → POST /pms-core/folio/split           (charge_ids based)
 *  - even     → POST /pms-core/folio/split-by-amount (equal monetary splits)
 *  - custom   → POST /pms-core/folio/split-by-amount (per-target amounts)
 */
const SplitFolioDialog = ({ folio, onClose, onSuccess }) => {
  const [mode, setMode] = useState('by_item'); // by_item | even | custom
  const [targetFolioType, setTargetFolioType] = useState('guest');
  const [reason, setReason] = useState('');
  const [processing, setProcessing] = useState(false);

  // by_item
  const [selectedCharges, setSelectedCharges] = useState([]);

  // even
  const [evenSplits, setEvenSplits] = useState(2);

  // custom: [{amount, target_folio_type}]
  const [customSplits, setCustomSplits] = useState([
    { amount: '', target_folio_type: 'guest' },
  ]);

  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  const folioCharges = Array.isArray(folio.charges) ? folio.charges : [];
  const folioBalance = Number(folio.balance) || 0;

  const toggleCharge = (chargeId) => {
    setSelectedCharges((prev) =>
      prev.includes(chargeId) ? prev.filter((c) => c !== chargeId) : [...prev, chargeId]
    );
  };

  const selectedTotal = useMemo(
    () =>
      folioCharges
        .filter((c) => selectedCharges.includes(c.id || c.charge_id))
        .reduce((s, c) => s + Number(c.total ?? c.amount ?? c.charge_amount ?? 0), 0),
    [folioCharges, selectedCharges]
  );

  const evenPerSplit = useMemo(() => {
    if (!folioBalance || evenSplits < 2) return 0;
    // Reserve at least 0.01 in source so it doesn't drain to zero;
    // backend rejects total >= source_balance.
    const transferable = Math.max(0, folioBalance - 0.01);
    const each = transferable / evenSplits;
    return Math.floor(each * 100) / 100;
  }, [folioBalance, evenSplits]);

  const customTotal = useMemo(
    () => customSplits.reduce((s, x) => s + (Number(x.amount) || 0), 0),
    [customSplits]
  );

  const updateCustomRow = (idx, patch) =>
    setCustomSplits((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));

  const addCustomRow = () =>
    setCustomSplits((prev) => [...prev, { amount: '', target_folio_type: 'guest' }]);

  const removeCustomRow = (idx) =>
    setCustomSplits((prev) => (prev.length === 1 ? prev : prev.filter((_, i) => i !== idx)));

  const handleSplit = async () => {
    if (!reason.trim()) {
      toast.error('Bölme sebebini yazın');
      return;
    }

    try {
      setProcessing(true);

      if (mode === 'by_item') {
        if (selectedCharges.length === 0) {
          toast.error('En az bir kalem seçin');
          return;
        }
        if (selectedCharges.length === folioCharges.length) {
          toast.error("Tüm kalemler seçilemez — orijinalde en az bir kalem kalmalı");
          return;
        }
        const res = await axios.post('/pms-core/folio/split', {
          source_folio_id: folio.id,
          charge_ids: selectedCharges,
          target_folio_type: targetFolioType,
          reason: reason.trim(),
        });
        toast.success(
          `Folio bölündü — ${res.data?.transferred_charges} kalem · $${Number(
            res.data?.transferred_amount || 0
          ).toFixed(2)} aktarıldı`
        );
      } else if (mode === 'even') {
        if (evenSplits < 2) {
          toast.error('En az 2 parça olmalı');
          return;
        }
        if (evenPerSplit <= 0) {
          toast.error('Bölmek için yeterli bakiye yok');
          return;
        }
        const splits = Array.from({ length: evenSplits - 1 }, () => ({
          amount: evenPerSplit,
          target_folio_type: targetFolioType,
        }));
        const res = await axios.post('/pms-core/folio/split-by-amount', {
          source_folio_id: folio.id,
          splits,
          reason: reason.trim(),
        });
        toast.success(
          `Folio ${evenSplits} eşit parçaya bölündü — ${res.data?.target_count} yeni folio · $${Number(
            res.data?.transferred_amount || 0
          ).toFixed(2)} aktarıldı`
        );
      } else if (mode === 'custom') {
        const cleaned = customSplits
          .map((r) => ({ amount: Number(r.amount) || 0, target_folio_type: r.target_folio_type }))
          .filter((r) => r.amount > 0);
        if (cleaned.length === 0) {
          toast.error('En az bir tutar girin');
          return;
        }
        if (customTotal >= folioBalance) {
          toast.error(
            `Toplam (${customTotal.toFixed(2)}) bakiyeden (${folioBalance.toFixed(2)}) küçük olmalı`
          );
          return;
        }
        const res = await axios.post('/pms-core/folio/split-by-amount', {
          source_folio_id: folio.id,
          splits: cleaned,
          reason: reason.trim(),
        });
        toast.success(
          `${res.data?.target_count} hedefe $${Number(res.data?.transferred_amount || 0).toFixed(
            2
          )} aktarıldı`
        );
      }

      if (onSuccess) onSuccess();
      if (onClose) onClose();
    } catch (error) {
      const detail = error.response?.data?.detail;
      toast.error(
        typeof detail === 'string' ? detail : detail?.error || 'Folio bölünemedi'
      );
    } finally {
      setProcessing(false);
    }
  };

  const folioTypeButtons = (value, setValue) => (
    <div className="flex gap-2">
      {[
        { v: 'guest', label: 'Misafir' },
        { v: 'company', label: 'Şirket' },
        { v: 'master', label: 'Master' },
      ].map((opt) => (
        <Button
          key={opt.v}
          type="button"
          variant={value === opt.v ? 'default' : 'outline'}
          size="sm"
          onClick={() => setValue(opt.v)}
        >
          {opt.label}
        </Button>
      ))}
    </div>
  );

  return (
    <Card className="border-2 border-blue-500 max-w-2xl mx-auto">
      <CardHeader>
        <CardTitle className="flex items-center">
          <Split className="w-5 h-5 mr-2 text-blue-600" />
          Folio Böl - {folio.folio_number}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Folio Info */}
        <div className="p-4 bg-gray-50 rounded-lg grid grid-cols-2 gap-4">
          <div>
            <p className="text-sm text-gray-600">Folio No</p>
            <p className="font-bold">{folio.folio_number}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600">Misafir</p>
            <p className="font-bold">{folio.guest_name || 'N/A'}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600">Oda</p>
            <p className="font-bold">{folio.room_number || 'N/A'}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600">Toplam Bakiye</p>
            <p className="font-bold text-green-600">${folioBalance.toFixed(2)}</p>
          </div>
        </div>

        {/* Mode tabs */}
        <div className="flex gap-2 border-b pb-2">
          {[
            { v: 'by_item', label: 'Kaleme Göre' },
            { v: 'even', label: 'Eşit Böl' },
            { v: 'custom', label: 'Özel Tutar' },
          ].map((opt) => (
            <Button
              key={opt.v}
              type="button"
              variant={mode === opt.v ? 'default' : 'outline'}
              size="sm"
              onClick={() => setMode(opt.v)}
            >
              {opt.label}
            </Button>
          ))}
        </div>

        {/* BY ITEM */}
        {mode === 'by_item' && (
          <>
            {folioCharges.length === 0 ? (
              <div className="p-4 bg-yellow-50 border border-yellow-200 rounded flex items-start gap-2">
                <AlertTriangle className="w-5 h-5 text-yellow-700 mt-0.5" />
                <div className="text-sm text-yellow-800">
                  Bu folioda görüntülenebilen masraf kalemi yok. Kalem bazlı bölme için folio
                  detayını açıp kalemleri yükleyin veya "Eşit Böl" / "Özel Tutar" modunu kullanın.
                </div>
              </div>
            ) : (
              <>
                <div>
                  <label className="text-sm font-medium mb-2 block">Hedef Folio Türü</label>
                  {folioTypeButtons(targetFolioType, setTargetFolioType)}
                </div>
                <div>
                  <label className="text-sm font-medium mb-2 block">
                    Yeni folioya taşınacak kalemleri seçin
                  </label>
                  <div className="space-y-1 max-h-64 overflow-y-auto border rounded p-2">
                    {folioCharges.map((c) => {
                      const cid = c.id || c.charge_id;
                      const checked = selectedCharges.includes(cid);
                      return (
                        <label
                          key={cid}
                          className="flex items-center justify-between p-2 hover:bg-gray-50 cursor-pointer rounded"
                        >
                          <div className="flex items-center gap-2 flex-1">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => toggleCharge(cid)}
                            />
                            <div>
                              <div className="text-sm font-medium">
                                {c.description || c.charge_name || 'Kalem'}
                              </div>
                              <div className="text-xs text-gray-500">
                                {c.charge_category || c.category || ''}
                              </div>
                            </div>
                          </div>
                          <span className="font-semibold text-sm">
                            ${Number(c.total ?? c.amount ?? c.charge_amount ?? 0).toFixed(2)}
                          </span>
                        </label>
                      );
                    })}
                  </div>
                  <p className="text-xs text-gray-600 mt-2">
                    Seçilen: <strong>{selectedCharges.length}</strong> kalem · Toplam{' '}
                    <strong>${selectedTotal.toFixed(2)}</strong>
                  </p>
                </div>
              </>
            )}
          </>
        )}

        {/* EVEN */}
        {mode === 'even' && (
          <>
            <div>
              <label className="text-sm font-medium mb-2 block">Hedef Folio Türü</label>
              {folioTypeButtons(targetFolioType, setTargetFolioType)}
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Kaç parçaya bölünsün?</label>
              <Input
                type="number"
                min={2}
                max={20}
                value={evenSplits}
                onChange={(e) => setEvenSplits(Math.max(2, Math.min(20, Number(e.target.value) || 2)))}
              />
              <p className="text-xs text-gray-600 mt-2">
                Her parçaya: <strong>${evenPerSplit.toFixed(2)}</strong> · Yeni folio sayısı:{' '}
                <strong>{evenSplits - 1}</strong> (orijinal de bir parça olarak kalır)
              </p>
            </div>
          </>
        )}

        {/* CUSTOM */}
        {mode === 'custom' && (
          <div className="space-y-2">
            <label className="text-sm font-medium">Hedef folio başına tutar</label>
            {customSplits.map((row, idx) => (
              <div key={idx} className="flex gap-2 items-center">
                <Input
                  type="number"
                  step="0.01"
                  placeholder="Tutar"
                  value={row.amount}
                  onChange={(e) => updateCustomRow(idx, { amount: e.target.value })}
                  className="flex-1"
                />
                <select
                  className="border rounded px-2 py-2 text-sm"
                  value={row.target_folio_type}
                  onChange={(e) => updateCustomRow(idx, { target_folio_type: e.target.value })}
                >
                  <option value="guest">Misafir</option>
                  <option value="company">Şirket</option>
                  <option value="master">Master</option>
                </select>
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  onClick={() => removeCustomRow(idx)}
                  disabled={customSplits.length === 1}
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
            ))}
            <Button type="button" variant="outline" size="sm" onClick={addCustomRow}>
              <Plus className="w-4 h-4 mr-1" /> Hedef Ekle
            </Button>
            <p className="text-xs text-gray-600">
              Toplam aktarılacak: <strong>${customTotal.toFixed(2)}</strong> / Bakiye{' '}
              <strong>${folioBalance.toFixed(2)}</strong>
              {customTotal >= folioBalance && folioBalance > 0 && (
                <span className="text-red-600 ml-2">
                  ⚠ Bakiyeden küçük olmalı (orijinalde bir miktar kalmalı)
                </span>
              )}
            </p>
          </div>
        )}

        {/* Reason */}
        <div>
          <label className="text-sm font-medium mb-2 block">Bölme Sebebi</label>
          <Input
            placeholder="Örn: Şirket faturası ayrıştırma, misafir talebi…"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>

        {/* Preview */}
        <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <h4 className="font-semibold text-blue-900 mb-2">Önizleme</h4>
          <div className="space-y-1 text-sm">
            <div className="flex items-center justify-between">
              <span>Mod:</span>
              <Badge variant="outline">
                {mode === 'by_item' ? 'Kaleme Göre' : mode === 'even' ? 'Eşit Böl' : 'Özel Tutar'}
              </Badge>
            </div>
            {mode === 'by_item' && (
              <div className="flex items-center justify-between font-semibold text-blue-700">
                <span>Aktarılacak Tutar:</span>
                <span>${selectedTotal.toFixed(2)}</span>
              </div>
            )}
            {mode === 'even' && (
              <div className="flex items-center justify-between font-semibold text-blue-700">
                <span>Aktarılacak Toplam:</span>
                <span>${(evenPerSplit * (evenSplits - 1)).toFixed(2)}</span>
              </div>
            )}
            {mode === 'custom' && (
              <div className="flex items-center justify-between font-semibold text-blue-700">
                <span>Aktarılacak Toplam:</span>
                <span>${customTotal.toFixed(2)}</span>
              </div>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex space-x-3">
          <Button onClick={handleSplit} disabled={processing} className="flex-1">
            <CheckCircle className="w-4 h-4 mr-2" />
            {processing ? 'Bölünüyor…' : 'Bölmeyi Onayla'}
          </Button>
          <Button variant="outline" onClick={onClose} disabled={processing}>
            <XCircle className="w-4 h-4 mr-2" />
            İptal
          </Button>
        </div>

        <div className="bg-yellow-50 border border-yellow-200 rounded p-3">
          <p className="text-xs text-yellow-700">
            ⚠️ <strong>Uyarı:</strong> Bu işlem geri alınamaz. "Eşit" ve "Özel" modlarında yeni
            folioya tek bir "Folio bölme aktarımı" kalemi yazılır; orijinal folioya da eşdeğer
            negatif ayarlama eklenir, böylece toplam bakiye korunur.
          </p>
        </div>
      </CardContent>
    </Card>
  );
};

export default SplitFolioDialog;
