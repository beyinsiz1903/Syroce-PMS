import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Line, Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import { TrendingUp, DollarSign, Target, Users, Settings as SettingsIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
);

const RMSModule = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [compSet, setCompSet] = useState([]);
  const [pricingStrategy, setPricingStrategy] = useState(null);
  const [demandForecast, setDemandForecast] = useState([]);
  const [autoPricingEnabled, setAutoPricingEnabled] = useState(false);
  const [priceAdjustments, setPriceAdjustments] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadRMSData();
  }, []);

  const loadRMSData = async () => {
    try {
      const [compSetRes, strategyRes, forecastRes, adjustmentsRes] = await Promise.all([
        axios.get('/rms/comp-set'),
        axios.get('/rms/pricing-strategy'),
        axios.get('/rms/demand-forecast?days=30'),
        axios.get('/rms/price-adjustments')
      ]);

      setCompSet(compSetRes.data.competitors || compSetRes.data.comp_set || []);
      setPricingStrategy(strategyRes.data);
      setDemandForecast(forecastRes.data.forecast || forecastRes.data.forecasts || []);
      setPriceAdjustments(adjustmentsRes.data.adjustments || []);
      setAutoPricingEnabled(strategyRes.data?.auto_pricing_enabled || false);
    } catch (error) {
      console.error('Failed to load RMS data:', error);
      toast.error('Failed to load RMS data');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleAutoPricing = async (enabled) => {
    try {
      await axios.put('/rms/pricing-strategy', {
        auto_pricing_enabled: enabled
      });
      setAutoPricingEnabled(enabled);
      toast.success(`Auto-pricing ${enabled ? 'enabled' : 'disabled'}`);
    } catch (error) {
      toast.error('Failed to update pricing strategy');
    }
  };

  const handleApplyRecommendations = async () => {
    try {
      await axios.post('/rms/apply-recommendations');
      toast.success('Pricing recommendations applied');
      loadRMSData();
    } catch (error) {
      toast.error('Failed to apply recommendations');
    }
  };

  if (loading) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="rms">
        <div className="flex items-center justify-center h-screen">
          <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-600"></div>
        </div>
      </Layout>
    );
  }

  const demandChartData = {
    labels: demandForecast.map(d => new Date(d.date).toLocaleDateString()),
    datasets: [
      {
        label: 'Predicted Demand',
        data: demandForecast.map(d => d.demand_index),
        borderColor: 'rgb(59, 130, 246)',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        tension: 0.4,
        fill: true
      }
    ]
  };

  const compSetChartData = {
    labels: compSet.map(c => c.name),
    datasets: [
      {
        label: 'Average Rate',
        data: compSet.map(c => c.avg_rate),
        backgroundColor: 'rgba(16, 185, 129, 0.8)'
      },
      {
        label: 'Your Rate',
        data: compSet.map(() => pricingStrategy?.current_rate || 0),
        backgroundColor: 'rgba(59, 130, 246, 0.8)'
      }
    ]
  };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="rms">
      <div className="p-6 space-y-6">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold">Gelir Yönetim Sistemi (RMS)</h1>
            <p className="text-gray-600">Yapay zeka destekli fiyatlama ve talep tahmini</p>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <Label>Otomatik Fiyatlama</Label>
              <Switch
                checked={autoPricingEnabled}
                onCheckedChange={handleToggleAutoPricing}
              />
            </div>
            <Button onClick={handleApplyRecommendations}>
              <Target className="w-4 h-4 mr-2" />
              Önerileri Uygula
            </Button>
          </div>
        </div>

        {/* KPI Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-600">Güncel ADR</p>
                  <p className="text-2xl font-bold">${pricingStrategy?.current_rate || 0}</p>
                </div>
                <DollarSign className="w-8 h-8 text-green-500" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-600">Önerilen ADR</p>
                  <p className="text-2xl font-bold">${pricingStrategy?.recommended_rate || 0}</p>
                </div>
                <TrendingUp className="w-8 h-8 text-blue-500" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-600">Rakip Set Ort.</p>
                  <p className="text-2xl font-bold">
                    ${compSet.length > 0 ? (compSet.reduce((sum, c) => sum + c.avg_rate, 0) / compSet.length).toFixed(0) : 0}
                  </p>
                </div>
                <Target className="w-8 h-8 text-purple-500" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-600">Pazar Pozisyonu</p>
                  <p className="text-2xl font-bold">{pricingStrategy?.market_position || 'N/A'}</p>
                </div>
                <Users className="w-8 h-8 text-orange-500" />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Charts */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>30 Günlük Talep Tahmini</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-80">
                <Line
                  data={demandChartData}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } }
                  }}
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Rakip Set Analizi</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-80">
                <Bar
                  data={compSetChartData}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false
                  }}
                />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Comp Set Table */}
        <Card>
          <CardHeader>
            <CardTitle>Rakip Set Detayı</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b">
                    <th className="text-left p-2">Otel</th>
                    <th className="text-left p-2">Ortalama Fiyat</th>
                    <th className="text-left p-2">Doluluk</th>
                    <th className="text-left p-2">RevPAR</th>
                    <th className="text-left p-2">Mesafe</th>
                  </tr>
                </thead>
                <tbody>
                  {compSet.map((comp) => (
                    <tr key={comp.id} className="border-b hover:bg-gray-50">
                      <td className="p-2 font-semibold">{comp.name}</td>
                      <td className="p-2">${comp.avg_rate}</td>
                      <td className="p-2">{comp.occupancy_rate}%</td>
                      <td className="p-2">${comp.revpar}</td>
                      <td className="p-2">{comp.distance_km} km</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        {/* Recent Price Adjustments */}
        <Card>
          <CardHeader>
            <CardTitle>Son Fiyat Güncellemeleri</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {priceAdjustments.slice(0, 5).map((adj) => (
                <div key={adj.id} className="flex justify-between items-center p-3 bg-gray-50 rounded">
                  <div>
                    <div className="font-semibold">{new Date(adj.date).toLocaleDateString()}</div>
                    <div className="text-sm text-gray-600">{adj.reason}</div>
                  </div>
                  <div className="text-right">
                    <div className="font-bold">${adj.old_rate} → ${adj.new_rate}</div>
                    <div className={`text-sm ${
                      adj.new_rate > adj.old_rate ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {adj.new_rate > adj.old_rate ? '+' : ''}
                      {((adj.new_rate - adj.old_rate) / adj.old_rate * 100).toFixed(1)}%
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
};

export default RMSModule;