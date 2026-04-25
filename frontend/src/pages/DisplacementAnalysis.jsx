import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Layout from '@/components/Layout';
import { Target, GitCompare, History, LayoutDashboard } from 'lucide-react';
import MarketOverviewTab from './displacement/MarketOverviewTab';
import AnalysisTab from './displacement/AnalysisTab';
import CompareTab from './displacement/CompareTab';
import HistoryTab from './displacement/HistoryTab';

const TABS = [
  { id: 'overview', icon: LayoutDashboard, labelKey: 'displacement.tabOverview', fallback: 'Market Overview', Component: MarketOverviewTab },
  { id: 'analyze', icon: Target, labelKey: 'displacement.tabAnalyze', fallback: 'Analyze', Component: AnalysisTab },
  { id: 'compare', icon: GitCompare, labelKey: 'displacement.tabCompare', fallback: 'Compare', Component: CompareTab },
  { id: 'history', icon: History, labelKey: 'displacement.tabHistory', fallback: 'History', Component: HistoryTab },
];

const DisplacementAnalysis = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('overview');
  const Active = (TABS.find(t => t.id === activeTab) || TABS[0]).Component;

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="displacement_analysis">
      <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{t('displacement.title', 'Displacement Analysis')}</h1>
            <p className="text-sm text-gray-500 mt-1">{t('displacement.subtitle', 'Evaluate group bookings against transient displacement to maximize revenue')}</p>
          </div>
        </div>

        <div className="flex gap-1 border-b">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {t(tab.labelKey, tab.fallback)}
            </button>
          ))}
        </div>

        <Active user={user} tenant={tenant} onLogout={onLogout} />
      </div>
    </Layout>
  );
};

export default DisplacementAnalysis;
