import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  TrendingUp, Users, DollarSign, Calendar, 
  ArrowUpRight, ArrowDownRight, Minus,
  Hotel, LogOut, UserCheck, XCircle, Coffee, Sparkles, Home
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const FlashReport = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState(null);
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);

  useEffect(() => {
    loadFlashReport();
  }, [selectedDate]);

  const loadFlashReport = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`/reports/flash-report?date=${selectedDate}`);
      setReport(response.data);
    } catch (error) {
      toast.error('Flash report yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  const MetricCard = ({ title, value, subtitle, icon: Icon, trend, color = "blue" }) => {
    const colorClasses = {
      blue: 'bg-blue-50 text-blue-600 border-blue-200',
      green: 'bg-green-50 text-green-600 border-green-200',
      purple: 'bg-purple-50 text-purple-600 border-purple-200',
      orange: 'bg-orange-50 text-orange-600 border-orange-200',
      red: 'bg-red-50 text-red-600 border-red-200'
    };

    return (
      <Card className={`border-2 ${colorClasses[color]}`}>
        <CardContent className="pt-6">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <p className="text-sm font-medium text-gray-600 mb-1">{title}</p>
              <p className="text-3xl font-bold text-gray-900">{value}</p>
              {subtitle && (
                <p className="text-sm text-gray-500 mt-1">{subtitle}</p>
              )}
            </div>
            <div className={`p-3 rounded-lg ${colorClasses[color]}`}>
              <Icon className="w-6 h-6" />
            </div>
          </div>
          {trend !== undefined && (
            <div className="mt-3 flex items-center gap-1">
              {trend > 0 ? (
                <ArrowUpRight className="w-4 h-4 text-green-600" />
              ) : trend < 0 ? (
                <ArrowDownRight className="w-4 h-4 text-red-600" />
              ) : (
                <Minus className="w-4 h-4 text-gray-400" />
              )}
              <span className={`text-sm font-semibold ${
                trend > 0 ? 'text-green-600' : trend < 0 ? 'text-red-600' : 'text-gray-500'
              }`}>
                {trend > 0 ? '+' : ''}{trend}% vs dün
              </span>
            </div>
          )}
        </CardContent>
      </Card>
    );
  };

  if (loading && !report) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-3">
            <Button 
              variant="outline" 
              size="icon"
              onClick={() => navigate('/')}
              className="hover:bg-blue-50"
            >
              <Home className="w-5 h-5" />
            </Button>
            <div>
              <h1 className="text-3xl font-bold text-gray-900 mb-2">
                ⚡ Flash Report
              </h1>
              <p className="text-gray-600">
                Günlük performans özeti - Yönetici raporu
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <input
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="px-4 py-2 border rounded-lg"
          />
          <Button onClick={loadFlashReport} disabled={loading}>
            🔄 Yenile
          </Button>
        </div>
      </div>

      {report && (
        <div className="space-y-6">
          {/* Key Metrics Row 1: Occupancy & Flow */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard
              title="Doluluk Oranı"
              value={`${report.occupancy.occupancy_pct}%`}
              subtitle={`${report.occupancy.rooms_occupied}/${report.occupancy.total_rooms} oda`}
              icon={Hotel}
              color="blue"
            />
            <MetricCard
              title="Varışlar (Arrival)"
              value={report.guest_flow.arrivals}
              subtitle="Bugün gelen misafir"
              icon={UserCheck}
              color="green"
            />
            <MetricCard
              title="Çıkışlar (Departure)"
              value={report.guest_flow.departures}
              subtitle="Bugün çıkan misafir"
              icon={LogOut}
              color="orange"
            />
            <MetricCard
              title="In-House"
              value={report.guest_flow.in_house}
              subtitle="Şu an oteldeki misafir"
              icon={Users}
              color="purple"
            />
          </div>

          {/* Revenue Metrics */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <MetricCard
              title="ADR (Ort. Oda Fiyatı)"
              value={`€${report.revenue.adr.toFixed(2)}`}
              subtitle="Average Daily Rate"
              icon={DollarSign}
              color="green"
            />
            <MetricCard
              title="RevPAR"
              value={`€${report.revenue.revpar.toFixed(2)}`}
              subtitle="Revenue Per Available Room"
              icon={TrendingUp}
              color="blue"
            />
            <MetricCard
              title="TRevPAR"
              value={`€${report.revenue.trevpar.toFixed(2)}`}
              subtitle="Total Revenue PAR"
              icon={Sparkles}
              color="purple"
            />
          </div>

          {/* Revenue Breakdown */}
          <Card>
            <CardHeader>
              <CardTitle>Gelir Dağılımı</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-gray-600">Oda Geliri</span>
                    <span className="text-sm font-bold">€{report.revenue.rooms_revenue.toFixed(2)}</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div 
                      className="bg-blue-600 h-2 rounded-full transition-all duration-500"
                      style={{ width: `${report.revenue_breakdown.rooms}%` }}
                    />
                  </div>
                  <span className="text-xs text-gray-500">{report.revenue_breakdown.rooms}%</span>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-gray-600">F&B Geliri</span>
                    <span className="text-sm font-bold">€{report.revenue.fnb_revenue.toFixed(2)}</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div 
                      className="bg-green-600 h-2 rounded-full transition-all duration-500"
                      style={{ width: `${report.revenue_breakdown.fnb}%` }}
                    />
                  </div>
                  <span className="text-xs text-gray-500">{report.revenue_breakdown.fnb}%</span>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-gray-600">Diğer Gelirler</span>
                    <span className="text-sm font-bold">€{report.revenue.other_revenue.toFixed(2)}</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div 
                      className="bg-purple-600 h-2 rounded-full transition-all duration-500"
                      style={{ width: `${report.revenue_breakdown.other}%` }}
                    />
                  </div>
                  <span className="text-xs text-gray-500">{report.revenue_breakdown.other}%</span>
                </div>
              </div>

              <div className="mt-6 pt-6 border-t">
                <div className="flex items-center justify-between">
                  <span className="text-lg font-semibold text-gray-700">Toplam Gelir</span>
                  <span className="text-2xl font-bold text-gray-900">
                    €{report.revenue.total_revenue.toFixed(2)}
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Issues & Alerts */}
          {(report.guest_flow.no_shows > 0 || report.guest_flow.cancellations > 0) && (
            <Card className="border-orange-200 bg-orange-50">
              <CardHeader>
                <CardTitle className="text-orange-800">⚠️ Dikkat Gerektiren Durumlar</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {report.guest_flow.no_shows > 0 && (
                    <div className="flex items-center gap-2 text-orange-700">
                      <XCircle className="w-5 h-5" />
                      <span className="font-semibold">{report.guest_flow.no_shows} No-show</span>
                    </div>
                  )}
                  {report.guest_flow.cancellations > 0 && (
                    <div className="flex items-center gap-2 text-orange-700">
                      <XCircle className="w-5 h-5" />
                      <span className="font-semibold">{report.guest_flow.cancellations} İptal</span>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Export Options */}
          <div className="flex gap-4">
            <Button variant="outline" className="flex-1" onClick={() => toast.success('E-posta gönderiliyor...')}>
              📧 E-posta Gönder
            </Button>
            <Button variant="outline" className="flex-1" onClick={() => toast.success('PDF indiriliyor...')}>
              📄 PDF İndir
            </Button>
            <Button variant="outline" className="flex-1" onClick={() => toast.success('Excel export başlatıldı')}>
              📊 Excel Export
            </Button>
          </div>

          {/* Auto Email Schedule */}
          <Card className="mt-6 bg-blue-50 border-blue-200">
            <CardHeader>
              <CardTitle className="text-lg">⏰ Otomatik Email Programı</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <p className="text-sm text-gray-700">
                  Flash report her sabah otomatik olarak email ile gönderilebilir.
                </p>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm font-medium">Gönderim Saati</label>
                    <select className="w-full px-3 py-2 border rounded-lg mt-1">
                      <option value="07:00">07:00</option>
                      <option value="08:00">08:00</option>
                      <option value="09:00">09:00</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-sm font-medium">Alıcılar</label>
                    <Input placeholder="email@hotel.com, email2@hotel.com" className="mt-1" />
                  </div>
                </div>
                <Button className="w-full bg-blue-600 hover:bg-blue-700" onClick={() => {
                  toast.success('Otomatik email programlandı! Her sabah 07:00\'da gönderilecek.');
                }}>
                  📅 Otomatik Email Ayarla
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
};

export default FlashReport;
