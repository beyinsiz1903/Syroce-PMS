import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

const API_URL = import.meta.env.VITE_BACKEND_URL || '';

const PredictiveMaintenanceDashboard = () => {
  const [alerts, setAlerts] = useState([]);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [assigningId, setAssigningId] = useState(null);
  const [assignedIds, setAssignedIds] = useState({});

  const guessIssueType = (equipment = '') => {
    const eq = equipment.toLowerCase();
    if (eq.includes('hvac') || eq.includes('ac') || eq.includes('heat')) return 'hvac';
    if (eq.includes('plumb') || eq.includes('water') || eq.includes('pipe')) return 'plumbing';
    if (eq.includes('electric') || eq.includes('light') || eq.includes('power')) return 'electrical';
    if (eq.includes('furniture') || eq.includes('door') || eq.includes('bed')) return 'furniture';
    return 'other';
  };

  const assignTask = async (alert, idx) => {
    if (assignedIds[idx]) return;
    setAssigningId(idx);
    try {
      const token = localStorage.getItem('token');
      const priorityMap = { critical: 'urgent', high: 'high', medium: 'normal', low: 'low' };
      const payload = {
        room_number: String(alert.room_number || ''),
        issue_type: guessIssueType(alert.equipment),
        priority: priorityMap[alert.severity] || 'normal',
        source: 'sensor',
        description: `[Predictive] ${alert.prediction || alert.equipment}. Recommended: ${alert.recommended_action || ''}`.trim(),
      };
      await axios.post(`/maintenance/work-orders`, payload, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setAssignedIds((s) => ({ ...s, [idx]: true }));
      toast.success(`Work order created for Room ${alert.room_number}`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to assign task');
    } finally {
      setAssigningId(null);
    }
  };

  useEffect(() => {
    fetchAlerts();
  }, []);

  const fetchAlerts = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get(
        `/ai/predictive-maintenance/dashboard`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setAlerts(response.data.alerts || []);
    } catch (error) {
      console.error('Error fetching alerts:', error);
    }
  };

  const runAnalysis = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await axios.post(
        `/ai/predictive-maintenance/analyze`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setAnalysisResult(response.data);
      fetchAlerts();
    } catch (error) {
      console.error('Error running analysis:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 bg-white">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">🔮 Predictive Maintenance</h1>
        <button
          onClick={runAnalysis}
          disabled={loading}
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2"
        >
          {loading ? '⏳ Analyzing...' : '🤖 Run AI Analysis'}
        </button>
      </div>

      {/* Analysis Result */}
      {analysisResult && (
        <div className="mb-6">
          <div className="grid grid-cols-4 gap-4 mb-6">
            <div className="bg-blue-50 p-4 rounded-lg">
              <div className="text-sm text-gray-600">Rooms Analyzed</div>
              <div className="text-2xl font-bold text-blue-600">{analysisResult.rooms_analyzed}</div>
            </div>
            <div className="bg-red-50 p-4 rounded-lg">
              <div className="text-sm text-gray-600">High Priority</div>
              <div className="text-2xl font-bold text-red-600">{analysisResult.high_priority}</div>
            </div>
            <div className="bg-yellow-50 p-4 rounded-lg">
              <div className="text-sm text-gray-600">Medium Priority</div>
              <div className="text-2xl font-bold text-yellow-600">{analysisResult.medium_priority}</div>
            </div>
            <div className="bg-green-50 p-4 rounded-lg">
              <div className="text-sm text-gray-600">Cost Savings</div>
              <div className="text-2xl font-bold text-green-600">{analysisResult.cost_savings_estimate}</div>
            </div>
          </div>
          <div className="bg-green-100 border-l-4 border-green-500 p-4 rounded">
            <p className="font-semibold">{analysisResult.summary}</p>
          </div>
        </div>
      )}

      {/* Active Alerts */}
      <h2 className="text-xl font-semibold mb-4">Active Predictive Alerts ({alerts.length})</h2>
      <div className="space-y-4">
        {alerts.map((alert, idx) => (
          <div
            key={idx}
            className={`border-l-4 rounded-lg p-4 ${
              alert.severity === 'critical' ? 'border-red-500 bg-red-50' :
              alert.severity === 'high' ? 'border-amber-500 bg-amber-50' :
              'border-yellow-500 bg-yellow-50'
            }`}
          >
            <div className="flex justify-between items-start">
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-2">
                  <span className={`px-3 py-1 rounded-full text-sm font-semibold ${
                    alert.severity === 'critical' ? 'bg-red-200 text-red-800' :
                    alert.severity === 'high' ? 'bg-amber-200 text-amber-800' :
                    'bg-yellow-200 text-yellow-800'
                  }`}>
                    {alert.severity.toUpperCase()}
                  </span>
                  <span className="text-lg font-bold">Room {alert.room_number}</span>
                  <span className="text-gray-600">{alert.equipment}</span>
                </div>
                <p className="text-gray-800 mb-2">🔍 {alert.prediction}</p>
                {alert.days_until_failure && (
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-red-600 font-semibold">
                      ⏰ Estimated failure in {alert.days_until_failure} days
                    </span>
                  </div>
                )}
                <div className="bg-white p-3 rounded border mt-2">
                  <p className="font-semibold text-sm text-gray-700 mb-1">✅ Recommended Action:</p>
                  <p className="text-sm">{alert.recommended_action}</p>
                </div>
              </div>
              <button
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 ml-4 disabled:opacity-60"
                onClick={() => assignTask(alert, idx)}
                disabled={assigningId === idx || !!assignedIds[idx]}
              >
                {assignedIds[idx] ? '✓ Assigned' : assigningId === idx ? 'Assigning…' : 'Assign Task'}
              </button>
            </div>
          </div>
        ))}

        {alerts.length === 0 && (
          <div className="text-center py-12 text-gray-500">
            <p className="text-lg">No active predictive alerts</p>
            <p className="text-sm mt-2">Run AI analysis to detect potential issues</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default PredictiveMaintenanceDashboard;