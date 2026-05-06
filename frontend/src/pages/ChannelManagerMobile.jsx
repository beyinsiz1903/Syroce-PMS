import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import PropertySwitcher from '@/components/PropertySwitcher';
import { ArrowLeft, Globe, CheckCircle, AlertTriangle, BarChart3, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const ChannelManagerMobile = ({ user }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [channels, setChannels] = useState([]);
  const [parity, setParity] = useState([]);
  const [performance, setPerformance] = useState([]);
  const [activeView, setActiveView] = useState('status');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [statusRes, parityRes, perfRes] = await Promise.all([
        axios.get('/channels/status'),
        axios.get('/channels/rate-parity'),
        axios.get('/channels/performance')
      ]);
      setChannels(statusRes.data.channels || []);
      setParity(parityRes.data.parity_data || []);
      setPerformance(perfRes.data.performance || []);
    } catch (error) {
      console.error('Failed to load channel data:', error);
      toast.error('Kanal verileri yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div className="min-h-screen bg-gradient-to-br from-emerald-50 to-teal-50 flex items-center justify-center"><RefreshCw className="h-12 w-12 animate-spin text-emerald-600" /></div>;

  return (
    <div className="min-h-screen bg-gradient-to-br from-emerald-50 to-teal-50 pb-20">
      <div className="bg-gradient-to-r from-emerald-600 to-teal-600 text-white p-4 sticky top-0 z-10 shadow-lg">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate(-1)} className="p-2 hover:bg-white/20 rounded-lg"><ArrowLeft className="h-5 w-5" /></button>
            <div><h1 className="text-xl font-bold">Kanal Yönetimi</h1><p className="text-emerald-100 text-sm">OTA Bağlantıları</p></div>
          </div>
          <button onClick={loadData} className="p-2 hover:bg-white/20 rounded-lg"><RefreshCw className="h-5 w-5" /></button>
        </div>
        <div className="flex gap-2">
          {['status', 'parity', 'performance'].map(view => (
            <button key={view} onClick={() => setActiveView(view)} className={`flex-1 py-2 rounded-lg text-sm ${activeView === view ? 'bg-white text-emerald-600' : 'bg-white/20'}`}>
              {view === 'status' ? 'Durum' : view === 'parity' ? 'Parite' : 'Performans'}
            </button>
          ))}
        </div>
      </div>

      <div className="p-4 space-y-3">
        {activeView === 'status' && channels.map(channel => (
          <Card key={channel.channel} className={`border-l-4 ${channel.connection_health === 'good' ? 'border-green-500' : 'border-amber-500'}`}>
            <CardContent className="p-4">
              <div className="flex justify-between items-start mb-3">
                <div>
                  <div className="font-bold text-lg flex items-center gap-2">
                    <Globe className="h-5 w-5" />
                    {channel.channel}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">Son senkron: {new Date(channel.last_sync).toLocaleTimeString('tr-TR')}</div>
                </div>
                {channel.connection_health === 'good' ? <CheckCircle className="h-6 w-6 text-green-500" /> : <AlertTriangle className="h-6 w-6 text-amber-500" />}
              </div>
              <div className="grid grid-cols-3 gap-2 text-sm">
                <div className="text-center bg-green-50 p-2 rounded">
                  <div className="font-bold text-green-600">{channel.bookings_today}</div>
                  <div className="text-xs text-gray-600">Bugün</div>
                </div>
                <div className="text-center bg-blue-50 p-2 rounded">
                  <div className="font-bold text-blue-600">{channel.inventory_synced ? '✓' : '✗'}</div>
                  <div className="text-xs text-gray-600">Envanter</div>
                </div>
                <div className="text-center bg-indigo-50 p-2 rounded">
                  <div className="font-bold text-indigo-600">{channel.rates_synced ? '✓' : '✗'}</div>
                  <div className="text-xs text-gray-600">Fiyat</div>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}

        {activeView === 'parity' && parity.map((p, idx) => (
          <Card key={idx} className={`${p.parity_status === 'violation' ? 'bg-red-50 border-red-200' : 'bg-green-50 border-green-200'} border-l-4`}>
            <CardContent className="p-4">
              <div className="flex justify-between items-start mb-3">
                <div>
                  <div className="font-bold">{p.room_type}</div>
                  <div className="text-sm text-gray-600">{p.date}</div>
                </div>
                <Badge className={`${p.parity_status === 'good' ? 'bg-green-500' : 'bg-red-500'} text-white`}>
                  {p.parity_status === 'good' ? 'UYUMLU' : 'İHLAL'}
                </Badge>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div><span className="text-gray-600">PMS:</span> <span className="font-bold">₺{p.our_pms_rate}</span></div>
                <div><span className="text-gray-600">Booking:</span> ₺{p.booking_com}</div>
                <div><span className="text-gray-600">Expedia:</span> ₺{p.expedia}</div>
                <div><span className="text-gray-600">Agoda:</span> <span className={p.violating_channel === 'Agoda' ? 'font-bold text-red-600' : ''}>₺{p.agoda}</span></div>
              </div>
            </CardContent>
          </Card>
        ))}

        {activeView === 'performance' && performance.map(perf => (
          <Card key={perf.channel}>
            <CardContent className="p-4">
              <div className="flex justify-between items-start mb-3">
                <div>
                  <div className="font-bold text-lg">{perf.channel}</div>
                  <Badge variant="outline">Pazar Payı: %{perf.market_share}</Badge>
                </div>
                <BarChart3 className="h-6 w-6 text-emerald-600" />
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="bg-blue-50 p-2 rounded">
                  <div className="text-gray-500 text-xs">Rezervasyon</div>
                  <div className="font-bold text-blue-600">{perf.bookings}</div>
                </div>
                <div className="bg-green-50 p-2 rounded">
                  <div className="text-gray-500 text-xs">{t("finance.revenue")}</div>
                  <div className="font-bold text-green-600">₺{(perf.revenue / 1000).toFixed(0)}K</div>
                </div>
                <div className="bg-indigo-50 p-2 rounded">
                  <div className="text-gray-500 text-xs">Ort. Fiyat</div>
                  <div className="font-bold text-indigo-600">₺{perf.avg_rate}</div>
                </div>
                <div className="bg-amber-50 p-2 rounded">
                  <div className="text-gray-500 text-xs">İptal Oranı</div>
                  <div className="font-bold text-amber-600">%{perf.cancellation_rate}</div>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      <PropertySwitcher onPropertyChange={loadData} />
    </div>
  );
};

export default ChannelManagerMobile;