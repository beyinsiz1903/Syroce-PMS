import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { alertDialog } from '@/lib/dialogs';
const API_URL = import.meta.env.VITE_BACKEND_URL || '';
const LoyaltyAutoTierManager = () => {
  const [upgrades, setUpgrades] = useState([]);
  const [guestPersonas, setGuestPersonas] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedGuest, setSelectedGuest] = useState(null);
  const [personaAnalysis, setPersonaAnalysis] = useState(null);
  const runAutoTierUpgrade = async () => {
    setLoading(true);
    try {
      const response = await axios.post(`/ai/loyalty/auto-tier-upgrade`, {}, {
        headers: {}
      });
      setUpgrades(response.data.upgrades || []);
      alertDialog({
        message: `${response.data.upgrades_applied} loyalty upgrades applied!`
      });
    } catch (error) {
      console.error('Error running auto-tier upgrade:', error);
    } finally {
      setLoading(false);
    }
  };
  const analyzeGuestPersona = async guestId => {
    setLoading(true);
    try {
      const response = await axios.post(`/ai/guest-persona/analyze/${guestId}`, {}, {
        headers: {}
      });
      setPersonaAnalysis(response.data);
    } catch (error) {
      console.error('Error analyzing guest persona:', error);
    } finally {
      setLoading(false);
    }
  };
  const fetchGuestInsights = async () => {
    try {
      const response = await axios.get(`/ai/guest-persona/all-insights`, {
        headers: {}
      });
      setGuestPersonas(response.data.insights || []);
    } catch (error) {
      console.error('Error fetching guest insights:', error);
    }
  };
  return <div className="p-6 bg-white overflow-hidden">
      <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4 mb-6">
        <h1 className="text-3xl font-bold">AI Loyalty Auto-Tier</h1>
        <div className="flex flex-wrap gap-4">
          <button onClick={fetchGuestInsights} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
            Refresh Insights
          </button>
          <button onClick={runAutoTierUpgrade} disabled={loading} className="px-4 py-2 bg-gradient-to-r from-indigo-600 to-pink-600 text-white rounded-lg hover:from-indigo-700 hover:to-pink-700 disabled:opacity-50">
            {loading ? 'Processing...' : 'Run Auto-Tier Upgrade'}
          </button>
        </div>
      </div>

      {/* Recent Upgrades */}
      {upgrades.length > 0 && <div className="mb-6">
          <h2 className="text-xl font-semibold mb-4">Recent Auto-Upgrades ({upgrades.length})</h2>
          <div className="space-y-3">
            {upgrades.map((upgrade, idx) => <div key={idx} className={`border-l-4 rounded-lg p-4 ${upgrade.action === 'tier_upgrade' ? 'border-indigo-500 bg-indigo-50' : upgrade.action === 'ota_to_direct_bonus' ? 'border-green-500 bg-green-50' : 'border-blue-500 bg-blue-50'}`}>
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <h3 className="font-semibold text-lg mb-1">{upgrade.guest_name}</h3>
                    <p className="text-gray-700 mb-2">{upgrade.reason}</p>
                    {upgrade.action === 'tier_upgrade' && <div className="flex items-center gap-3">
                        <span className="px-3 py-1 bg-gray-200 rounded">{upgrade.old_tier}</span>
                        <span>→</span>
                        <span className="px-3 py-1 bg-indigo-600 text-white rounded font-semibold">{upgrade.new_tier}</span>
                      </div>}
                    {upgrade.bonus_points && <div className="mt-2">
                        <span className="text-green-600 font-semibold">+{upgrade.bonus_points} points</span>
                        <span className="text-gray-600 ml-2">({upgrade.old_points} → {upgrade.new_points})</span>
                      </div>}
                    {upgrade.benefits_unlocked && <div className="mt-2">
                        <p className="text-sm font-medium text-gray-700 mb-1">New Benefits:</p>
                        <div className="flex flex-wrap gap-2">
                          {upgrade.benefits_unlocked.map((benefit, bidx) => <span key={bidx} className="text-xs bg-white border px-2 py-1 rounded">{benefit}</span>)}
                        </div>
                      </div>}
                  </div>
                </div>
              </div>)}
          </div>
        </div>}

      {/* Guest Persona Insights */}
      <div>
        <h2 className="text-xl font-semibold mb-4">Guest Persona Intelligence</h2>
        <div className="grid grid-cols-3 gap-4">
          {[{
          type: 'price_sensitive',
          icon: '',
          color: 'blue',
          label: 'Price Sensitive'
        }, {
          type: 'experience_seeker',
          icon: '',
          color: 'purple',
          label: 'Experience Seeker'
        }, {
          type: 'high_ltv',
          icon: '',
          color: 'yellow',
          label: 'High LTV'
        }, {
          type: 'upsell_candidate',
          icon: '',
          color: 'green',
          label: 'Upsell Candidate'
        }, {
          type: 'ota_to_direct_candidate',
          icon: '',
          color: 'orange',
          label: 'OTA → Direct'
        }, {
          type: 'complainer',
          icon: '',
          color: 'red',
          label: 'Complainer'
        }].map(persona => <div key={persona.type} className={`bg-${persona.color}-50 border-2 border-${persona.color}-200 rounded-lg p-4`}>
              <div className="text-3xl mb-2">{persona.icon}</div>
              <div className="font-semibold mb-1">{persona.label}</div>
              <div className="text-2xl font-bold text-${persona.color}-600">
                {guestPersonas.filter(g => g.persona_type === persona.type).length}
              </div>
              <div className="text-sm text-gray-600 mt-2">guests identified</div>
            </div>)}
        </div>
      </div>

      {/* Persona Analysis Modal */}
      {personaAnalysis && <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-[800px] max-h-[80vh] overflow-y-auto">
            <h3 className="text-2xl font-bold mb-4">AI Persona Analysis - {personaAnalysis.guest_name}</h3>
            
            <div className="grid grid-cols-3 gap-4 mb-6">
              <div className="bg-blue-50 p-3 rounded">
                <div className="text-sm text-gray-600">Total Bookings</div>
                <div className="text-2xl font-bold">{personaAnalysis.analysis_summary.total_bookings}</div>
              </div>
              <div className="bg-green-50 p-3 rounded">
                <div className="text-sm text-gray-600">Lifetime Value</div>
                <div className="text-2xl font-bold">${personaAnalysis.analysis_summary.lifetime_value}</div>
              </div>
              <div className="bg-indigo-50 p-3 rounded">
                <div className="text-sm text-gray-600">Personas Detected</div>
                <div className="text-2xl font-bold">{personaAnalysis.personas_detected}</div>
              </div>
            </div>

            <div className="space-y-4">
              {personaAnalysis.personas.map((persona, idx) => <div key={idx} className="border rounded-lg p-4">
                  <div className="flex justify-between items-start mb-3">
                    <h4 className="text-lg font-semibold">{persona.type.replace('_', ' ').toUpperCase()}</h4>
                    <span className="px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm font-semibold">
                      {Math.round(persona.confidence * 100)}% confidence
                    </span>
                  </div>
                  <div className="mb-3">
                    <p className="text-sm font-medium text-gray-700 mb-2">Indicators:</p>
                    <ul className="list-disc list-inside text-sm space-y-1">
                      {persona.indicators.map((indicator, iidx) => <li key={iidx}>{indicator}</li>)}
                    </ul>
                  </div>
                  <div className="bg-blue-50 p-3 rounded">
                    <p className="text-sm font-medium text-gray-700 mb-2">Recommendations:</p>
                    <ul className="list-disc list-inside text-sm space-y-1">
                      {persona.recommendations.map((rec, ridx) => <li key={ridx}>{rec}</li>)}
                    </ul>
                  </div>
                </div>)}
            </div>

            <button onClick={() => setPersonaAnalysis(null)} className="mt-6 px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300 w-full">
              Close
            </button>
          </div>
        </div>}
    </div>;
};
export default LoyaltyAutoTierManager;