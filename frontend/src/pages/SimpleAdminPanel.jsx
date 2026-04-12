import React, { useState, useEffect } from 'react';
import { AlertCircle, CheckCircle, Clock, Activity } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const SimpleAdminPanel = () => {
  const { t } = useTranslation();
  const [systemStatus, setSystemStatus] = useState(null);
  const [recentErrors, setRecentErrors] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchSystemStatus();
    // Her 30 saniyede bir güncelle
    const interval = setInterval(fetchSystemStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchSystemStatus = async () => {
    try {
      const response = await fetch(`/api/monitoring/health`);
      const data = await response.json();
      setSystemStatus(data);
      setLoading(false);
    } catch (error) {
      console.error('System status fetch error:', error);
      setLoading(false);
    }
  };

  const getStatusColor = (status) => {
    switch(status) {
      case 'healthy': return 'bg-green-500';
      case 'warning': return 'bg-yellow-500';
      case 'critical': return 'bg-red-500';
      default: return 'bg-gray-500';
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-100 flex items-center justify-center">
        <div className="text-center">
          <Clock className="w-12 h-12 animate-spin mx-auto mb-4 text-blue-600" />
          <p className="text-gray-600">{t('adminPanel.checkingStatus')}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100 p-8">
      <div className="max-w-6xl mx-auto">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">{t('adminPanel.title')}</h1>
          <p className="text-gray-600">{t('adminPanel.subtitle')}</p>
        </div>

        {/* Ana Durum Kartı */}
        <div className="bg-white rounded-lg shadow-lg p-6 mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-2xl font-semibold text-gray-900">{t('adminPanel.overallStatus')}</h2>
            <div className={`flex items-center space-x-2 px-4 py-2 rounded-full ${
              systemStatus?.status === 'healthy' ? 'bg-green-100' : 'bg-yellow-100'
            }`}>
              {systemStatus?.status === 'healthy' ? (
                <>
                  <CheckCircle className="w-5 h-5 text-green-600" />
                  <span className="text-green-600 font-semibold">{t('adminPanel.systemRunning')}</span>
                </>
              ) : (
                <>
                  <AlertCircle className="w-5 h-5 text-yellow-600" />
                  <span className="text-yellow-600 font-semibold">{t('adminPanel.attentionNeeded')}</span>
                </>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
            {/* Database Durumu */}
            <div className="bg-gray-50 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-gray-600">{t('adminPanel.database')}</span>
                <div className={`w-3 h-3 rounded-full ${
                  getStatusColor(systemStatus?.components?.database?.status)
                }`}></div>
              </div>
              <p className="text-2xl font-bold text-gray-900">
                {systemStatus?.components?.database?.status === 'healthy' ? t('adminPanel.running') : t('adminPanel.issue')}
              </p>
            </div>

            {/* CPU Durumu */}
            <div className="bg-gray-50 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-gray-600">{t('adminPanel.cpuUsage')}</span>
                <Activity className="w-4 h-4 text-blue-600" />
              </div>
              <p className="text-2xl font-bold text-gray-900">
                {systemStatus?.components?.system?.cpu_usage?.toFixed(1) || '0'}%
              </p>
            </div>

            {/* Memory Durumu */}
            <div className="bg-gray-50 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-gray-600">{t('adminPanel.memoryUsage')}</span>
                <Activity className="w-4 h-4 text-purple-600" />
              </div>
              <p className="text-2xl font-bold text-gray-900">
                {systemStatus?.components?.system?.memory_usage?.toFixed(1) || '0'}%
              </p>
            </div>
          </div>
        </div>

        {/* Bilgilendirme Kartı */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-6 mb-8">
          <div className="flex items-start space-x-3">
            <AlertCircle className="w-6 h-6 text-blue-600 flex-shrink-0 mt-1" />
            <div>
              <h3 className="text-lg font-semibold text-blue-900 mb-2">
                {t('adminPanel.troubleTitle')}
              </h3>
              <p className="text-blue-800 mb-4">
                {t('adminPanel.troubleDesc')}
              </p>
              <ol className="list-decimal list-inside space-y-2 text-blue-800">
                <li>Bana şu mesajı gönderin: <strong>"Sistem sorunu var, kontrol et"</strong></li>
                <li>Veya spesifik söyleyin: <strong>"Rezervasyon formu çalışmıyor"</strong></li>
                <li>Ben otomatik olarak:
                  <ul className="list-disc list-inside ml-6 mt-2 space-y-1">
                    <li>Sorunu tespit ederim</li>
                    <li>Düzeltirim</li>
                    <li>Test ederim</li>
                    <li>Canlıya alırım</li>
                  </ul>
                </li>
              </ol>
              <div className="mt-4 p-4 bg-white rounded border border-blue-200">
                <p className="text-sm text-blue-900 font-semibold mb-2">💡 Örnek Mesajlar:</p>
                <ul className="text-sm text-blue-800 space-y-1">
                  <li>• "Login sayfası çalışmıyor"</li>
                  <li>• "Dashboard yavaş yükleniyor"</li>
                  <li>• "Demo formu submit olmuyor"</li>
                  <li>• "Mobilde tasarım bozuk"</li>
                </ul>
              </div>
            </div>
          </div>
        </div>

        {/* İletişim Bilgisi */}
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">{t('adminPanel.monitoringActive')}</h3>
          <p className="text-gray-600 mb-4">
            {t('adminPanel.monitoringDesc')}
          </p>
          <div className="flex items-center space-x-2 text-green-600">
            <CheckCircle className="w-5 h-5" />
            <span>{t('adminPanel.monitoringStatus')}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SimpleAdminPanel;
