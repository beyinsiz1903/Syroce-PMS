import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { Moon, PlayCircle, CheckCircle, AlertTriangle, Clock, TrendingUp, Calendar } from 'lucide-react';

import { alertDialog } from '@/lib/dialogs';
import { useTranslation } from 'react-i18next';
// Helper to get yesterday in YYYY-MM-DD format
const getDefaultAuditDate = () => {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return d.toISOString().split('T')[0];
};

const NightAuditModule = () => {
  const { t } = useTranslation();
  const [auditDate, setAuditDate] = useState(getDefaultAuditDate);
  const [status, setStatus] = useState(null);
  const [report, setReport] = useState(null);
  const [auditId, setAuditId] = useState(null);

  const [startResult, setStartResult] = useState(null);
  const [autoPostingResult, setAutoPostingResult] = useState(null);
  const [noShowResult, setNoShowResult] = useState(null);
  const [endOfDayResult, setEndOfDayResult] = useState(null);

  const [chargeNoShowFee, setChargeNoShowFee] = useState(true);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [runningStep, setRunningStep] = useState(null); // 'start' | 'auto' | 'noShow' | 'end'

  // Fetch status + report when auditDate changes
  useEffect(() => {
    fetchStatusAndReport();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [auditDate]);

  const fetchStatusAndReport = async () => {
    setLoadingStatus(true);
    try {
      // Status
      const statusRes = await axios.get('/night-audit/status', {
        params: { audit_date: auditDate },
      });
      setStatus(statusRes.data);
      if (statusRes.data && statusRes.data.id) {
        setAuditId(statusRes.data.id);
      }

      // Report (may not exist yet)
      try {
        const reportRes = await axios.get('/night-audit/audit-report', {
          params: { audit_date: auditDate },
        });
        setReport(reportRes.data);
      } catch (err) {
        // 404 means henüz audit yok; bu durumda raporu temizleyelim
        setReport(null);
      }
    } catch (err) {
      console.error('Error fetching night audit status/report', err);
    } finally {
      setLoadingStatus(false);
    }
  };

  const handleStartAudit = async () => {
    setRunningStep('start');
    try {
      const res = await axios.post('/night-audit/start-audit', null, {
        params: { audit_date: auditDate },
      });
      setStartResult(res.data);
      if (res.data.audit_id) {
        setAuditId(res.data.audit_id);
      }
      await fetchStatusAndReport();
    } catch (err) {
      console.error('Error starting night audit', err);
      await alertDialog({ message: 'Night audit başlatılamadı. Detay için konsolu kontrol edin.' });
    } finally {
      setRunningStep(null);
    }
  };

  const handleAutomaticPosting = async () => {
    setRunningStep('auto');
    try {
      const res = await axios.post('/night-audit/automatic-posting', null, {
        params: { audit_date: auditDate },
      });
      setAutoPostingResult(res.data);
      await fetchStatusAndReport();
    } catch (err) {
      console.error('Error in automatic posting', err);
      await alertDialog({ message: 'Oda gelirleri post edilirken hata oluştu.' });
    } finally {
      setRunningStep(null);
    }
  };

  const handleNoShowHandling = async () => {
    setRunningStep('noShow');
    try {
      const res = await axios.post('/night-audit/no-show-handling', null, {
        params: {
          audit_date: auditDate,
          charge_no_show_fee: chargeNoShowFee,
        },
      });
      setNoShowResult(res.data);
      await fetchStatusAndReport();
    } catch (err) {
      console.error('Error processing no-shows', err);
      await alertDialog({ message: 'No-show işlemleri sırasında hata oluştu.' });
    } finally {
      setRunningStep(null);
    }
  };

  const handleEndOfDay = async () => {
    if (!auditId) {
      await alertDialog({ message: 'Önce audit başlatılmalı (Audit ID bulunamadı).' });
      return;
    }
    setRunningStep('end');
    try {
      const res = await axios.post('/night-audit/end-of-day', null, {
        params: { audit_id: auditId },
      });
      setEndOfDayResult(res.data);
      await fetchStatusAndReport();
    } catch (err) {
      console.error('Error completing end-of-day', err);
      await alertDialog({ message: 'Gün sonu kapanışında hata oluştu.' });
    } finally {
      setRunningStep(null);
    }
  };

  const disabledAll = loadingStatus || runningStep !== null;

  const currentAudit = report?.audit || null;
  const bookingsByStatus = report?.bookings_by_status || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Moon className="w-7 h-7 text-blue-600" />
            Night Audit
          </h1>
          <p className="text-gray-600 text-sm">
            {t('cm.components_NightAuditModule.belirli_bir_is_gunu_icin_no_show_oda_gel')}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-sm text-gray-600 flex items-center gap-2">
            <Calendar className="w-4 h-4" />
            <span>Audit Date</span>
          </div>
          <Input
            type="date"
            className="w-40 h-9"
            value={auditDate}
            onChange={(e) => setAuditDate(e.target.value)}
            disabled={disabledAll}
          />
        </div>
      </div>

      {/* Status cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <div className="text-xs text-gray-500 mb-1">{t('cm.components_NightAuditModule.durum')}</div>
              <div className="flex items-center gap-2">
                <Badge
                  className={
                    status?.status === 'completed'
                      ? 'bg-green-500'
                      : status?.status === 'in_progress'
                      ? 'bg-yellow-500'
                      : 'bg-gray-400'
                  }
                >
                  {status?.status || 'not_started'}
                </Badge>
              </div>
            </div>
            {status?.status === 'completed' ? (
              <CheckCircle className="w-7 h-7 text-green-600" />
            ) : (
              <AlertTriangle className="w-7 h-7 text-yellow-500" />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <div className="text-xs text-gray-500 mb-1">{t('cm.components_NightAuditModule.toplam_odalar')}</div>
              <div className="text-xl font-semibold">
                {currentAudit?.total_rooms ?? '-'}
              </div>
            </div>
            <TrendingUp className="w-7 h-7 text-blue-600" />
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <div className="text-xs text-gray-500 mb-1">Doluluk (%)</div>
              <div className="text-xl font-semibold">
                {currentAudit && currentAudit.total_rooms > 0
                  ? `${(
                      (currentAudit.occupied_rooms / currentAudit.total_rooms) * 100
                    ).toFixed(1)}%`
                  : '-'}
              </div>
            </div>
            <Clock className="w-7 h-7 text-indigo-600" />
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <div className="text-xs text-gray-500 mb-1">{t('cm.components_NightAuditModule.toplam_gelir')}</div>
              <div className="text-xl font-semibold">
                {currentAudit?.total_revenue != null
                  ? `€${currentAudit.total_revenue.toFixed(2)}`
                  : '-'}
              </div>
            </div>
            <TrendingUp className="w-7 h-7 text-green-600" />
          </CardContent>
        </Card>
      </div>

      {/* Steps */}
      <Card>
        <CardHeader>
          <CardTitle>{t('cm.components_NightAuditModule.night_audit_adimlari')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Step 1 */}
          <div className="flex flex-col md:flex-row md:items-center gap-4 p-3 rounded-lg border border-gray-100 bg-white">
            <div className="flex-1">
              <div className="font-semibold">{t('cm.components_NightAuditModule.1_audit_baslat')}</div>
              <div className="text-xs text-gray-600">
                {t('cm.components_NightAuditModule.bu_tarih_icin_night_audit_kaydi_olusturu')}
              </div>
              {startResult && (
                <div className="mt-2 text-xs text-gray-600">
                  <span className="font-medium">Statistikler:</span>{' '}
                  {startResult.statistics && (
                    <>
                      Odalar: {startResult.statistics.total_rooms} | Doluluk: {startResult.statistics.occupancy_pct}{t('cm.components_NightAuditModule.toplam_gelir_bd4d6')}{startResult.statistics.total_revenue}
                    </>
                  )}
                </div>
              )}
            </div>
            <Button
              variant="outline"
              onClick={handleStartAudit}
              disabled={disabledAll}
            >
              <PlayCircle className="w-4 h-4 mr-2" />
              {runningStep === 'start' ? 'Çalışıyor...' : 'Audit Başlat'}
            </Button>
          </div>

          {/* Step 2 */}
          <div className="flex flex-col md:flex-row md:items-center gap-4 p-3 rounded-lg border border-gray-100 bg-white">
            <div className="flex-1">
              <div className="font-semibold">{t('cm.components_NightAuditModule.2_oda_gelirlerini_post_et')}</div>
              <div className="text-xs text-gray-600">
                {t('cm.components_NightAuditModule.check_in_durumundaki_tum_odalar_icin_gun')}
              </div>
              {autoPostingResult && (
                <div className="mt-2 text-xs text-gray-600">
                  <span className="font-medium">{t('cm.components_NightAuditModule.sonuc')}</span>{' '}
                  {autoPostingResult.posted_count} rezervasyon, toplam €
                  {autoPostingResult.total_amount_posted}
                </div>
              )}
            </div>
            <Button
              variant="outline"
              onClick={handleAutomaticPosting}
              disabled={disabledAll}
            >
              <PlayCircle className="w-4 h-4 mr-2" />
              {runningStep === 'auto' ? 'Çalışıyor...' : 'Oda Gelirlerini Post Et'}
            </Button>
          </div>

          {/* Step 3 */}
          <div className="flex flex-col md:flex-row md:items-center gap-4 p-3 rounded-lg border border-gray-100 bg-white">
            <div className="flex-1">
              <div className="font-semibold">{t('cm.components_NightAuditModule.3_no_show_isleme')}</div>
              <div className="text-xs text-gray-600">
                {t('cm.components_NightAuditModule.check_in_yapmamis_confirmed_guaranteed_r')}
              </div>
              <label className="mt-2 inline-flex items-center gap-2 text-xs text-gray-700">
                <input
                  type="checkbox"
                  checked={chargeNoShowFee}
                  onChange={(e) => setChargeNoShowFee(e.target.checked)}
                  disabled={disabledAll}
                />
                {t('cm.components_NightAuditModule.no_show_ucreti_uygula')}
              </label>
              {noShowResult && (
                <div className="mt-2 text-xs text-gray-600">
                  <span className="font-medium">{t('cm.components_NightAuditModule.sonuc_5e347')}</span>{' '}
                  {noShowResult.no_shows_processed} rezervasyon, toplam €
                  {noShowResult.total_no_show_charges}
                </div>
              )}
            </div>
            <Button
              variant="outline"
              onClick={handleNoShowHandling}
              disabled={disabledAll}
            >
              <PlayCircle className="w-4 h-4 mr-2" />
              {runningStep === 'noShow' ? 'Çalışıyor...' : 'No-Show İşle'}
            </Button>
          </div>

          {/* Step 4 */}
          <div className="flex flex-col md:flex-row md:items-center gap-4 p-3 rounded-lg border border-gray-100 bg-white">
            <div className="flex-1">
              <div className="font-semibold">{t('cm.components_NightAuditModule.4_gun_sonu_kapanisi')}</div>
              <div className="text-xs text-gray-600">
                {t('cm.components_NightAuditModule.night_audit_surecini_tamamlar_ozet_istat')}
              </div>
              {endOfDayResult && (
                <div className="mt-2 text-xs text-gray-600">
                  <span className="font-medium">{t('cm.components_NightAuditModule.ozet')}</span>{' '}
                  {endOfDayResult.summary && (
                    <>
                      {t('cm.components_NightAuditModule.toplam_gelir_e49f2')}{endOfDayResult.summary.total_revenue} | No
                      Show: {endOfDayResult.summary.no_shows} {t('cm.components_NightAuditModule.dolu_odalar')}{' '}
                      {endOfDayResult.summary.occupied_rooms}
                    </>
                  )}
                </div>
              )}
            </div>
            <Button
              variant="outline"
              onClick={handleEndOfDay}
              disabled={disabledAll}
            >
              <PlayCircle className="w-4 h-4 mr-2" />
              {runningStep === 'end' ? 'Çalışıyor...' : 'Gün Sonunu Kapat'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Bookings by status */}
      {bookingsByStatus && bookingsByStatus.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>{t('cm.components_NightAuditModule.duruma_gore_rezervasyon_ozeti')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-gray-600">
                    <th className="py-2 pr-4">{t('cm.components_NightAuditModule.durum_074f4')}</th>
                    <th className="py-2 pr-4 text-right">Adet</th>
                    <th className="py-2 pr-4 text-right">{t('cm.components_NightAuditModule.toplam_gelir_81fef')}</th>
                  </tr>
                </thead>
                <tbody>
                  {bookingsByStatus.map((row, idx) => (
                    <tr key={idx} className="border-b last:border-0">
                      <td className="py-2 pr-4 capitalize">{row._id}</td>
                      <td className="py-2 pr-4 text-right">{row.count}</td>
                      <td className="py-2 pr-4 text-right">
                        €{row.revenue?.toFixed ? row.revenue.toFixed(2) : row.revenue}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default NightAuditModule;
