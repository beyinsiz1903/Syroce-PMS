import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const API_URL = import.meta.env.VITE_BACKEND_URL || '';

const AIRMSDashboard = () => {
  const [competitorRates, setCompetitorRates] = useState([]);
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
      const token = localStorage.getItem('token');
      const response = await axios.post(
        `${API_URL}/api/rms/ai-pricing/competitor-scrape`,
        {
          date: new Date().toISOString().split('T')[0],
          competitors: ['Competitor A', 'Competitor B', 'Competitor C'],
          room_types: ['Standard', 'Deluxe']
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setCompetitorRates(response.data.competitor_rates || []);
    } catch (error) {
      console.error('Error scraping competitor rates:', error);
    } finally {
      setLoading(false);
    }
  };

  const calculateElasticity = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await axios.post(
        `${API_URL}/api/rms/ai-pricing/calculate-elasticity`,
        { room_type: 'Standard', analysis_days: 90 },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setElasticity(response.data);
    } catch (error) {
      console.error('Error calculating elasticity:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchMarketCompression = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get(
        `${API_URL}/api/rms/market-compression`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setMarketCompression(response.data);
    } catch (error) {
      console.error('Error fetching market compression:', error);
    }
  };

  const autoPublishRates = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const today = new Date();
      const endDate = new Date(today);
      endDate.setDate(endDate.getDate() + 30);
      
      const response = await axios.post(
        `${API_URL}/api/rms/ai-pricing/auto-publish-rates`,
        {
          start_date: today.toISOString().split('T')[0],
          end_date: endDate.toISOString().split('T')[0],
          strategy: 'revenue_optimization'
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      alert(`Success! ${response.data.rates_published} rates published. Avg rate: $${response.data.avg_rate}`);
    } catch (error) {
      console.error('Error publishing rates:', error);
      alert('Failed to publish rates');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 bg-white">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">🤖 AI Revenue Management</h1>
        <button
          onClick={autoPublishRates}
          disabled={loading}
          className="px-6 py-3 bg-gradient-to-r from-purple-600 to-blue-600 text-white rounded-lg hover:from-purple-700 hover:to-blue-700 disabled:opacity-50 font-semibold text-lg"
        >
          {loading ? '⏳ Publishing...' : '🚀 Auto-Publish AI Rates'}
        </button>
      </div>

      {/* Market Compression */}
      {marketCompression && (
        <div className="mb-6">
          <h2 className="text-xl font-semibold mb-4">Market Compression Analysis</h2>
          <div className="grid grid-cols-3 gap-4 mb-4">
            <div className={`p-4 rounded-lg ${
              marketCompression.compression_score > 70 ? 'bg-red-50 border-red-200' :
              marketCompression.compression_score > 40 ? 'bg-yellow-50 border-yellow-200' : 'bg-green-50 border-green-200'
            } border-2`}>
              <div className="text-sm text-gray-600">Compression Score</div>
              <div className={`text-3xl font-bold ${
                marketCompression.compression_score > 70 ? 'text-red-600' :
                marketCompression.compression_score > 40 ? 'text-yellow-600' : 'text-green-600'
              }`}>
                {marketCompression.compression_score}
              </div>
              <div className="text-sm font-medium mt-1">{marketCompression.compression_level}</div>
            </div>
            <div className="bg-blue-50 p-4 rounded-lg border-2 border-blue-200">
              <div className="text-sm text-gray-600">City Occupancy</div>
              <div className="text-3xl font-bold text-blue-600">{marketCompression.city_occupancy_estimate}</div>
            </div>
            <div className="bg-purple-50 p-4 rounded-lg border-2 border-purple-200">
              <div className="text-sm text-gray-600">Pricing Opportunity</div>
              <div className="text-3xl font-bold text-purple-600">{marketCompression.pricing_opportunity_pct}%</div>
            </div>
          </div>
          <div className="bg-blue-100 border-l-4 border-blue-500 p-4 rounded">
            <p className="font-semibold text-blue-900">💡 {marketCompression.recommendation}</p>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <button
          onClick={scrapeCompetitorRates}
          disabled={loading}
          className="p-4 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          🔍 Scrape Competitor Rates
        </button>
        <button
          onClick={calculateElasticity}
          disabled={loading}
          className="p-4 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
        >
          📈 Calculate Elasticity
        </button>
        <button
          onClick={fetchMarketCompression}
          disabled={loading}
          className="p-4 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
        >
          🎯 Refresh Compression
        </button>
      </div>

      {/* Competitor Rates */}
      {competitorRates.length > 0 && (
        <div className="mb-6">
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
                {competitorRates.map((rate, idx) => (
                  <tr key={idx} className="border-b hover:bg-gray-50">
                    <td className="p-3 font-medium">{rate.competitor}</td>
                    <td className="p-3">{rate.room_type}</td>
                    <td className="p-3">
                      <span className="text-lg font-bold text-green-600">${rate.rate}</span>
                    </td>
                    <td className="p-3 text-gray-600">{rate.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Price Elasticity */}
      {elasticity && (
        <div className="mb-6">
          <h2 className="text-xl font-semibold mb-4">Price Elasticity Analysis</h2>
          <div className="bg-white border rounded-lg p-6">
            <div className="grid grid-cols-2 gap-6 mb-4">
              <div>
                <div className="text-sm text-gray-600 mb-1">Elasticity Coefficient</div>
                <div className="text-3xl font-bold text-blue-600">{elasticity.elasticity_coefficient}</div>
                <div className="text-sm text-gray-600 mt-1">{elasticity.interpretation}</div>
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
                {elasticity.recommendations.map((rec, idx) => (
                  <li key={idx} className="text-sm">{rec}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AIRMSDashboard;