import { useEffect, useState } from 'react';
import axios from 'axios';

export const localIsoDate = () => {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
};

/**
 * PMS ekranlarının varsayılan tarihini sunucunun operasyon tarihinden alır.
 * Tarayıcının UTC günü ile night-audit sonrası iş günü birbirinden farklı olabilir.
 */
export const useBusinessDate = () => {
  const [businessDate, setBusinessDate] = useState(localIsoDate);

  useEffect(() => {
    let active = true;
    axios.get('/night-audit/business-date')
      .then(({ data }) => {
        const date = String(data?.business_date || '').slice(0, 10);
        if (active && /^\d{4}-\d{2}-\d{2}$/.test(date)) setBusinessDate(date);
      })
      // The local calendar day is a safe fallback if Night Audit is unavailable.
      .catch(() => {});
    return () => { active = false; };
  }, []);

  return businessDate;
};
