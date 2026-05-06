import React, { useState } from 'react';
import EnhancedReservationCalendar from '../components/EnhancedReservationCalendar';
import EnhancedFrontDesk from '../components/EnhancedFrontDesk';
import AIHousekeepingBoard from '../components/AIHousekeepingBoard';
import PredictiveMaintenanceDashboard from '../components/PredictiveMaintenanceDashboard';
import AIRMSDashboard from '../components/AIRMSDashboard';
import LoyaltyAutoTierManager from '../components/LoyaltyAutoTierManager';
import FolioManagementPage from '../components/FolioManagementPage';
import { useTranslation } from 'react-i18next';

const AIEnhancedPMS = () => {
  const { t } = useTranslation();
  const [activeModule, setActiveModule] = useState('reservation');

  const modules = [
    { id: 'reservation', name: t('aiEnhancedPms.reservationCalendar'), component: EnhancedReservationCalendar },
    { id: 'frontdesk', name: t('aiEnhancedPms.frontDesk'), component: EnhancedFrontDesk },
    { id: 'folio', name: t('aiEnhancedPms.folioRegistration'), component: FolioManagementPage },
    { id: 'housekeeping', name: t('aiEnhancedPms.aiHousekeeping'), component: AIHousekeepingBoard },
    { id: 'maintenance', name: t('aiEnhancedPms.predictiveMaintenance'), component: PredictiveMaintenanceDashboard },
    { id: 'rms', name: t('aiEnhancedPms.aiRevenueManagement'), component: AIRMSDashboard },
    { id: 'loyalty', name: t('aiEnhancedPms.aiLoyalty'), component: LoyaltyAutoTierManager }
  ];

  const ActiveComponent = modules.find(m => m.id === activeModule)?.component || EnhancedReservationCalendar;

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <div className="bg-gradient-to-r from-indigo-600 to-blue-600 text-white p-6 shadow-lg">
        <h1 className="text-4xl font-bold mb-2">{t('aiEnhancedPms.title')}</h1>
        <p className="text-lg opacity-90">{t('aiEnhancedPms.subtitle')}</p>
      </div>

      {/* Navigation */}
      <div className="bg-white shadow-md p-4 overflow-x-auto">
        <div className="flex gap-2 min-w-max">
          {modules.map(module => (
            <button
              key={module.id}
              onClick={() => setActiveModule(module.id)}
              className={`px-6 py-3 rounded-lg font-medium transition-all whitespace-nowrap ${
                activeModule === module.id
                  ? 'bg-gradient-to-r from-indigo-600 to-blue-600 text-white shadow-lg scale-105'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {module.name}
            </button>
          ))}
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto p-6">
        <div className="bg-white rounded-lg shadow-lg">
          <ActiveComponent />
        </div>
      </div>

      {/* Footer */}
      <div className="bg-gray-800 text-white p-6 mt-8">
        <div className="container mx-auto">
          <div className="flex justify-between items-center">
            <div>
              <h3 className="font-bold text-lg mb-2">{t('aiEnhancedPms.aiFeaturesActive')}</h3>
              <ul className="text-sm space-y-1 opacity-80">
                <li>✅ {t('aiEnhancedPms.aiPricingEngine')}</li>
                <li>✅ {t('aiEnhancedPms.guestPersona')}</li>
                <li>✅ {t('aiEnhancedPms.predMaintenance')}</li>
                <li>✅ {t('aiEnhancedPms.aiHousekeepingScheduler')}</li>
                <li>✅ {t('aiEnhancedPms.autoTierLoyalty')}</li>
              </ul>
            </div>
            <div className="text-right">
              <p className="text-2xl font-bold">{t('aiEnhancedPms.apiEndpoints')}</p>
              <p className="text-sm opacity-80">{t('aiEnhancedPms.featureCategories')}</p>
              <p className="text-sm opacity-80">{t('aiEnhancedPms.aiModules')}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AIEnhancedPMS;
