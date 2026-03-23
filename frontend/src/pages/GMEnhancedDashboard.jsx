import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import PropertySwitcher from '@/components/PropertySwitcher';
import {
  ArrowLeft, 
  TrendingUp,
  TrendingDown,
  Users,
  AlertTriangle,
  CheckCircle,
  Clock,
  RefreshCw,
  Target,
  MessageSquare,
  BarChart3,
  Award
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const GMEnhancedDashboard = ({ user }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [teamPerformance, setTeamPerformance] = useState(null);
  const [complaintManagement, setComplaintManagement] = useState(null);
  const [enhancedSnapshot, setEnhancedSnapshot] = useState(null);
  const [activeView, setActiveView] = useState('snapshot'); // snapshot, team, complaints

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      
      const [teamRes, complaintsRes, snapshotRes] = await Promise.all([
        axios.get('/gm/team-performance'),
        axios.get('/gm/complaint-management'),
        axios.get('/gm/snapshot-enhanced')
      ]);
      
      setTeamPerformance(teamRes.data);
      setComplaintManagement(complaintsRes.data);
      setEnhancedSnapshot(snapshotRes.data);
    } catch (error) {
      console.error('Failed to load GM data:', error);
      toast.error('GM verileri yüklenemedi');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const handleRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  const getTrendIcon = (trend) => {
    if (trend === 'up') return <TrendingUp className="h-4 w-4 text-green-500" />;
    if (trend === 'down') return <TrendingDown className="h-4 w-4 text-red-500" />;
    return null;
  };

  if (loading && !refreshing) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-indigo-50 to-purple-50 flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="h-12 w-12 animate-spin text-indigo-600 mx-auto mb-4" />
          <p className="text-gray-600">{t('nav.dashboard')} yükleniyor...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 to-purple-50 pb-20">
      {/* Header */}
      <div className="bg-gradient-to-r from-indigo-600 to-purple-600 text-white p-4 sticky top-0 z-10 shadow-lg">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate(-1)} className="p-2 hover:bg-white/20 rounded-lg transition">
              <ArrowLeft className="h-5 w-5" />
            </button>
            <div>
              <h1 className="text-xl font-bold">GM Dashboard</h1>
              <p className="text-indigo-100 text-sm">Gelişmiş Yönetim Paneli</p>
            </div>
          </div>
          
          <button
            onClick={handleRefresh}
            className="p-2 hover:bg-white/20 rounded-lg transition"
            disabled={refreshing}
          >
            <RefreshCw className={`h-5 w-5 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {/* View Tabs */}
        <div className="flex gap-2">
          <button
            onClick={() => setActiveView('snapshot')}
            className={`flex-1 py-2 rounded-lg font-semibold transition ${
              activeView === 'snapshot' ? 'bg-white text-indigo-600' : 'bg-white/20'
            }`}
          >
            Snapshot
          </button>
          <button
            onClick={() => setActiveView('team')}
            className={`flex-1 py-2 rounded-lg font-semibold transition ${
              activeView === 'team' ? 'bg-white text-indigo-600' : 'bg-white/20'
            }`}
          >
            Takım
          </button>
          <button
            onClick={() => setActiveView('complaints')}
            className={`flex-1 py-2 rounded-lg font-semibold transition ${
              activeView === 'complaints' ? 'bg-white text-indigo-600' : 'bg-white/20'
            }`}
          >
            Şikayetler
          </button>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Enhanced Snapshot View */}
        {activeView === 'snapshot' && enhancedSnapshot && (
          <>
            {/* Today vs Yesterday vs Last Week Comparison */}
            <Card className="bg-white">
              <CardContent className="p-4">
                <h3 className="font-bold text-lg mb-4">Karşılaştırmalı Özet</h3>
                
                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div className="text-center">
                    <div className="font-semibold text-gray-500">Bugün</div>
                  </div>
                  <div className="text-center">
                    <div className="font-semibold text-gray-500">Dün</div>
                  </div>
                  <div className="text-center">
                    <div className="font-semibold text-gray-500">Geçen Hafta</div>
                  </div>
                </div>

                {/* Occupancy */}
                <div className="grid grid-cols-3 gap-2 mt-3 pb-3 border-b">
                  <div className="text-center">
                    <div className="text-2xl font-bold text-indigo-600">%{enhancedSnapshot.today.occupancy}</div>
                    <div className="text-xs text-gray-500">Doluluk</div>
                  </div>
                  <div className="text-center">
                    <div className="text-xl font-semibold text-gray-600">%{enhancedSnapshot.yesterday.occupancy}</div>
                  </div>
                  <div className="text-center">
                    <div className="text-xl font-semibold text-gray-400">%{enhancedSnapshot.last_week.occupancy}</div>
                  </div>
                </div>

                {/* Revenue */}
                <div className="grid grid-cols-3 gap-2 mt-3 pb-3 border-b">
                  <div className="text-center">
                    <div className="text-2xl font-bold text-green-600">₺{(enhancedSnapshot.today.revenue / 1000).toFixed(0)}K</div>
                    <div className="text-xs text-gray-500">{t("finance.revenue")}</div>
                  </div>
                  <div className="text-center">
                    <div className="text-xl font-semibold text-gray-600">₺{(enhancedSnapshot.yesterday.revenue / 1000).toFixed(0)}K</div>
                  </div>
                  <div className="text-center">
                    <div className="text-xl font-semibold text-gray-400">₺{(enhancedSnapshot.last_week.revenue / 1000).toFixed(0)}K</div>
                  </div>
                </div>

                {/* Check-ins/outs */}
                <div className="grid grid-cols-2 gap-3 mt-3">
                  <div>
                    <div className="text-xs text-gray-500 mb-1">Check-in</div>
                    <div className="flex items-center gap-2">
                      <div className="text-xl font-bold">{enhancedSnapshot.today.check_ins}</div>
                      {getTrendIcon(enhancedSnapshot.trends.occupancy_trend)}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 mb-1">Check-out</div>
                    <div className="text-xl font-bold">{enhancedSnapshot.today.check_outs}</div>
                  </div>
                </div>

                {/* Complaints & Tasks */}
                <div className="grid grid-cols-2 gap-3 mt-3">
                  <div className="bg-orange-50 p-3 rounded-lg">
                    <div className="text-xs text-orange-600 mb-1">Şikayetler</div>
                    <div className="text-2xl font-bold text-orange-600">{enhancedSnapshot.today.complaints}</div>
                  </div>
                  <div className="bg-red-50 p-3 rounded-lg">
                    <div className="text-xs text-red-600 mb-1">Acil Görevler</div>
                    <div className="text-2xl font-bold text-red-600">{enhancedSnapshot.today.pending_tasks}</div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Trend Indicators */}
            <div className="grid grid-cols-3 gap-2">
              <Card className={`${
                enhancedSnapshot.trends.occupancy_trend === 'up' 
                  ? 'bg-green-50 border-green-200' 
                  : 'bg-red-50 border-red-200'
              }`}>
                <CardContent className="p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs">Doluluk</span>
                    {getTrendIcon(enhancedSnapshot.trends.occupancy_trend)}
                  </div>
                </CardContent>
              </Card>
              <Card className={`${
                enhancedSnapshot.trends.revenue_trend === 'up' 
                  ? 'bg-green-50 border-green-200' 
                  : 'bg-red-50 border-red-200'
              }`}>
                <CardContent className="p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs">{t("finance.revenue")}</span>
                    {getTrendIcon(enhancedSnapshot.trends.revenue_trend)}
                  </div>
                </CardContent>
              </Card>
              <Card className={`${
                enhancedSnapshot.trends.complaints_trend === 'down' 
                  ? 'bg-green-50 border-green-200' 
                  : 'bg-red-50 border-red-200'
              }`}>
                <CardContent className="p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs">Şikayetler</span>
                    {getTrendIcon(enhancedSnapshot.trends.complaints_trend === 'down' ? 'up' : 'down')}
                  </div>
                </CardContent>
              </Card>
            </div>
          </>
        )}

        {/* Team Performance View */}
        {activeView === 'team' && teamPerformance && (
          <>
            {/* Overall Performance */}
            <Card className="bg-gradient-to-r from-blue-500 to-indigo-500 text-white">
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm opacity-90">Genel Performans</div>
                    <div className="text-3xl font-bold mt-1">%{teamPerformance.overall_performance}</div>
                  </div>
                  <div className="text-right">
                    <Award className="h-12 w-12 opacity-80" />
                    <div className="text-sm mt-1">
                      {teamPerformance.departments_meeting_target}/{teamPerformance.departments.length} Hedefte
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Department Cards */}
            <div className="space-y-3">
              {teamPerformance.departments.map((dept) => (
                <Card 
                  key={dept.department}
                  className={`border-l-4 ${
                    dept.status === 'good' 
                      ? 'border-green-500 bg-green-50' 
                      : 'border-orange-500 bg-orange-50'
                  }`}
                >
                  <CardContent className="p-4">
                    <div className="flex justify-between items-start mb-3">
                      <div>
                        <h3 className="font-bold text-lg">{dept.department_tr}</h3>
                        <p className="text-sm text-gray-600">{dept.metric}</p>
                      </div>
                      <Badge className={`${
                        dept.status === 'good' 
                          ? 'bg-green-500' 
                          : 'bg-orange-500'
                      } text-white`}>
                        {dept.status === 'good' ? 'İyi' : 'İyileştirilebilir'}
                      </Badge>
                    </div>

                    {/* Progress Bar */}
                    <div className="mb-2">
                      <div className="flex justify-between text-sm mb-1">
                        <span>Mevcut</span>
                        <span className="font-bold">{dept.value}{dept.unit}</span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-3">
                        <div 
                          className={`h-3 rounded-full ${
                            dept.status === 'good' ? 'bg-green-500' : 'bg-orange-500'
                          }`}
                          style={{ width: `${Math.min(dept.value, 100)}%` }}
                        ></div>
                      </div>
                      <div className="flex justify-between text-xs mt-1 text-gray-500">
                        <span>0{dept.unit}</span>
                        <span>Hedef: {dept.target}{dept.unit}</span>
                      </div>
                    </div>

                    <div className="text-sm text-gray-600">
                      {dept.details}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </>
        )}

        {/* Complaint Management View */}
        {activeView === 'complaints' && complaintManagement && (
          <>
            {/* Complaint Summary */}
            <div className="grid grid-cols-2 gap-3">
              <Card className="bg-gradient-to-r from-orange-500 to-red-500 text-white">
                <CardContent className="p-4">
                  <div className="text-sm opacity-90">Aktif Şikayetler</div>
                  <div className="text-4xl font-bold mt-1">{complaintManagement.active_count}</div>
                </CardContent>
              </Card>
              <Card className="bg-gradient-to-r from-red-500 to-pink-500 text-white">
                <CardContent className="p-4">
                  <div className="text-sm opacity-90">Acil (&gt;2 gün)</div>
                  <div className="text-4xl font-bold mt-1">{complaintManagement.urgent_complaints}</div>
                </CardContent>
              </Card>
            </div>

            {/* Average Resolution Time */}
            <Card>
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm text-gray-500">Ort. Çözüm Süresi</div>
                    <div className="text-3xl font-bold text-blue-600">{complaintManagement.avg_resolution_time_hours} saat</div>
                  </div>
                  <Clock className="h-12 w-12 text-blue-200" />
                </div>
              </CardContent>
            </Card>

            {/* Category Breakdown */}
            <Card>
              <CardContent className="p-4">
                <h3 className="font-bold mb-3">Kategori Dağılımı</h3>
                <div className="space-y-2">
                  {complaintManagement.category_breakdown.map((cat) => (
                    <div key={cat.category} className="flex justify-between items-center">
                      <span className="text-sm">{cat.category_tr}</span>
                      <Badge variant="outline">{cat.count}</Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Active Complaints List */}
            <Card>
              <CardContent className="p-4">
                <h3 className="font-bold mb-3 flex items-center gap-2">
                  <MessageSquare className="h-5 w-5" />
                  Aktif Şikayetler
                </h3>
                <div className="space-y-3">
                  {complaintManagement.active_complaints.slice(0, 5).map((complaint) => (
                    <div 
                      key={complaint.id}
                      className={`p-3 rounded-lg border-l-4 ${
                        complaint.days_open > 2 
                          ? 'border-red-500 bg-red-50' 
                          : 'border-orange-500 bg-orange-50'
                      }`}
                    >
                      <div className="flex justify-between items-start mb-2">
                        <div>
                          <div className="font-semibold">{complaint.guest_name}</div>
                          <div className="text-xs text-gray-500">{complaint.category_tr || complaint.category}</div>
                        </div>
                        <div className="flex items-center gap-1">
                          {'⭐'.repeat(complaint.rating)}
                        </div>
                      </div>
                      <div className="text-sm text-gray-700 mb-2">{complaint.comment}</div>
                      <div className="flex justify-between items-center text-xs">
                        <span className={`font-semibold ${
                          complaint.days_open > 2 ? 'text-red-600' : 'text-orange-600'
                        }`}>
                          {complaint.days_open} gün açık
                        </span>
                        {complaint.days_open > 2 && (
                          <Badge variant="destructive" className="text-xs">ACİL</Badge>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </>
        )}
      </div>

      {/* Property Switcher */}
      <PropertySwitcher onPropertyChange={() => loadData()} />
    </div>
  );
};

export default GMEnhancedDashboard;