import React, { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Badge } from './ui/badge';
import { Split, CheckCircle, XCircle, AlertTriangle } from 'lucide-react';

/**
 * SplitFolioDialog — Charge-based folio split.
 * Backed by POST /pms-core/folio/split (folio_hardening_service.split_folio).
 * Backend currently supports only by-item (charge_ids) splits — even/custom
 * amount splits are not implemented in the hardening service.
 */
const SplitFolioDialog = ({ folio, onClose, onSuccess }) => {
  const [selectedCharges, setSelectedCharges] = useState([]);
  const [targetFolioType, setTargetFolioType] = useState('guest');
  const [reason, setReason] = useState('');
  const [processing, setProcessing] = useState(false);

  const folioCharges = Array.isArray(folio.charges) ? folio.charges : [];
  const folioBalance = Number(folio.balance) || 0;

  const toggleCharge = (chargeId) => {
    setSelectedCharges((prev) =>
      prev.includes(chargeId) ? prev.filter((c) => c !== chargeId) : [...prev, chargeId]
    );
  };

  const selectedTotal = folioCharges
    .filter((c) => selectedCharges.includes(c.id || c.charge_id))
    .reduce((s, c) => s + Number(c.total ?? c.amount ?? c.charge_amount ?? 0), 0);

  const handleSplit = async () => {
    if (selectedCharges.length === 0) {
      toast.error('En az bir kalem seçin');
      return;
    }
    if (selectedCharges.length === folioCharges.length) {
      toast.error("Tüm kalemler seçilemez — orijinal folio'da en az bir kalem kalmalı");
      return;
    }
    if (!reason.trim()) {
      toast.error('Bölme sebebini yazın');
      return;
    }

    try {
      setProcessing(true);
      const response = await axios.post('/pms-core/folio/split', {
        source_folio_id: folio.id,
        charge_ids: selectedCharges,
        target_folio_type: targetFolioType,
        reason: reason.trim(),
      });

      toast.success(
        <div>
          <p className="font-semibold">Folio başarıyla bölündü!</p>
          <p className="text-xs">
            {response.data?.transferred_charges} kalem · ${response.data?.transferred_amount?.toFixed(2)} aktarıldı
          </p>
        </div>
      );

      if (onSuccess) onSuccess();
      if (onClose) onClose();
    } catch (error) {
      const detail = error.response?.data?.detail;
      toast.error(
        typeof detail === 'string'
          ? detail
          : detail?.error || 'Folio bölünemedi'
      );
    } finally {
      setProcessing(false);
    }
  };

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
        <div className="p-4 bg-gray-50 rounded-lg">
          <div className="grid grid-cols-2 gap-4">
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
        </div>

        {/* Empty-state for charges */}
        {folioCharges.length === 0 ? (
          <div className="p-4 bg-yellow-50 border border-yellow-200 rounded flex items-start gap-2">
            <AlertTriangle className="w-5 h-5 text-yellow-700 mt-0.5" />
            <div className="text-sm text-yellow-800">
              Bu folioda görüntülenebilen masraf kalemi yok. Bölme işlemi için folio detayını
              açıp kalemleri yükleyin, sonra tekrar deneyin.
            </div>
          </div>
        ) : (
          <>
            {/* Target folio type */}
            <div>
              <label className="text-sm font-medium mb-2 block">Hedef Folio Türü</label>
              <div className="flex gap-2">
                {[
                  { v: 'guest', label: 'Misafir' },
                  { v: 'company', label: 'Şirket' },
                  { v: 'master', label: 'Master' },
                ].map((opt) => (
                  <Button
                    key={opt.v}
                    type="button"
                    variant={targetFolioType === opt.v ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setTargetFolioType(opt.v)}
                  >
                    {opt.label}
                  </Button>
                ))}
              </div>
            </div>

            {/* By-item charge selection */}
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
              <div className="space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <span>Orijinal Folio:</span>
                  <span className="font-medium">{folio.folio_number}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Aktarılacak:</span>
                  <Badge variant="outline">{selectedCharges.length} kalem</Badge>
                </div>
                <div className="flex items-center justify-between font-semibold text-blue-700">
                  <span>Aktarılacak Tutar:</span>
                  <span>${selectedTotal.toFixed(2)}</span>
                </div>
              </div>
            </div>
          </>
        )}

        {/* Actions */}
        <div className="flex space-x-3">
          <Button
            onClick={handleSplit}
            disabled={processing || folioCharges.length === 0}
            className="flex-1"
          >
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
            ⚠️ <strong>Uyarı:</strong> Bu işlem geri alınamaz. Seçilen kalemler yeni bir folioya
            taşınır ve orijinal folionun bakiyesi yeniden hesaplanır.
          </p>
        </div>
      </CardContent>
    </Card>
  );
};

export default SplitFolioDialog;
