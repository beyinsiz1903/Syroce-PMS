import React, { createContext, useContext, useState, useCallback, useMemo, useEffect } from 'react';
import axios from 'axios';

const EntitlementContext = createContext(null);

export const useEntitlements = () => {
  const context = useContext(EntitlementContext);
  if (!context) {
    throw new Error('useEntitlements must be used within an EntitlementProvider');
  }
  return context;
};

// An operator must only see a module explicitly granted to the current hotel.
// Super-admin access is intentionally kept separate: it is needed for platform
// administration, but must not be used to describe a hotel's purchased setup.

export const EntitlementProvider = ({ children, currentTenantId, isSuperAdmin }) => {
  const [state, setState] = useState({
    tenantId: null,
    modules: null,
    entitlements: null,
    loading: true,
    loaded: false,
    error: null,
  });

  const clearEntitlements = useCallback(() => {
    setState({
      tenantId: null,
      modules: null,
      entitlements: null,
      loading: false,
      loaded: false,
      error: null,
    });
    localStorage.removeItem("entitlements");
  }, []);

  const fetchEntitlements = useCallback(async (tenantIdToFetch) => {
    if (!tenantIdToFetch) {
      clearEntitlements();
      return;
    }
    
    setState(prev => ({ ...prev, loading: true, error: null }));
    try {
      const res = await axios.get("/subscription/current");
      const tenantModules = res.data?.modules || {};
      const tenantEntitlements = res.data?.entitlements || {};
      
      const newState = {
        tenantId: tenantIdToFetch,
        modules: tenantModules,
        entitlements: tenantEntitlements,
        loading: false,
        loaded: true,
        error: null,
      };
      
      setState(newState);
      localStorage.setItem("entitlements", JSON.stringify({
        tenantId: tenantIdToFetch,
        modules: tenantModules,
        entitlements: tenantEntitlements
      }));
    } catch (err) {
      setState(prev => ({
        ...prev,
        loading: false,
        loaded: false,
        error: err?.response?.data?.detail || "Failed to load entitlements"
      }));
    }
  }, [clearEntitlements]);

  // Load from cache or fetch on mount/tenant change
  useEffect(() => {
    if (!currentTenantId) {
      clearEntitlements();
      return;
    }

    const storedStr = localStorage.getItem("entitlements");
    if (storedStr) {
      try {
        const stored = JSON.parse(storedStr);
        if (stored.tenantId === currentTenantId) {
          setState(prev => ({
            ...prev,
            modules: stored.modules || {},
            entitlements: stored.entitlements || {},
            loading: true, // Keep loading true until server confirms for strict modules
            loaded: false,
            tenantId: currentTenantId,
            error: null
          }));
          // Optimistically refresh in background
          fetchEntitlements(currentTenantId);
          return;
        }
      } catch (e) {
        // ignore parse error
      }
    }
    
    // If no cache or mismatch, fetch immediately
    fetchEntitlements(currentTenantId);
  }, [currentTenantId, fetchEntitlements, clearEntitlements]);

  const isStateValid = state.loaded && !state.error && state.tenantId === currentTenantId;

  const hasTenantModule = useCallback((moduleKey) => {
    if (!moduleKey) return true;
    if (state.loading) return false;
    if (!isStateValid) return false;
    return state.modules?.[moduleKey] === true || Boolean(state.entitlements?.[moduleKey]);
  }, [state.loading, isStateValid, state.modules, state.entitlements]);

  const hasModule = useCallback((moduleKey) => {
    if (!moduleKey || isSuperAdmin) return true;
    return hasTenantModule(moduleKey);
  }, [hasTenantModule, isSuperAdmin]);

  const hasFeature = useCallback((moduleKey, featureKey) => {
    if (!moduleKey || !featureKey) return true;
    if (isSuperAdmin) return true;
    if (state.loading) return false;
    if (!isStateValid) return false;
    
    const moduleEntitlements = state.entitlements?.[moduleKey];
    if (!moduleEntitlements) return false;
    
    const features = moduleEntitlements.features;
    return Array.isArray(features) ? features.includes(featureKey) : false;
  }, [isSuperAdmin, state.loading, isStateValid, state.entitlements]);

  const getLimit = useCallback((moduleKey, limitKey) => {
    if (!moduleKey || !limitKey) return 0;
    if (state.loading || !isStateValid) return 0;
    
    const moduleEntitlements = state.entitlements?.[moduleKey];
    if (!moduleEntitlements || !moduleEntitlements.limits) return 0;
    
    return moduleEntitlements.limits[limitKey] ?? 0;
  }, [state.loading, isStateValid, state.entitlements]);

  const value = useMemo(() => ({
    modules: state.modules,
    entitlements: state.entitlements,
    isSuperAdmin,
    loading: state.loading,
    loaded: state.loaded,
    error: state.error, tenantId: state.tenantId,
    refresh: () => fetchEntitlements(currentTenantId),
    clearEntitlements,
    hasModule,
    hasTenantModule,
    hasFeature,
    getLimit
  }), [
    state.modules, state.entitlements, isSuperAdmin, state.loading,
    state.loaded, state.error, state.tenantId, currentTenantId, fetchEntitlements,
    clearEntitlements, hasModule, hasTenantModule, hasFeature, getLimit
  ]);

  return (
    <EntitlementContext.Provider value={value}>
      {children}
    </EntitlementContext.Provider>
  );
};
