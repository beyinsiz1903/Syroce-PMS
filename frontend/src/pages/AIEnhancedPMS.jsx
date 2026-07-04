import React, { useState } from 'react';
import EnhancedReservationCalendar from '../components/EnhancedReservationCalendar';
import EnhancedFrontDesk from '../components/EnhancedFrontDesk';
import AIHousekeepingBoard from '../components/AIHousekeepingBoard';
import PredictiveMaintenanceDashboard from '../components/PredictiveMaintenanceDashboard';
import AIRMSDashboard from '../components/AIRMSDashboard';
import LoyaltyAutoTierManager from '../components/LoyaltyAutoTierManager';
import FolioManagementPage from '../components/FolioManagementPage';
import { useTranslation } from 'react-i18next';
import { Sparkles, Calendar, Users, ClipboardCheck, Wrench, TrendingUp, Crown, CreditCard } from 'lucide-react';

const AIEnhancedPMS = () => {
  const { t } = useTranslation();
  const [activeModule, setActiveModule] = useState('reservation');

  const modules = [
    { id: 'reservation', name: t('aiEnhancedPms.reservationCalendar'), component: EnhancedReservationCalendar, icon: Calendar },
    { id: 'frontdesk', name: t('aiEnhancedPms.frontDesk'), component: EnhancedFrontDesk, icon: Users },
    { id: 'folio', name: t('aiEnhancedPms.folioRegistration'), component: FolioManagementPage, icon: CreditCard },
    { id: 'housekeeping', name: t('aiEnhancedPms.aiHousekeeping'), component: AIHousekeepingBoard, icon: ClipboardCheck },
    { id: 'maintenance', name: t('aiEnhancedPms.predictiveMaintenance'), component: PredictiveMaintenanceDashboard, icon: Wrench },
    { id: 'rms', name: t('aiEnhancedPms.aiRevenueManagement'), component: AIRMSDashboard, icon: TrendingUp },
    { id: 'loyalty', name: t('aiEnhancedPms.aiLoyalty'), component: LoyaltyAutoTierManager, icon: Crown }
  ];

  const ActiveComponent = modules.find(m => m.id === activeModule)?.component || EnhancedReservationCalendar;

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Header Area */}
      <div className="px-8 py-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
        <div>
          <h2 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-indigo-500" />
            {t('aiEnhancedPms.title')}
          </h2>
          <p className="text-sm text-slate-500 mt-1">{t('aiEnhancedPms.subtitle')}</p>
        </div>
        <div className="flex items-center gap-4 text-xs font-medium text-slate-500">
          <div className="flex items-center gap-1.5 bg-indigo-50 text-indigo-700 px-3 py-1.5 rounded-full border border-indigo-100">
            <span className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse"></span>
            AI Aktif
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="px-8 pt-4 border-b border-slate-200">
        <div className="flex gap-6 overflow-x-auto no-scrollbar">
          {modules.map(module => {
            const isActive = activeModule === module.id;
            return (
              <button
                key={module.id}
                data-testid={`ai-pms-tab-${module.id}`}
                onClick={() => setActiveModule(module.id)}
                className={`flex items-center gap-2 pb-3 px-1 border-b-2 font-medium text-sm transition-colors whitespace-nowrap ${
                  isActive
                    ? 'border-indigo-600 text-indigo-700'
                    : 'border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300'
                }`}
              >
                <module.icon className={`w-4 h-4 ${isActive ? 'text-indigo-600' : 'text-slate-400'}`} />
                {module.name}
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto p-8 bg-slate-50/30">
        <div className="max-w-7xl mx-auto">
          <ActiveComponent />
        </div>
      </div>
    </div>
  );
};

export default AIEnhancedPMS;
