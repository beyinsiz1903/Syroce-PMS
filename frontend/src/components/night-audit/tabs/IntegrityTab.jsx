import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { TabsContent } from '@/components/ui/tabs';
import { Moon, Play, Clock, CheckCircle2, XCircle, AlertTriangle, RefreshCw, Calendar, FileText, ChevronDown, ChevronUp, DollarSign, Users, Building2, BarChart3, Eye, Loader2, Shield, Info, Timer, Settings2, Zap, RotateCcw, TrendingUp, CreditCard, ShieldCheck, Scale, Receipt, PieChart, ArrowUpDown, Banknote, AlertOctagon, Search } from 'lucide-react';

export default function IntegrityTab(props) {
  const { IntegrityBadge, StatCard, detail, integrityCheck } = props;
  return (
    <TabsContent value="integrity" className="space-y-4 mt-4">
      {integrityCheck ? (
        <>
          {/* Summary */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard
              icon={ShieldCheck}
              label="Toplam Kontrol"
              value={integrityCheck.summary?.total || 0}
              color="text-indigo-600"
            />
            <StatCard
              icon={CheckCircle2}
              label="Gecen"
              value={integrityCheck.summary?.passed || 0}
              color="text-emerald-600"
            />
            <StatCard
              icon={AlertTriangle}
              label="Uyari"
              value={integrityCheck.summary?.warnings || 0}
              color="text-amber-600"
            />
            <StatCard
              icon={XCircle}
              label="Başarısız"
              value={integrityCheck.summary?.failures || 0}
              color="text-red-600"
            />
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
                {(integrityCheck.checks || []).map((check, i) => (
                  <div
                    key={i}
                    data-testid={`integrity-check-${check.check}`}
                    className={`flex items-center justify-between p-3 rounded-lg border ${
                      check.status === "pass" ? "bg-emerald-50/50 border-emerald-100"
                        : check.status === "warning" ? "bg-amber-50/50 border-amber-100"
                        : "bg-red-50/50 border-red-100"
                    }`}
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
                    <IntegrityBadge status={check.status} />
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </>
      ) : (
        <div className="flex items-center justify-center py-16 text-gray-400 text-sm">
          <Loader2 className="w-5 h-5 mr-2 animate-spin" /> Bütünlük kontrolu yükleniyor...
        </div>
      )}
    </TabsContent>
  );
}
