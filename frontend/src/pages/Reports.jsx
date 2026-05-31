import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import NightAuditModule from "@/components/NightAuditModule";
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { 
  FileText, 
  Download, 
  Calendar,
  TrendingUp,
  DollarSign,
  Building,
  FileSpreadsheet,
  Plus,
  X,
  Trash2
} from 'lucide-react';
import { normalizeFeatures } from '@/utils/featureFlags';
import { useTranslation } from 'react-i18next';

const Reports = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const [selectedReports, setSelectedReports] = useState([]);
  const [showSelector, setShowSelector] = useState(false);
  const [activeSection, setActiveSection] = useState('excel'); // 'excel' | 'night_audit'

  const plan =
    tenant?.subscription_plan ||
    tenant?.plan ||
    tenant?.subscription_tier ||
    'core_small_hotel';

  const isLite = plan === 'pms_lite';
  const features = normalizeFeatures(tenant?.features || {});
  const isReportsLite = !!features.reports_lite || isLite;

  // Per-tenant section entitlement: tenant.modules['reports.<key>'] === false
  // hides that section. Missing/undefined = visible (backward compatible).
  const tenantModulesMap = tenant?.modules || {};
  const isReportSectionEnabled = (sectionKey) => tenantModulesMap[`reports.${sectionKey}`] !== false;
  const showExcelSection = isReportSectionEnabled('excel');
  const showNightAuditSection = isReportSectionEnabled('night_audit');

  // Snap activeSection to a visible one if the current pick was disabled.
  useEffect(() => {
    if (activeSection === 'excel' && !showExcelSection && showNightAuditSection) {
      setActiveSection('night_audit');
    } else if (activeSection === 'night_audit' && !showNightAuditSection && showExcelSection) {
      setActiveSection('excel');
    }
  }, [activeSection, showExcelSection, showNightAuditSection]);

  // All available reports
  const availableReports = [
    // FINANS RAPORLARI
    {
      id: 'daily-flash',
      name: t('reports.dailyFlashReport'),
      category: 'financial',
      icon: DollarSign,
      endpoint: '/reports/daily-flash/excel',
      needsDateRange: false,
      description: t('reports.dailyFlashReport')
    },
    {
      id: 'company-aging',
      name: t('reports.companyAgingReport'),
      category: 'financial',
      icon: DollarSign,
      endpoint: '/reports/company-aging/excel',
      needsDateRange: false,
      description: t('reports.companyAgingReport')
    },
    {
      id: 'revenue-detail',
      name: t('reports.revenueDetailReport'),
      category: 'financial',
      icon: DollarSign,
      endpoint: '/reports/revenue-detail/excel',
      needsDateRange: true,
      description: t('reports.revenueDetailReport')
    },
    {
      id: 'forecast-detail',
      name: t('reports.forecastDetailReport'),
      category: 'financial',
      icon: Calendar,
      endpoint: '/reports/forecast-detail/excel',
      needsDateRange: true,
      description: t('reports.forecastDetailReport')
    },

    // OPERASYON RAPORLARI
    {
      id: 'housekeeping-efficiency',
      name: t('reports.housekeepingEfficiency'),
      category: 'operational',
      icon: Building,
      endpoint: '/reports/housekeeping-efficiency/excel',
      needsDateRange: true,
      description: t('reports.housekeepingEfficiency')
    },
    {
      id: 'operations-daily-summary',
      name: t('reports.operationsDailySummary'),
      category: 'operational',
      icon: Calendar,
      endpoint: '/reports/operations-daily-summary/excel',
      needsDateRange: false,
      description: t('reports.operationsDailySummary')
    },

    // PAZAR / MARKET RAPORLARI
    {
      id: 'market-segment',
      name: t('reports.marketSegmentAnalysis'),
      category: 'market',
      icon: TrendingUp,
      endpoint: '/reports/market-segment/excel',
      needsDateRange: true,
      description: t('reports.marketSegmentAnalysis')
    },
    {
      id: 'channel-distribution',
      name: t('reports.channelDistribution'),
      category: 'market',
      icon: TrendingUp,
      endpoint: '/reports/channel-distribution/excel',
      needsDateRange: true,
      description: t('reports.channelDistribution')
    }
  ];

  // Per-tenant report-list entitlement: tenant.modules['reports.<id>'] === false
  // hides that report from the selector. Missing/undefined = visible (backward compatible).
  const visibleReports = availableReports.filter(
    (r) => tenantModulesMap[`reports.${r.id}`] !== false
  );

  const addReport = (reportId) => {
    const report = availableReports.find(r => r.id === reportId);
    if (report && !selectedReports.find(r => r.id === reportId)) {
      setSelectedReports([...selectedReports, {
        ...report,
        startDate: new Date(new Date().setMonth(new Date().getMonth() - 1)).toISOString().split('T')[0],
        endDate: new Date().toISOString().split('T')[0]
      }]);
    }
    setShowSelector(false);
  };

  const removeReport = (reportId) => {
    setSelectedReports(selectedReports.filter(r => r.id !== reportId));
  };

  const updateReportDate = (reportId, field, value) => {
    setSelectedReports(selectedReports.map(r => 
      r.id === reportId ? { ...r, [field]: value } : r
    ));
  };

  const handleDownloadReport = async (report) => {
    setLoading(true);
    try {
      let url = report.endpoint;
      
      // Add date parameters if needed
      if (report.needsDateRange) {
        url += `?start_date=${report.startDate}&end_date=${report.endDate}`;
      }
      
      const response = await axios.get(url, {
        responseType: 'blob'
      });
      
      // Create download link
      const blob = new Blob([response.data], { 
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' 
      });
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      
      // Get filename from content-disposition header or use default
      const contentDisposition = response.headers['content-disposition'];
      let filename = `${report.name.replace(/\s+/g, '_')}.xlsx`;
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
        if (filenameMatch && filenameMatch[1]) {
          filename = filenameMatch[1].replace(/['"]/g, '');
        }
      }
      
      link.download = filename;
      document.body.appendChild(link);
      link.click();

  if (isReportsLite) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="reports">
        <div className="p-6 max-w-4xl mx-auto space-y-6">
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">Raporlar (PMS Lite)</h1>
            <p className="mt-1 text-sm text-gray-600">
              Son 7 ve 30 güne ait doluluk ve ciro özetlerini görebilirsiniz.
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Doluluk (7 Gün)</CardTitle>
                <CardDescription>Son 7 gün ortalama doluluk oranı</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold text-gray-900">%--</div>
                <p className="mt-1 text-xs text-gray-500">Bu ekranda özet metrikler gösterilir.</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Ciro (7 Gün)</CardTitle>
                <CardDescription>Son 7 gün toplam oda geliri</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold text-gray-900">₺--</div>
                <p className="mt-1 text-xs text-gray-500">Detaylı kırılımlar ileride eklenebilir.</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Doluluk (30 Gün)</CardTitle>
                <CardDescription>Son 30 gün ortalama doluluk oranı</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold text-gray-900">%--</div>
                <p className="mt-1 text-xs text-gray-500">Bu alanda daha fazla detay daha sonra eklenebilir.</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Ciro (30 Gün)</CardTitle>
                <CardDescription>Son 30 gün toplam oda geliri</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold text-gray-900">₺--</div>
                <p className="mt-1 text-xs text-gray-500">Muhasebe / AR raporları burada gösterilmiyor.</p>
              </CardContent>
            </Card>
          </div>
        </div>
      </Layout>
    );
  }

      document.body.removeChild(link);
      window.URL.revokeObjectURL(downloadUrl);
      
      toast.success(`${report.name} {t('reports.downloadSuccess')}!`);
    } catch (error) {
      console.error('Failed to download report:', error);
      toast.error(t('reports.downloadFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadAll = async () => {
    for (const report of selectedReports) {
      await handleDownloadReport(report);
      // Small delay between downloads
      await new Promise(resolve => setTimeout(resolve, 500));
    }
  };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="reports">
      <div className="p-6 max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2 flex items-center gap-3">
            <FileSpreadsheet className="w-8 h-8 text-green-600" />
            Excel Reports
          </h1>
          <p className="text-gray-600">{t('reports.addReportDesc')}</p>
        </div>

        {/* Section Tabs */}
        <div className="mb-4 flex gap-2 border-b pb-2 text-sm">
          {showExcelSection && (
            <button
              type="button"
              onClick={() => setActiveSection('excel')}
              className={`px-3 py-1 rounded-t-md border-b-2 text-xs md:text-sm ${
                activeSection === 'excel'
                  ? 'border-blue-600 text-blue-700 font-semibold'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              Excel Raporları
            </button>
          )}
          {showNightAuditSection && (
            <button
              type="button"
              onClick={() => setActiveSection('night_audit')}
              className={`px-3 py-1 rounded-t-md border-b-2 text-xs md:text-sm ${
                activeSection === 'night_audit'
                  ? 'border-blue-600 text-blue-700 font-semibold'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              Night Audit
            </button>
          )}
          <button
            type="button"
            onClick={() => navigate('/reports/builder')}
            className="px-3 py-1 rounded-t-md border-b-2 text-xs md:text-sm border-transparent text-gray-500 hover:text-gray-700 flex items-center gap-1"
            data-testid="report-builder-tab"
          >
            <Plus className="w-3 h-3" />
            Rapor Oluşturucu
          </button>
        </div>

        {/* Excel Reports Section */}
        {showExcelSection && activeSection === 'excel' && (
          <div>
            {/* Add Report Button */}
            <div className="mb-6">
              {!showSelector ? (
                <Button 
                  onClick={() => setShowSelector(true)}
                  className="bg-blue-600 hover:bg-blue-700"
                >
                  <Plus className="w-4 h-4 mr-2" />
                  Add Report to Download
                </Button>
              ) : (
                <Card className="border-2 border-blue-500">
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-lg">Select Report</CardTitle>
                      <Button 
                        variant="ghost" 
                        size="sm"
                        onClick={() => setShowSelector(false)}
                      >
                        <X className="w-4 h-4" />
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <Select onValueChange={addReport}>
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="Choose a report..." />
                      </SelectTrigger>
                      <SelectContent>
                        {visibleReports
                          .filter(r => !selectedReports.find(sr => sr.id === r.id))
                          .map(report => (
                            <SelectItem key={report.id} value={report.id}>
                              <div className="flex items-center gap-2">
                                <report.icon className="w-4 h-4 text-gray-500" />
                                <div>
                                  <div className="font-medium">{report.name}</div>
                                  <div className="text-xs text-gray-500">{report.description}</div>
                                </div>
                              </div>
                            </SelectItem>
                          ))}
                      </SelectContent>
                    </Select>
                  </CardContent>
                </Card>
              )}
            </div>

            {/* {t('reports.selectedReports')} */}
            {selectedReports.length > 0 && (
              <div>
                <div className="mb-4 flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-gray-900">
                    {t('reports.selectedReports')} ({selectedReports.length})
                  </h2>
                  <Button 
                    onClick={handleDownloadAll}
                    disabled={loading}
                    className="bg-green-600 hover:bg-green-700"
                  >
                    <Download className="w-4 h-4 mr-2" />
                    {t('reports.downloadAll')}
                  </Button>
                </div>

                <div className="space-y-4">
                  {selectedReports.map(report => (
                    <Card key={report.id} className="border-l-4 border-l-green-500">
                      <CardContent className="pt-6">
                        <div className="flex items-start justify-between gap-4">
                          {/* Report Info */}
                          <div className="flex items-start gap-3 flex-1">
                            <div className="mt-1">
                              <report.icon className="w-5 h-5 text-gray-600" />
                            </div>
                            <div className="flex-1">
                              <h3 className="font-semibold text-gray-900 mb-1">
                                {report.name}
                              </h3>
                              <p className="text-sm text-gray-500 mb-3">
                                {report.description}
                              </p>

                              {/* Date Range Inputs */}
                              {report.needsDateRange && (
                                <div className="grid grid-cols-2 gap-3 max-w-md">
                                  <div>
                                    <Label className="text-xs text-gray-600">Start Date</Label>
                                    <Input
                                      type="date"
                                      value={report.startDate}
                                      onChange={(e) => updateReportDate(report.id, 'startDate', e.target.value)}
                                      className="mt-1 h-9"
                                    />
                                  </div>
                                  <div>
                                    <Label className="text-xs text-gray-600">End Date</Label>
                                    <Input
                                      type="date"
                                      value={report.endDate}
                                      onChange={(e) => updateReportDate(report.id, 'endDate', e.target.value)}
                                      className="mt-1 h-9"
                                    />
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>

                          {/* Action Buttons */}
                          <div className="flex gap-2">
                            <Button
                              size="sm"
                              onClick={() => handleDownloadReport(report)}
                              disabled={loading}
                              className="bg-green-600 hover:bg-green-700 text-white"
                            >
                              <Download className="w-4 h-4 mr-1" />
                              Download
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => removeReport(report.id)}
                              className="text-red-600 hover:text-red-700 hover:bg-red-50"
                            >
                              <Trash2 className="w-4 h-4" />
                            </Button>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            )}

            {/* Empty State */}
            {selectedReports.length === 0 && !showSelector && (
              <Card className="border-dashed border-2">
                <CardContent className="py-12">
                  <div className="text-center">
                    <FileSpreadsheet className="w-16 h-16 text-gray-400 mx-auto mb-4" />
                    <h3 className="text-lg font-semibold text-gray-900 mb-2">
                      No Reports Selected
                    </h3>
                    <p className="text-gray-500 mb-4">
                      Click the &quot;Add Report to Download&quot; button to start selecting reports
                    </p>
                    <Button 
                      onClick={() => setShowSelector(true)}
                      variant="outline"
                    >
                      <Plus className="w-4 h-4 mr-2" />
                      Add Your First Report
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Official Guest List Shortcut */}
            <Card className="mt-6 border-green-200 bg-green-50/40">
              <CardContent className="pt-6 flex items-start justify-between gap-4">
                <div className="flex gap-3 flex-1">
                  <FileText className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <h4 className="font-semibold text-gray-900 mb-1">Resmi Müşteri Listesi (Maliye Raporu)</h4>
                    <p className="text-sm text-gray-600 mb-1">
                      Maliye veya resmi denetim geldiğinde, seçtiğiniz gün için otelde konaklayan tüm
                      misafirlerin resmi listesini tek ekrandan alabilirsiniz. Liste, TCKN/pasaport,
                      oda, giriş-çıkış ve toplam tutarı içerir.
                    </p>
                    <p className="text-xs text-gray-500">
                      İpucu: İhtiyaç anında hızlı erişim için bu sayfayı sık kullananlara ekleyin.
                    </p>
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  className="text-xs bg-white"
                  onClick={() => navigate('/reports/official-guest-list')}
                >
                  Resmi Müşteri Listesine Git
                </Button>
              </CardContent>
            </Card>

            {/* Info Card */}
            <Card className="mt-6 bg-blue-50 border-blue-200">
              <CardContent className="pt-6 flex items-start justify-between gap-4">
                <div className="flex gap-3 flex-1">
                  <FileText className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <h4 className="font-semibold text-gray-900 mb-1">Export Tips</h4>
                    <ul className="text-sm text-gray-600 space-y-1">
                      <li>• Select multiple reports and download them all at once</li>
                      <li>• Date ranges are automatically set to last 30 days (adjustable)</li>
                      <li>• Excel files include formatted tables with headers and totals</li>
                      <li>• All financial amounts are properly formatted with currency symbols</li>
                    </ul>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-2">
                  <span className="text-xs text-gray-500">Corporate performance</span>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => navigate('/reports/corporate-contracts')}
                    className="text-xs"
                  >
                    Corporate Contracts Dashboard
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => navigate('/reports/corporate-contract-approvals')}
                    className="text-xs"
                  >
                    Sözleşme Onayları
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Night Audit Section */}
        {activeSection === 'night_audit' && (
        <div className="mt-10">
          <h2 className="text-xl font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <Calendar className="w-5 h-5 text-blue-600" />
            Night Audit
          </h2>
          <p className="text-sm text-gray-600 mb-4">
            Gece denetimi işlemlerinizi yönetin: oda gelirlerini post edin, no-show rezervasyonları işleyin ve gün sonu kapanışını tamamlayın.
          </p>
          <Card className="border border-blue-100 bg-blue-50/40">
            <CardContent className="p-4">
              <NightAuditModule />
            </CardContent>
          </Card>
        </div>
        )}

      </div>
    </Layout>
  );
};

export default Reports;
