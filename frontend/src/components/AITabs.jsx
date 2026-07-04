import React from 'react';
import { useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { Activity, BarChart3, Cpu } from 'lucide-react';

const AITabs = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const tabs = [
    {
      id: 'predictive-analytics',
      label: 'Tahmine Dayalı Analiz',
      icon: Activity,
      path: '/predictive-analytics',
    },
    {
      id: 'dynamic-pricing',
      label: 'Dinamik Fiyatlandırma',
      icon: BarChart3,
      path: '/dynamic-pricing',
    },
    {
      id: 'revenue-autopilot',
      label: 'Revenue Autopilot',
      icon: Cpu,
      path: '/revenue-autopilot',
    },
  ];

  const [searchParams] = useSearchParams();

  const handleNavigate = (tab) => {
    // Check if we are inside the AI Hub context (either by path or query param)
    if (location.pathname.includes('/app/ai') || searchParams.has('module')) {
      navigate(`${location.pathname}?module=${tab.id}`);
    } else {
      navigate(tab.path);
    }
  };

  // Helper to match active tab
  const isActive = (tab) => {
    if (location.pathname.includes('/app/ai') || searchParams.has('module')) {
      return searchParams.get('module') === tab.id;
    }
    return location.pathname.includes(tab.path);
  };

  return (
    <div className="flex flex-wrap items-center gap-2 mb-6 p-1 bg-slate-100 rounded-lg w-fit">
      {tabs.map((tab) => {
        const active = isActive(tab);
        const Icon = tab.icon;
        return (
          <button
            key={tab.id}
            onClick={() => handleNavigate(tab)}
            className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${
              active 
                ? 'bg-white text-indigo-700 shadow-sm ring-1 ring-slate-200/50' 
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/50'
            }`}
          >
            <Icon className={`w-4 h-4 ${active ? 'text-indigo-600' : 'text-slate-500'}`} />
            {tab.label}
          </button>
        );
      })}
    </div>
  );
};

export default AITabs;
