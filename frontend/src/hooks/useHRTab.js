import { useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

const TABS = new Set(['attendance', 'payroll', 'leave', 'performance', 'overtime', 'recruitment']);

export function useHRTab() {
  const location = useLocation();
  const navigate = useNavigate();
  const requested = new URLSearchParams(location.search).get('tab');
  const activeTab = TABS.has(requested) ? requested : 'attendance';
  const setActiveTab = useCallback((tab) => {
    if (!TABS.has(tab)) return;
    const params = new URLSearchParams(location.search);
    params.set('tab', tab);
    params.delete('id'); // Do not carry a leave record into another module.
    navigate({ pathname: location.pathname, search: params.toString() });
  }, [location.pathname, location.search, navigate]);
  return [activeTab, setActiveTab];
}
