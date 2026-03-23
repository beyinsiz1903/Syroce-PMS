import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { 
  FileText, 
  TrendingUp, 
  TrendingDown, 
  Calendar, 
  DollarSign,
  Clock,
  CheckCircle,
  AlertTriangle,
  ChevronLeft,
  ChevronRight
} from 'lucide-react';

const MaintenanceReports = () => {
  const [reportType, setReportType] = useState('weekly'); // weekly or monthly
  const [weeklyReport, setWeeklyReport] = useState(null);
  const [monthlyReport, setMonthlyReport] = useState(null);
  const [currentMonth, setCurrentMonth] = useState(new Date().toISOString().slice(0, 7));
  const [weekOffset, setWeekOffset] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadReports();
  }, [reportType, currentMonth, weekOffset]);

  const loadReports = async () => {
    setLoading(true);
    try {
      if (reportType === 'weekly') {
        const response = await axios.get(`/maintenance/reports/weekly?week_offset=${weekOffset}`);
        setWeeklyReport(response.data);
      } else {
        const response = await axios.get(`/maintenance/reports/monthly?month=${currentMonth}`);
        setMonthlyReport(response.data);
      }
    } catch (error) {
      console.error('Failed to load reports:', error);
    } finally {
      setLoading(false);
    }
  };

  const changeMonth = (direction) => {
    const [year, month] = currentMonth.split('-').map(Number);
    let newMonth = month + direction;
    let newYear = year;

    if (newMonth > 12) {
      newMonth = 1;
      newYear++;
    } else if (newMonth < 1) {
      newMonth = 12;
      newYear--;
    }

    setCurrentMonth(`${newYear}-${newMonth.toString().padStart(2, '0')}`);
  };

  const getMonthName = (monthStr) => {
    const months = [
      'Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
      'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'
    ];
    const [year, month] = monthStr.split('-');
    return `${months[parseInt(month) - 1]} ${year}`;
  };

  if (loading) {
    return <div className="text-center py-4">Yükleniyor...</div>;
  }

  const report = reportType === 'weekly' ? weeklyReport : monthlyReport;

  return (
    <div className="space-y-4">
      {/* Header with Type Selector */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between text-lg">
            <span className="flex items-center">
              <FileText className="w-5 h-5 mr-2" />
              Teknik Servis Raporları
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-2 mb-4">
            <Button
              variant={reportType === 'weekly' ? 'default' : 'outline'}
              onClick={() => setReportType('weekly')}
              className="w-full"
            >
              📅 Haftalık
            </Button>
            <Button
              variant={reportType === 'monthly' ? 'default' : 'outline'}
              onClick={() => setReportType('monthly')}
              className="w-full"
            >
              📊 Aylık
            </Button>
          </div>

          {/* Period Navigator */}
          <div className="flex items-center justify-between p-2 bg-gray-50 rounded-lg">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => reportType === 'weekly' ? setWeekOffset(weekOffset - 1) : changeMonth(-1)}
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <span className="font-medium text-sm">
              {reportType === 'weekly' 
                ? `Hafta ${report.period.week_number} (${report.period.start} - ${report.period.end})`
                : getMonthName(currentMonth)
              }
            </span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => reportType === 'weekly' ? setWeekOffset(weekOffset + 1) : changeMonth(1)}
              disabled={reportType === 'weekly' && weekOffset >= 0}
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Summary Stats */}
      <Card className="bg-gradient-to-br from-blue-50 to-indigo-100">
        <CardContent className="p-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="text-center">
              <div className="text-3xl font-bold text-blue-600">
                {report.summary.total_tasks}
              </div>
              <div className="text-xs text-gray-600">Toplam Görev</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-green-600">
                {report.summary.completed}
              </div>
              <div className="text-xs text-gray-600">Tamamlanan</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-orange-600">
                {report.summary.completion_rate}%
              </div>
              <div className="text-xs text-gray-600">Tamamlanma</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-purple-600">
                {report.summary.sla_compliance}%
              </div>
              <div className="text-xs text-gray-600">SLA Uyum</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Performance Metrics */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Performans Metrikleri</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 bg-blue-50 rounded-lg">
              <div className="flex items-center space-x-2">
                <Clock className="w-5 h-5 text-blue-600" />
                <span className="text-sm font-medium">Ort. Yanıt Süresi</span>
              </div>
              <span className="font-bold text-blue-600">
                {report.summary.avg_response_time} dk
              </span>
            </div>

            {reportType === 'monthly' && (
              <div className="flex items-center justify-between p-3 bg-green-50 rounded-lg">
                <div className="flex items-center space-x-2">
                  <CheckCircle className="w-5 h-5 text-green-600" />
                  <span className="text-sm font-medium">Ort. Çözüm Süresi</span>
                </div>
                <span className="font-bold text-green-600">
                  {report.summary.avg_resolution_time} dk
                </span>
              </div>
            )}

            {report.summary.emergency > 0 && (
              <div className="flex items-center justify-between p-3 bg-red-50 rounded-lg">
                <div className="flex items-center space-x-2">
                  <AlertTriangle className="w-5 h-5 text-red-600" />
                  <span className="text-sm font-medium">Acil Görevler</span>
                </div>
                <Badge className="bg-red-500">{report.summary.emergency}</Badge>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Cost Breakdown (Monthly Only) */}
      {reportType === 'monthly' && monthlyReport.costs && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center text-base">
              <DollarSign className="w-5 h-5 mr-2" />
              Maliyet Analizi
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex items-center justify-between p-2 bg-gray-50 rounded">
                <span className="text-sm">Toplam Maliyet</span>
                <span className="font-bold text-lg">₺{monthlyReport.costs.total.toLocaleString()}</span>
              </div>
              <div className="flex items-center justify-between p-2 bg-gray-50 rounded text-sm">
                <span>Parça Maliyeti</span>
                <span className="font-medium">₺{monthlyReport.costs.parts.toLocaleString()}</span>
              </div>
              <div className="flex items-center justify-between p-2 bg-gray-50 rounded text-sm">
                <span>İşçilik</span>
                <span className="font-medium">₺{monthlyReport.costs.labor.toLocaleString()}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* By Category */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Kategori Bazlı</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {Object.entries(report.by_category).map(([category, data]) => (
              <div key={category} className="p-2 bg-gray-50 rounded-lg">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium capitalize">{category}</span>
                  <span className="text-sm font-bold">{data.count} görev</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-blue-500 h-2 rounded-full"
                    style={{ width: `${(data.completed / data.count) * 100}%` }}
                  />
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  {data.completed} tamamlandı
                  {reportType === 'monthly' && data.cost > 0 && ` • ₺${data.cost.toFixed(0)}`}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Top Issues (Weekly) */}
      {reportType === 'weekly' && weeklyReport.top_issues && weeklyReport.top_issues.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">En Sık Sorunlar</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {weeklyReport.top_issues.map((item, index) => (
                <div key={index} className="flex items-center justify-between p-2 bg-gray-50 rounded">
                  <span className="text-sm">{item.issue}</span>
                  <Badge variant="outline">{item.count}</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Most Active Rooms (Monthly) */}
      {reportType === 'monthly' && monthlyReport.most_active_rooms && monthlyReport.most_active_rooms.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">En Aktif Odalar</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {monthlyReport.most_active_rooms.slice(0, 5).map((room, index) => (
                <div key={index} className="flex items-center justify-between p-2 bg-gray-50 rounded">
                  <span className="text-sm font-medium">{room.room}</span>
                  <Badge className="bg-orange-500">{room.tasks} görev</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default MaintenanceReports;
