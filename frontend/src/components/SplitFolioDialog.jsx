import React, { useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Badge } from './ui/badge';
import { Split, CheckCircle, XCircle, AlertTriangle, Plus, Trash2, GripVertical } from 'lucide-react';
import { useTranslation } from 'react-i18next';

// Para birimi: uygulamanin geri kalani (FoliosTab/DocumentTabs/PricingTabs) gibi
// tr-TR bicimli tutar + " TL" goster. Folyolar tek para birimi tasir (varsayilan
// TRY, open_folio_service); per-kalem doviz/cevrim YOK. Onceki "$"+toFixed(2) ABD
// bicimi bir gosterim hatasiydi (ana ekran "47.700 TL" iken bolme ekrani
// minibar kalemini "$100.00" gosteriyordu).
const fmtTL = (v) => (Number(v) || 0).toLocaleString('tr-TR');

const chargeIdOf = (c) => c.id || c.charge_id;
const FOLIO_TYPE_LABELS = { guest: 'Misafir', company: 'Şirket', master: 'Master' };

/**
 * SplitFolioDialog
 *  - by_item  → POST /pms-core/folio/split           (charge_ids based)
 *  - even     → POST /pms-core/folio/split-by-amount (equal monetary splits)
 *  - custom   → POST /pms-core/folio/split-by-amount (per-target amounts)
 */
