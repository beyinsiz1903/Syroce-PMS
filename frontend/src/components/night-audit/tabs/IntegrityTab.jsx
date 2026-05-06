import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { TabsContent } from '@/components/ui/tabs';
import { CheckCircle2, XCircle, AlertTriangle, Loader2, Shield, ShieldCheck, ChevronRight } from 'lucide-react';
import IntegrityItemsModal from '../IntegrityItemsModal';

async function navigateToItem(it, navigate) {
  // Folyo açma: önce folio_id, yoksa booking_id üzerinden açık folio bul
  if (it.action === 'open_folio' || it.folio_id) {
    if (it.folio_id) {
      navigate(`/folio-detail/${it.folio_id}`);
      return;
    }
    if (it.booking_id) {
      try {
        const { data } = await axios.get(`/folio/booking/${it.booking_id}`);
        const list = Array.isArray(data) ? data : (data?.folios || []);
        const open = list.find((f) => f.status === 'open') || list[0];
        const folioId = open?.id || open?.folio_id;
        if (folioId) {
          navigate(`/folio-detail/${folioId}`);
          return;
        }
        toast.error('Bu rezervasyon için açık folyo bulunamadı');
      } catch (e) {
        toast.error('Folyo açılamadı: ' + (e.response?.data?.detail || e.message));
      }
      return;
    }
  }
  // Rezervasyon açma
  if (it.booking_id) {
    navigate(`/pms?edit=${it.booking_id}#bookings`);
    return;
  }
  toast.error('Bu kayıt için açılacak ekran yok');
}

export default function IntegrityTab(props) {
  const { IntegrityBadge, StatCard, integrityCheck } = props;
  const navigate = useNavigate();
  const [modalCheck, setModalCheck] = useState(null);

  const handleRowClick = async (check) => {
    const items = check.items || [];
    if (items.length === 0) return;
    if (items.length === 1) {
      await navigateToItem(items[0], navigate);
      return;
    }
    setModalCheck(check);
  };

  const handlePickItem = async (it) => {
    setModalCheck(null);
    await navigateToItem(it, navigate);
  };

  return (
    <TabsContent value="integrity" className="space-y-4 mt-4">
      {integrityCheck ? (
        <>
          {/* Summary */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard icon={ShieldCheck} label="Toplam Kontrol" value={integrityCheck.summary?.total || 0} color="text-indigo-600" />
            <StatCard icon={CheckCircle2} label="Gecen" value={integrityCheck.summary?.passed || 0} color="text-emerald-600" />
            <StatCard icon={AlertTriangle} label="Uyarı" value={integrityCheck.summary?.warnings || 0} color="text-amber-600" />
            <StatCard icon={XCircle} label="Başarısız" value={integrityCheck.summary?.failures || 0} color="text-red-600" />
          </div>

          {/* Overall Status */}
          <div className={`p-4 rounded-xl border-2 ${
            integrityCheck.summary?.overall_status === "pass" ? "border-emerald-200 bg-emerald-50"
              : integrityCheck.summary?.overall_status === "warning" ? "border-amber-200 bg-amber-50"
              : "border-red-200 bg-red-50"
          }`}>
            <div className="flex items-center gap-3">
              {integrityCheck.summary?.overall_status === "pass" ? (
                <ShieldCheck className="w-6 h-6 text-emerald-600" />
              ) : integrityCheck.summary?.overall_status === "warning" ? (
                <AlertTriangle className="w-6 h-6 text-amber-600" />
              ) : (
                <XCircle className="w-6 h-6 text-red-600" />
              )}
              <div>
                <p className="text-sm font-bold text-gray-900">
                  {integrityCheck.summary?.overall_status === "pass" ? "Finansal Bütünlük Kontrolu Gecti"
                    : integrityCheck.summary?.overall_status === "warning" ? "Uyarilarla Gecti"
                    : "Bütünlük Sorunlari Tespit Edildi"}
                </p>
                <p className="text-xs text-gray-600">
                  {integrityCheck.business_date} tarihli kontrol sonuclari
                </p>
              </div>
            </div>
          </div>

          {/* Individual Checks */}
          <Card data-testid="integrity-checks-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Shield className="w-4 h-4 text-indigo-500" />
                Kontrol Detaylari
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {(integrityCheck.checks || []).map((check, i) => {
                  const items = check.items || [];
                  const clickable = items.length > 0;
                  const Wrap = clickable ? 'button' : 'div';
                  const wrapProps = clickable
                    ? {
                        type: 'button',
                        onClick: () => handleRowClick(check),
                        title: items.length === 1
                          ? 'Tıklayın — kayda gidin'
                          : `Tıklayın — ${items.length} kayıttan birini seçin`,
                      }
                    : {};
                  return (
                    <Wrap
                      key={i}
                      data-testid={`integrity-check-${check.check}`}
                      {...wrapProps}
                      className={`w-full text-left flex items-center justify-between p-3 rounded-lg border transition-colors ${
                        check.status === "pass" ? "bg-emerald-50/50 border-emerald-100"
                          : check.status === "warning" ? "bg-amber-50/50 border-amber-100"
                          : "bg-red-50/50 border-red-100"
                      } ${clickable ? 'hover:bg-white hover:shadow-sm cursor-pointer' : ''}`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        {check.status === "pass" ? (
                          <CheckCircle2 className="w-5 h-5 text-emerald-500 flex-shrink-0" />
                        ) : check.status === "warning" ? (
                          <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0" />
                        ) : (
                          <XCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
                        )}
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-gray-800">{check.label}</p>
                          <p className="text-xs text-gray-500 mt-0.5">{check.detail}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <IntegrityBadge status={check.status} />
                        {clickable && <ChevronRight className="w-4 h-4 text-gray-400" />}
                      </div>
                    </Wrap>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          <IntegrityItemsModal
            open={!!modalCheck}
            onOpenChange={(open) => !open && setModalCheck(null)}
            check={modalCheck}
            onPick={handlePickItem}
          />
        </>
      ) : (
        <div className="flex items-center justify-center py-16 text-gray-400 text-sm">
          <Loader2 className="w-5 h-5 mr-2 animate-spin" /> Bütünlük kontrolu yükleniyor...
        </div>
      )}
    </TabsContent>
  );
}
