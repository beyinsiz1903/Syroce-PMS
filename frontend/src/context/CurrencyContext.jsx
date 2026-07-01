import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import axios from 'axios';
import { currencySymbol, formatAmount, formatCurrency } from '@/lib/currency';

const DEFAULT_CODE = 'TRY';

function getCurrentTenantId() {
  try {
    const u = JSON.parse(localStorage.getItem('user') || 'null');
    return u?.tenant_id || u?.tenantId || 'anon';
  } catch {
    return 'anon';
  }
}

function storageKey() {
  return `tenant_currency:${getCurrentTenantId()}`;
}

function readCachedCurrency() {
  try {
    const raw = localStorage.getItem(storageKey());
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed?.code) return parsed;
  } catch {
    /* ignore */
  }
  return null;
}

function writeCachedCurrency(code, symbol) {
  try {
    localStorage.setItem(storageKey(), JSON.stringify({ code, symbol }));
  } catch {
    /* ignore */
  }
}

function clearAllCurrencyCaches() {
  try {
    const keys = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && (k === 'tenant_currency' || k.startsWith('tenant_currency:'))) keys.push(k);
    }
    keys.forEach(k => localStorage.removeItem(k));
  } catch {
    /* ignore */
  }
}

const CurrencyContext = createContext({
  code: DEFAULT_CODE,
  symbol: currencySymbol(DEFAULT_CODE),
  format: (v, opts) => formatCurrency(v, DEFAULT_CODE, opts),
  amount: (v, opts) => formatAmount(v, DEFAULT_CODE, opts),
  refresh: async () => {},
  setCurrency: () => {},
});

export function CurrencyProvider({ isAuthenticated, children }) {
  const initial = readCachedCurrency();
  const [code, setCode] = useState(initial?.code || DEFAULT_CODE);
  const [symbol, setSymbol] = useState(initial?.symbol || currencySymbol(initial?.code || DEFAULT_CODE));

  const refresh = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const res = await axios.get('/pms/hotel-settings');
      const c = (res?.data?.currency || DEFAULT_CODE).toUpperCase();
      const s = res?.data?.currency_symbol || currencySymbol(c);
      setCode(c);
      setSymbol(s);
      writeCachedCurrency(c, s);
    } catch {
      /* keep cached value */
    }
  }, [isAuthenticated]);

  useEffect(() => {
    if (isAuthenticated) {
      refresh();
    } else {
      setCode(DEFAULT_CODE);
      setSymbol(currencySymbol(DEFAULT_CODE));
      clearAllCurrencyCaches();
    }
  }, [isAuthenticated, refresh]);

  const setCurrency = useCallback((nextCode, nextSymbol) => {
    const c = (nextCode || DEFAULT_CODE).toUpperCase();
    const s = nextSymbol || currencySymbol(c);
    setCode(c);
    setSymbol(s);
    writeCachedCurrency(c, s);
  }, []);

  const value = {
    code,
    symbol,
    format: (v, opts) => formatCurrency(v, code, opts),
    amount: (v, opts) => formatAmount(v, code, opts),
    refresh,
    setCurrency,
  };

  return <CurrencyContext.Provider value={value}>{children}</CurrencyContext.Provider>;
}

export function useCurrency() {
  return useContext(CurrencyContext);
}

export default CurrencyContext;
