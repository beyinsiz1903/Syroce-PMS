import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
const API_URL = import.meta.env.VITE_BACKEND_URL || '';
const AIRMSDashboard = () => {
  const [competitorRates, setCompetitorRates] = useState([]);
  const [competitorMsg, setCompetitorMsg] = useState(null);
  const [demandForecast, setDemandForecast] = useState([]);
  const [elasticity, setElasticity] = useState(null);
  const [marketCompression, setMarketCompression] = useState(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    fetchMarketCompression();
  }, []);
  const scrapeCompetitorRates = async () => {
    setLoading(true);
    try {
      const response = await axios.post(`/rms/ai-pricing/competitor-scrape`, {
        competitors: ['Competitor A', 'Competitor B', 'Competitor C'],
        room_types: ['Standard', 'Deluxe']
      }, {
        params: {
          date: new Date().toISOString().split('T')[0]
        },
        headers: {}
      });
      setCompetitorRates(response.data.competitor_rates || []);
      setCompetitorMsg(response.data.data_available === false ? response.data.message || 'Rakip fiyat veri kaynağı yapılandırılmamış' : null);
    } catch (error) {
      console.error('Error scraping competitor rates:', error);
      setCompetitorRates([]);
      setCompetitorMsg(error.response?.data?.detail || error.response?.data?.message || 'Rakip fiyat veri kaynağı yapılandırılmamış');
    } finally {
      setLoading(false);
    }
  };
  const calculateElasticity = async () => {
    setLoading(true);
    try {
      const response = await axios.post(`/rms/ai-pricing/calculate-elasticity`, null, {
        params: {
          room_type: 'Standard',
          analysis_days: 90
        },
        headers: {}
      });
      setElasticity(response.data);
    } catch (error) {
      console.error('Error calculating elasticity:', error);
      setElasticity({
        data_available: false,
        message: error.response?.data?.detail || error.response?.data?.message || 'Fiyat esnekliği hesaplanamadı'
      });
    } finally {
      setLoading(false);
    }
  };
  const fetchMarketCompression = async () => {
    try {
      const response = await axios.get(`/rms/market-compression`, {
        headers: {}
      });
      setMarketCompression(response.data);
    } catch (error) {
      console.error('Error fetching market compression:', error);
    }
  };
  const autoPublishRates = async () => {
    setLoading(true);
    try {
      const today = new Date();
      const endDate = new Date(today);
      endDate.setDate(endDate.getDate() + 30);
      const response = await axios.post(`/rms/ai-pricing/auto-publish-rates`, null, {
        params: {
          start_date: today.toISOString().split('T')[0],
          end_date: endDate.toISOString().split('T')[0],
          strategy: 'revenue_optimization'
        },
        headers: {}
      });
      if (response.data.data_available === false || response.data.success === false) {
        toast.error(response.data.message || 'Fiyatlar yayınlanamadı: yeterli gerçek veri yok');
      } else if (response.data.dry_run) {
        toast.success(`${(response.data.published_rates || []).length} tarife hesaplandı (deneme/dry-run, yayınlanmadı)`);
      } else {
        toast.success(`${response.data.rates_published} fiyat yayınlandı • Ort. fiyat: $${response.data.avg_rate}`);
      }
    } catch (error) {
      console.error('Error publishing rates:', error);
      toast.error(error.response?.data?.detail || error.response?.data?.message || 'Fiyatlar yayınlanamadı');
    } finally {
      setLoading(false);
    }
  };
  return <div className="p-6 bg-white">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">Kural Bazlı Gelir Yönetimi</h1>
        <button onClick={autoPublishRates} disabled={loading} className="px-6 py-3 bg-slate-900 text-white rounded-lg hover:bg-slate-800 disabled:opacity-50 font-semibold text-base inline-flex items-center gap-2">
          {loading ? 'Yayınlanıyor…' : 'Tarifeleri Otomatik Yayınla'}
        </button>
      </div>

      {/* Market Compression */}
      {marketCompression && marketCompression.data_available === false && <div className="mb-6">
          <h2 className="text-xl font-semibold mb-4">Market Compression Analysis</h2>
          <div className="bg-amber-50 border-l-4 border-amber-500 p-4 rounded mb-4">
            <p className="text-sm text-amber-900">
              {marketCompression.message || 'Pazar verisi yapılandırılmamış'}
            </p>
          </div>
          {marketCompression.events && marketCompression.events.length > 0 && <div className="bg-white border rounded-lg p-4">
              <p className="font-semibold mb-2">Şehir Etkinlikleri</p>
              <ul className="list-disc list-inside space-y-1">
                {marketCompression.events.map((ev, idx) => <li key={idx} className="text-sm">
                    {ev.name}{ev.impact ? ` (${ev.impact})` : ''}
                  </li>)}
              </ul>
            </div>}
        </div>}
      {marketCompression && marketCompression.data_available !== false && <div className="mb-6">
          <h2 className="text-xl font-semibold mb-4">Market Compression Analysis</h2>
          <div className="grid grid-cols-3 gap-4 mb-4">
            <div className={`p-4 rounded-lg ${marketCompression.compression_score > 70 ? 'bg-red-50 border-red-200' : marketCompression.compression_score > 40 ? 'bg-yellow-50 border-yellow-200' : 'bg-green-50 border-green-200'} border-2`}>
              <div className="text-sm text-gray-600">Compression Score</div>
              <div className={`text-3xl font-bold ${marketCompression.compression_score > 70 ? 'text-red-600' : marketCompression.compression_score > 40 ? 'text-yellow-600' : 'text-green-600'}`}>
                {marketCompression.compression_score}
              </div>
              <div className="text-sm font-medium mt-1">{marketCompression.compression_level}</div>
            </div>
            <div className="bg-blue-50 p-4 rounded-lg border-2 border-blue-200">
              <div className="text-sm text-gray-600">City Occupancy</div>
              <div className="text-3xl font-bold text-blue-600">{marketCompression.city_occupancy_estimate}</div>
            </div>
            <div className="bg-indigo-50 p-4 rounded-lg border-2 border-indigo-200">
              <div className="text-sm text-gray-600">Pricing Opportunity</div>
              <div className="text-3xl font-bold text-indigo-600">{marketCompression.pricing_opportunity_pct}%</div>
            </div>
          </div>
          <div className="bg-blue-100 border-l-4 border-blue-500 p-4 rounded">
            <p className="font-semibold text-blue-900">{marketCompression.recommendation}</p>
          </div>
        </div>}

      {/* Actions */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <button onClick={scrapeCompetitorRates} disabled={loading} className="p-4 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
          Scrape Competitor Rates
        </button>
        <button onClick={calculateElasticity} disabled={loading} className="p-4 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50">
          Calculate Elasticity
        </button>
        <button onClick={fetchMarketCompression} disabled={loading} className="p-4 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
          Refresh Compression
        </button>
      </div>

      {/* Competitor Rates */}
      {competitorRates.length > 0 && <div className="mb-6">
          <h2 className="text-xl font-semibold mb-4">Competitor Rate Intelligence</h2>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="bg-gray-100">
                  <th className="p-3 text-left">Competitor</th>
                  <th className="p-3 text-left">Room Type</th>
                  <th className="p-3 text-left">Rate</th>
                  <th className="p-3 text-left">Source</th>
                </tr>
              </thead>
              <tbody>
                {competitorRates.map((rate, idx) => <tr key={idx} className="border-b hover:bg-gray-50">
                    <td className="p-3 font-medium">{rate.competitor}</td>
                    <td className="p-3">{rate.room_type}</td>
                    <td className="p-3">
                      <span className="text-lg font-bold text-green-600">${rate.rate}</span>
                    </td>
                    <td className="p-3 text-gray-600">{rate.source}</td>
                  </tr>)}
              </tbody>
            </table>
          </div>
        </div>}

      {competitorMsg && <div className="mb-6 bg-amber-50 border-l-4 border-amber-500 p-4 rounded">
          <p className="text-sm text-amber-900">{competitorMsg}</p>
        </div>}

      {/* Price Elasticity */}
      {elasticity && elasticity.data_available === false && <div className="mb-6 bg-amber-50 border-l-4 border-amber-500 p-4 rounded">
          <p className="text-sm text-amber-900">
            {elasticity.message || 'Fiyat esnekliği için yeterli veri yok'}
          </p>
        </div>}
      {elasticity && elasticity.data_available !== false && <div className="mb-6">
          <h2 className="text-xl font-semibold mb-4">Price Elasticity Analysis</h2>
          <div className="bg-white border rounded-lg p-6">
            <div className="grid grid-cols-2 gap-6 mb-4">
              <div>
                <div className="text-sm text-gray-600 mb-1">Elasticity Coefficient</div>
                <div className="text-3xl font-bold text-blue-600">{elasticity.elasticity_coefficient}</div>
                <div className="text-sm text-gray-600 mt-1">{elasticity.interpretation}</div>
                {typeof elasticity.fit_r2 === 'number' && <div className="text-xs text-gray-500 mt-1">
                    Uyum (R²): {elasticity.fit_r2} • {elasticity.bookings_analyzed} rezervasyon
                  </div>}
              </div>
              <div>
                <div className="text-sm text-gray-600 mb-1">Optimal Price Point</div>
                <div className="text-3xl font-bold text-green-600">${elasticity.optimal_price_point}</div>
                <div className="text-sm text-green-600 mt-1">+{elasticity.expected_revenue_lift} revenue lift</div>
              </div>
            </div>
            <div className="bg-yellow-50 border-l-4 border-yellow-500 p-4 rounded">
              <p className="font-semibold mb-2">Recommendations:</p>
              <ul className="list-disc list-inside space-y-1">
                {(elasticity.recommendations || []).map((rec, idx) => <li key={idx} className="text-sm">{rec}</li>)}
              </ul>
            </div>
          </div>
        </div>}
    </div>;
};
export default AIRMSDashboard;