const SplitFolioDialog = ({ folio, onClose, onSuccess }) => {
  const { t } = useTranslation();
  const [mode, setMode] = useState('by_item'); // by_item | even | custom
  const [targetFolioType, setTargetFolioType] = useState('guest');
  const [reason, setReason] = useState('');
  const [processing, setProcessing] = useState(false);

  // by_item
  const [selectedCharges, setSelectedCharges] = useState([]);
  const [dragOverPane, setDragOverPane] = useState(null); // 'source' | 'target' | null

  // even
  const [evenSplits, setEvenSplits] = useState(2);

  // custom: [{amount, target_folio_type}]
  const [customSplits, setCustomSplits] = useState([
    { amount: '', target_folio_type: 'guest' },
  ]);

  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  const folioCharges = Array.isArray(folio.charges) ? folio.charges : [];
  const folioBalance = Number(folio.balance) || 0;

  // Booking kapsamlı ekstra masraflar folio_id taşımaz ve folio.balance'a
  // dâhil DEĞİLDİR (Task #426). Tutar tabanlı bölmede (eşit/özel) backend bu
  // ekstra masrafları kaynak folioya absorbe ettiğinden, bölünebilir bakiye =
  // folio bakiyesi + ekstra masraf toplamıdır. Aşağıdaki hesaplar bu artırılmış
  // bakiyeyi kullanır; "Kaleme Göre" akışı değişmez (kalem tek tek seçilir).
  const extraChargesTotal = useMemo(
    () =>
      folioCharges
        .filter((c) => !c.folio_id)
        .reduce((s, c) => s + Number(c.total ?? c.amount ?? c.charge_amount ?? 0), 0),
    [folioCharges]
  );
  const divisibleBalance = folioBalance + extraChargesTotal;

  // Mews tarzi iki-bolmeli surukle-birak: sol pano = ana folio (kalir),
  // sag pano = hedef folio (aktarilacak). Surukle-birak VEYA tikla ile tasinir.
  const moveToTarget = (cid) =>
    setSelectedCharges((prev) => (prev.includes(cid) ? prev : [...prev, cid]));
  const moveToSource = (cid) =>
    setSelectedCharges((prev) => prev.filter((x) => x !== cid));

  const onChargeDragStart = (e, cid) => {
    e.dataTransfer.setData('text/plain', cid);
    e.dataTransfer.effectAllowed = 'move';
  };
  const onPaneDragOver = (e, pane) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (dragOverPane !== pane) setDragOverPane(pane);
  };
  const onPaneDrop = (e, pane) => {
    e.preventDefault();
    const cid = e.dataTransfer.getData('text/plain');
    setDragOverPane(null);
    if (!cid) return;
    if (pane === 'target') moveToTarget(cid);
    else moveToSource(cid);
  };

  const renderChargeCard = (c, side) => {
    const cid = chargeIdOf(c);
    return (
      <div
        key={cid}
        draggable
        role="button"
        tabIndex={0}
        aria-label={`${c.description || c.charge_name || 'Kalem'} — ${
          side === 'source' ? 'hedefe taşı' : 'geri al'
        }`}
        onDragStart={(e) => onChargeDragStart(e, cid)}
        onClick={() => (side === 'source' ? moveToTarget(cid) : moveToSource(cid))}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            if (side === 'source') moveToTarget(cid);
            else moveToSource(cid);
          }
        }}
        title={
          side === 'source'
            ? 'Hedefe taşımak için sürükleyin veya tıklayın'
            : 'Geri almak için sürükleyin veya tıklayın'
        }
        data-testid={`split-charge-${cid}`}
        className="flex items-center justify-between gap-2 p-2 bg-white border rounded cursor-grab active:cursor-grabbing hover:border-sky-400 hover:shadow-sm focus:outline-none focus:ring-2 focus:ring-sky-400 transition select-none"
      >
        <div className="flex items-center gap-2 min-w-0">
          <GripVertical className="w-4 h-4 text-gray-400 shrink-0" />
          <div className="min-w-0">
            <div className="text-sm font-medium truncate">
              {c.description || c.charge_name || 'Kalem'}
            </div>
            <div className="text-xs text-gray-500 truncate">
              {c.charge_category || c.category || ''}
            </div>
          </div>
        </div>
        <span className="font-semibold text-sm whitespace-nowrap">
          {fmtTL(c.total ?? c.amount ?? c.charge_amount ?? 0)} TL
        </span>
      </div>
    );
  };

  const selectedTotal = useMemo(
    () =>
      folioCharges
        .filter((c) => selectedCharges.includes(c.id || c.charge_id))
        .reduce((s, c) => s + Number(c.total ?? c.amount ?? c.charge_amount ?? 0), 0),
    [folioCharges, selectedCharges]
  );

  const sourceCharges = useMemo(
    () => folioCharges.filter((c) => !selectedCharges.includes(chargeIdOf(c))),
    [folioCharges, selectedCharges]
  );
  const targetCharges = useMemo(
    () => folioCharges.filter((c) => selectedCharges.includes(chargeIdOf(c))),
    [folioCharges, selectedCharges]
  );
  const stayTotal = useMemo(
    () =>
      sourceCharges.reduce(
        (s, c) => s + Number(c.total ?? c.amount ?? c.charge_amount ?? 0),
        0
      ),
    [sourceCharges]
  );

  const evenPerSplit = useMemo(() => {
    if (!divisibleBalance || evenSplits < 2) return 0;
    // Reserve at least 0.01 in source so it doesn't drain to zero;
    // backend rejects total >= source_balance (ekstra masraflar dâhil).
    const transferable = Math.max(0, divisibleBalance - 0.01);
    const each = transferable / evenSplits;
    return Math.floor(each * 100) / 100;
  }, [divisibleBalance, evenSplits]);

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
        if (sourceCharges.length === 0) {
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
          `Folio bölündü — ${res.data?.transferred_charges} kalem · ${fmtTL(
            res.data?.transferred_amount
          )} TL aktarıldı`
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
          `Folio ${evenSplits} eşit parçaya bölündü — ${res.data?.target_count} yeni folio · ${fmtTL(
            res.data?.transferred_amount
          )} TL aktarıldı`
        );
      } else if (mode === 'custom') {
        const cleaned = customSplits
          .map((r) => ({ amount: Number(r.amount) || 0, target_folio_type: r.target_folio_type }))
          .filter((r) => r.amount > 0);
        if (cleaned.length === 0) {
          toast.error('En az bir tutar girin');
          return;
        }
        if (customTotal >= divisibleBalance) {
          toast.error(
            `Toplam (${fmtTL(customTotal)} TL) bakiyeden (${fmtTL(divisibleBalance)} TL) küçük olmalı`
          );
          return;
        }
        const res = await axios.post('/pms-core/folio/split-by-amount', {
          source_folio_id: folio.id,
          splits: cleaned,
          reason: reason.trim(),
        });
        toast.success(
          `${res.data?.target_count} hedefe ${fmtTL(
            res.data?.transferred_amount
          )} TL aktarıldı`
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
    <Card className="border-2 border-blue-500 max-w-3xl mx-auto">
      <CardHeader>
        <CardTitle className="flex items-center">
          <Split className="w-5 h-5 mr-2 text-blue-600" />
          {t('cm.components_SplitFolioDialog.folio_bol')} {folio.folio_number}
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
            <p className="text-sm text-gray-600">{t('cm.components_SplitFolioDialog.misafir')}</p>
            <p className="font-bold">{folio.guest_name || 'N/A'}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600">{t('cm.components_SplitFolioDialog.oda')}</p>
            <p className="font-bold">{folio.room_number || 'N/A'}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600">{t('cm.components_SplitFolioDialog.toplam_bakiye')}</p>
            <p className="font-bold text-green-600">{fmtTL(folioBalance)} TL</p>
            {extraChargesTotal > 0 && (
              <p className="text-xs text-gray-500 mt-0.5">
                + Ekstra masraf {fmtTL(extraChargesTotal)} TL = Bölünebilir{' '}
                <strong>{fmtTL(divisibleBalance)} TL</strong>
              </p>
            )}
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
                  {t('cm.components_SplitFolioDialog.bu_folioda_goruntulenebilen_masraf_kalem')}
                </div>
              </div>
            ) : (
              <>
                <div>
                  <label className="text-sm font-medium mb-2 block">{t('cm.components_SplitFolioDialog.hedef_folio_turu')}</label>
                  {folioTypeButtons(targetFolioType, setTargetFolioType)}
                </div>
                <div>
                  <label className="text-sm font-medium mb-2 block">
                    Kalemleri sürükleyip bırakın (veya tıklayın)
                  </label>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {/* Sol pano: Ana folio (kalan kalemler) */}
                    <div
                      onDragOver={(e) => onPaneDragOver(e, 'source')}
                      onDragLeave={() => setDragOverPane(null)}
                      onDrop={(e) => onPaneDrop(e, 'source')}
                      data-testid="split-source-pane"
                      className={`rounded-lg border-2 p-2 transition ${
                        dragOverPane === 'source'
                          ? 'border-sky-400 bg-sky-50'
                          : 'border-gray-200 bg-gray-50'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2 px-1">
                        <span className="text-xs font-semibold text-gray-700">
                          Ana Folio (kalır)
                        </span>
                        <Badge variant="outline" className="text-xs">
                          {sourceCharges.length}
                        </Badge>
                      </div>
                      <div className="space-y-1 max-h-64 overflow-y-auto min-h-[8rem]">
                        {sourceCharges.length === 0 ? (
                          <div className="text-xs text-red-600 p-4 text-center">
                            Orijinalde en az bir kalem kalmalı
                          </div>
                        ) : (
                          sourceCharges.map((c) => renderChargeCard(c, 'source'))
                        )}
                      </div>
                      <div className="text-xs text-gray-600 mt-2 px-1">
                        Kalan: <strong>{fmtTL(stayTotal)} TL</strong>
                      </div>
                    </div>

                    {/* Sağ pano: Hedef folio (aktarılacak kalemler) */}
                    <div
                      onDragOver={(e) => onPaneDragOver(e, 'target')}
                      onDragLeave={() => setDragOverPane(null)}
                      onDrop={(e) => onPaneDrop(e, 'target')}
                      data-testid="split-target-pane"
                      className={`rounded-lg border-2 p-2 transition ${
                        dragOverPane === 'target'
                          ? 'border-blue-500 bg-blue-50'
                          : 'border-blue-200 bg-blue-50/40'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2 px-1">
                        <span className="text-xs font-semibold text-blue-800">
                          Hedef Folio · {FOLIO_TYPE_LABELS[targetFolioType]}
                        </span>
                        <Badge variant="outline" className="text-xs">
                          {targetCharges.length}
                        </Badge>
                      </div>
                      <div className="space-y-1 max-h-64 overflow-y-auto min-h-[8rem]">
                        {targetCharges.length === 0 ? (
                          <div className="text-xs text-blue-700/70 p-6 text-center border-2 border-dashed border-blue-200 rounded">
                            Kalemleri buraya sürükleyin
                          </div>
                        ) : (
                          targetCharges.map((c) => renderChargeCard(c, 'target'))
                        )}
                      </div>
                      <div className="text-xs text-blue-800 mt-2 px-1">
                        Aktarılacak: <strong>{fmtTL(selectedTotal)} TL</strong>
                      </div>
                    </div>
                  </div>
                  <p className="text-xs text-gray-600 mt-2">
                    {t('cm.components_SplitFolioDialog.secilen')} <strong>{selectedCharges.length}</strong> {t('cm.components_SplitFolioDialog.kalem_toplam')}{' '}
                    <strong>{fmtTL(selectedTotal)} TL</strong>
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
              <label className="text-sm font-medium mb-2 block">{t('cm.components_SplitFolioDialog.hedef_folio_turu_e4829')}</label>
              {folioTypeButtons(targetFolioType, setTargetFolioType)}
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">{t('cm.components_SplitFolioDialog.kac_parcaya_bolunsun')}</label>
              <Input
                type="number"
                min={2}
                max={20}
                value={evenSplits}
                onChange={(e) => setEvenSplits(Math.max(2, Math.min(20, Number(e.target.value) || 2)))}
              />
              <p className="text-xs text-gray-600 mt-2">
                {t('cm.components_SplitFolioDialog.her_parcaya')} <strong>{fmtTL(evenPerSplit)} TL</strong> {t('cm.components_SplitFolioDialog.yeni_folio_sayisi')}{' '}
                <strong>{evenSplits - 1}</strong> {t('cm.components_SplitFolioDialog.orijinal_de_bir_parca_olarak_kalir')}
              </p>
            </div>
          </>
        )}

        {/* CUSTOM */}
        {mode === 'custom' && (
          <div className="space-y-2">
            <label className="text-sm font-medium">{t('cm.components_SplitFolioDialog.hedef_folio_basina_tutar')}</label>
            {customSplits.map((row, idx) => (
              <div key={idx} className="flex gap-2 items-center">
                <Input
                  type="number"
                  step="0.01"
                  placeholder={t('cm.components_SplitFolioDialog.tutar')}
                  value={row.amount}
                  onChange={(e) => updateCustomRow(idx, { amount: e.target.value })}
                  className="flex-1"
                />
                <select
                  className="border rounded px-2 py-2 text-sm"
                  value={row.target_folio_type}
                  onChange={(e) => updateCustomRow(idx, { target_folio_type: e.target.value })}
                >
                  <option value="guest">{t('cm.components_SplitFolioDialog.misafir_633b8')}</option>
                  <option value="company">{t('cm.components_SplitFolioDialog.sirket')}</option>
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
              <Plus className="w-4 h-4 mr-1" /> {t('cm.components_SplitFolioDialog.hedef_ekle')}
            </Button>
            <p className="text-xs text-gray-600">
              {t('cm.components_SplitFolioDialog.toplam_aktarilacak')} <strong>{fmtTL(customTotal)} TL</strong> {t('cm.components_SplitFolioDialog.bakiye')}{' '}
              <strong>{fmtTL(divisibleBalance)} TL</strong>
              {extraChargesTotal > 0 && (
                <span className="text-gray-400 ml-1">(ekstra masraf dâhil)</span>
              )}
              {customTotal >= divisibleBalance && divisibleBalance > 0 && (
                <span className="text-red-600 ml-2">
                  {t('cm.components_SplitFolioDialog.bakiyeden_kucuk_olmali_orijinalde_bir_mi')}
                </span>
              )}
            </p>
          </div>
        )}

        {/* Reason */}
        <div>
          <label className="text-sm font-medium mb-2 block">{t('cm.components_SplitFolioDialog.bolme_sebebi')}</label>
          <Input
            placeholder={t('cm.components_SplitFolioDialog.orn_sirket_faturasi_ayristirma_misafir_t')}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>

        {/* Preview */}
        <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <h4 className="font-semibold text-blue-900 mb-2">{t('cm.components_SplitFolioDialog.onizleme')}</h4>
          <div className="space-y-1 text-sm">
            <div className="flex items-center justify-between">
              <span>Mod:</span>
              <Badge variant="outline">
                {mode === 'by_item' ? 'Kaleme Göre' : mode === 'even' ? 'Eşit Böl' : 'Özel Tutar'}
              </Badge>
            </div>
            {mode === 'by_item' && (
              <div className="flex items-center justify-between font-semibold text-blue-700">
                <span>{t('cm.components_SplitFolioDialog.aktarilacak_tutar')}</span>
                <span>{fmtTL(selectedTotal)} TL</span>
              </div>
            )}
            {mode === 'even' && (
              <div className="flex items-center justify-between font-semibold text-blue-700">
                <span>{t('cm.components_SplitFolioDialog.aktarilacak_toplam')}</span>
                <span>{fmtTL(evenPerSplit * (evenSplits - 1))} TL</span>
              </div>
            )}
            {mode === 'custom' && (
              <div className="flex items-center justify-between font-semibold text-blue-700">
                <span>{t('cm.components_SplitFolioDialog.aktarilacak_toplam_03d73')}</span>
                <span>{fmtTL(customTotal)} TL</span>
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
            {t('cm.components_SplitFolioDialog.iptal')}
          </Button>
        </div>

        <div className="bg-yellow-50 border border-yellow-200 rounded p-3">
          <p className="text-xs text-yellow-700">
            <strong>{t('cm.components_SplitFolioDialog.uyari')}</strong> {t('cm.components_SplitFolioDialog.bu_islem_geri_alinamaz_esit_ve_ozel_modl')}
          </p>
        </div>
      </CardContent>
    </Card>
  );
};

export default SplitFolioDialog;
