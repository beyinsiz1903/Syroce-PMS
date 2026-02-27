import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
import { useTranslation } from 'react-i18next';
  Activity, Database, Zap, Server, Clock, 
  TrendingUp, TrendingDown, RefreshCw, CheckCircle, XCircle
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const PerformanceMonitorDashboard = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [webVitals, setWebVitals] = useState({
    FCP: 0,
    LCP: 0,
    FID: 0,
    CLS: 0,
    TTFB: 0,
  });

  // Fetch optimization health
  const { data: health, isLoading: healthLoading, refetch: refetchHealth } = useQuery({
    queryKey: ['optimization', 'health'],
    queryFn: () => axios.get('/optimization/health').then(res => res.data),
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  // Fetch cache stats
  const { data: cacheStats, refetch: refetchCache } = useQuery({
    queryKey: ['optimization', 'cache-stats'],
    queryFn: () => axios.get('/optimization/cache/stats').then(res => res.data),
    refetchInterval: 30000,
  });

  // Fetch view stats
  const { data: viewStats, refetch: refetchViews } = useQuery({
    queryKey: ['optimization', 'view-stats'],
    queryFn: () => axios.get('/optimization/views/stats').then(res => res.data),
    refetchInterval: 30000,
  });

  // Fetch archive stats
  const { data: archiveStats, refetch: refetchArchive } = useQuery({
    queryKey: ['optimization', 'archive-stats'],
    queryFn: () => axios.get('/optimization/archive/stats').then(res => res.data),
    refetchInterval: 60000, // Every minute
  });

  // Measure Web Vitals
  useEffect(() => {
    if ('PerformanceObserver' in window) {
      try {
        // First Contentful Paint
        const fcpObserver = new PerformanceObserver((list) => {
          const entries = list.getEntries();
          entries.forEach((entry) => {
            if (entry.name === 'first-contentful-paint') {
              setWebVitals(prev => ({ ...prev, FCP: entry.startTime }));
            }
          });
        });
        fcpObserver.observe({ entryTypes: ['paint'] });

        // Largest Contentful Paint
        const lcpObserver = new PerformanceObserver((list) => {
          const entries = list.getEntries();
          const lastEntry = entries[entries.length - 1];
          setWebVitals(prev => ({ ...prev, LCP: lastEntry.startTime }));
        });
        lcpObserver.observe({ entryTypes: ['largest-contentful-paint'] });

        // First Input Delay
        const fidObserver = new PerformanceObserver((list) => {
          const entries = list.getEntries();
          entries.forEach((entry) => {
            setWebVitals(prev => ({ ...prev, FID: entry.processingStart - entry.startTime }));
          });
        });
        fidObserver.observe({ entryTypes: ['first-input'] });

        // Cumulative Layout Shift
        const clsObserver = new PerformanceObserver((list) => {
          let clsValue = 0;
          list.getEntries().forEach((entry) => {
            if (!entry.hadRecentInput) {
              clsValue += entry.value;
            }
          });
          setWebVitals(prev => ({ ...prev, CLS: clsValue }));
        });
        clsObserver.observe({ entryTypes: ['layout-shift'] });

        // Time to First Byte
        const navigation = performance.getEntriesByType('navigation')[0];
        if (navigation) {
          setWebVitals(prev => ({ 
            ...prev, 
            TTFB: navigation.responseStart - navigation.requestStart 
          }));
        }
      } catch (error) {
        console.warn('Performance monitoring not fully supported:', error);
      }
    }
  }, []);

  const getScoreColor = (metric, value) => {
    const thresholds = {
      FCP: { good: 1800, poor: 3000 },
      LCP: { good: 2500, poor: 4000 },
      FID: { good: 100, poor: 300 },
      CLS: { good: 0.1, poor: 0.25 },
      TTFB: { good: 200, poor: 600 },
    };

    const threshold = thresholds[metric];
    if (value <= threshold.good) return 'text-green-600 bg-green-50';
    if (value <= threshold.poor) return 'text-yellow-600 bg-yellow-50';
    return 'text-red-600 bg-red-50';
  };

  const getScoreLabel = (metric, value) => {
    const thresholds = {
      FCP: { good: 1800, poor: 3000 },
      LCP: { good: 2500, poor: 4000 },
      FID: { good: 100, poor: 300 },
      CLS: { good: 0.1, poor: 0.25 },
      TTFB: { good: 200, poor: 600 },
    };

    const threshold = thresholds[metric];
    if (value <= threshold.good) return 'Good';
    if (value <= threshold.poor) return 'Needs Improvement';
    return 'Poor';
  };

  const refreshAll = () => {
    refetchHealth();
    refetchCache();
    refetchViews();
    refetchArchive();
  };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="system-monitor">
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">{t('common.status')}</h1>
            <p className="text-gray-600">Real-time optimization system metrics</p>
          </div>
          <Button onClick={refreshAll} variant="outline">
            <RefreshCw className="w-4 h-4 mr-2" />
            Refresh All
          </Button>
        </div>

        {/* System Health */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="w-5 h-5" />
              Optimization System Health
            </CardTitle>
          </CardHeader>
          <CardContent>
            {healthLoading ? (
              <div className="animate-pulse space-y-2">
                <div className="h-4 bg-gray-200 rounded w-3/4"></div>
                <div className="h-4 bg-gray-200 rounded w-1/2"></div>
              </div>
            ) : health ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="flex items-center gap-3">
                  {health.archival ? (
                    <CheckCircle className="w-5 h-5 text-green-600" />
                  ) : (
                    <XCircle className="w-5 h-5 text-red-600" />
                  )}
                  <div>
                    <div className="font-medium">Data Archival</div>
                    <div className="text-sm text-gray-600">
                      {health.archival ? 'Active' : 'Inactive'}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  {health.materialized_views ? (
                    <CheckCircle className="w-5 h-5 text-green-600" />
                  ) : (
                    <XCircle className="w-5 h-5 text-red-600" />
                  )}
                  <div>
                    <div className="font-medium">Materialized Views</div>
                    <div className="text-sm text-gray-600">
                      {viewStats?.total_views || 0} views
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  {health.cache ? (
                    <CheckCircle className="w-5 h-5 text-green-600" />
                  ) : (
                    <XCircle className="w-5 h-5 text-red-600" />
                  )}
                  <div>
                    <div className="font-medium">Cache Manager</div>
                    <div className="text-sm text-gray-600">
                      {cacheStats?.total_keys || 0} keys
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  {health.cache_warmer ? (
                    <CheckCircle className="w-5 h-5 text-green-600" />
                  ) : (
                    <XCircle className="w-5 h-5 text-red-600" />
                  )}
                  <div>
                    <div className="font-medium">Cache Warmer</div>
                    <div className="text-sm text-gray-600">
                      {health.cache_warmer ? 'Active' : 'Inactive'}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center text-gray-500 py-4">
                Unable to fetch health status
              </div>
            )}
          </CardContent>
        </Card>

        {/* Web Vitals */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="w-5 h-5" />
              Core Web Vitals
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
              <div className={`p-4 rounded-lg ${getScoreColor('FCP', webVitals.FCP)}`}>
                <div className="text-sm font-medium mb-1">FCP</div>
                <div className="text-2xl font-bold">{webVitals.FCP.toFixed(0)}ms</div>
                <div className="text-xs mt-1">{getScoreLabel('FCP', webVitals.FCP)}</div>
              </div>

              <div className={`p-4 rounded-lg ${getScoreColor('LCP', webVitals.LCP)}`}>
                <div className="text-sm font-medium mb-1">LCP</div>
                <div className="text-2xl font-bold">{webVitals.LCP.toFixed(0)}ms</div>
                <div className="text-xs mt-1">{getScoreLabel('LCP', webVitals.LCP)}</div>
              </div>

              <div className={`p-4 rounded-lg ${getScoreColor('FID', webVitals.FID)}`}>
                <div className="text-sm font-medium mb-1">FID</div>
                <div className="text-2xl font-bold">{webVitals.FID.toFixed(0)}ms</div>
                <div className="text-xs mt-1">{getScoreLabel('FID', webVitals.FID)}</div>
              </div>

              <div className={`p-4 rounded-lg ${getScoreColor('CLS', webVitals.CLS)}`}>
                <div className="text-sm font-medium mb-1">CLS</div>
                <div className="text-2xl font-bold">{webVitals.CLS.toFixed(3)}</div>
                <div className="text-xs mt-1">{getScoreLabel('CLS', webVitals.CLS)}</div>
              </div>

              <div className={`p-4 rounded-lg ${getScoreColor('TTFB', webVitals.TTFB)}`}>
                <div className="text-sm font-medium mb-1">TTFB</div>
                <div className="text-2xl font-bold">{webVitals.TTFB.toFixed(0)}ms</div>
                <div className="text-xs mt-1">{getScoreLabel('TTFB', webVitals.TTFB)}</div>
              </div>
            </div>
            <div className="mt-4 text-xs text-gray-600">
              <strong>FCP</strong>: First Contentful Paint | 
              <strong> LCP</strong>: Largest Contentful Paint | 
              <strong> FID</strong>: First Input Delay | 
              <strong> CLS</strong>: Cumulative Layout Shift | 
              <strong> TTFB</strong>: Time to First Byte
            </div>
          </CardContent>
        </Card>

        {/* Cache Statistics */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Database className="w-5 h-5" />
                Cache Statistics
              </CardTitle>
            </CardHeader>
            <CardContent>
              {cacheStats ? (
                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <span className="text-gray-600">Total Keys</span>
                    <span className="font-bold">{cacheStats.total_keys}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-gray-600">Memory Used</span>
                    <span className="font-bold">{cacheStats.memory_used}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-gray-600">Connected Clients</span>
                    <span className="font-bold">{cacheStats.connected_clients}</span>
                  </div>

                  {cacheStats.layer_distribution && (
                    <div className="mt-4">
                      <div className="text-sm font-medium mb-2">Layer Distribution</div>
                      <div className="space-y-2">
                        <div className="flex justify-between">
                          <span className="text-sm text-gray-600">L1 (1 min)</span>
                          <Badge>{cacheStats.layer_distribution.L1} keys</Badge>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-sm text-gray-600">L2 (5 min)</span>
                          <Badge>{cacheStats.layer_distribution.L2} keys</Badge>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-sm text-gray-600">L3 (1 hour)</span>
                          <Badge>{cacheStats.layer_distribution.L3} keys</Badge>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center text-gray-500 py-4">
                  Cache stats unavailable
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Server className="w-5 h-5" />
                Materialized Views
              </CardTitle>
            </CardHeader>
            <CardContent>
              {viewStats?.views ? (
                <div className="space-y-4">
                  {viewStats.views.map((view, idx) => (
                    <div key={idx} className="border-b last:border-b-0 pb-3 last:pb-0">
                      <div className="flex justify-between items-start mb-2">
                        <span className="font-medium">{view.view_name}</span>
                        <Badge variant="outline">{view.view_type}</Badge>
                      </div>
                      <div className="text-sm text-gray-600 space-y-1">
                        <div className="flex justify-between">
                          <span>Age:</span>
                          <span>{view.age_seconds?.toFixed(1)}s</span>
                        </div>
                        <div className="flex justify-between">
                          <span>Refresh Time:</span>
                          <span className="text-green-600 font-medium">
                            {view.refresh_duration_ms?.toFixed(2)}ms
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center text-gray-500 py-4">
                  No materialized views
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Archive Statistics */}
        {archiveStats && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Clock className="w-5 h-5" />
                Data Archival Statistics
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div>
                  <div className="text-sm text-gray-600 mb-1">Active Bookings</div>
                  <div className="text-2xl font-bold">
                    {archiveStats.active_bookings?.toLocaleString() || 0}
                  </div>
                </div>
                <div>
                  <div className="text-sm text-gray-600 mb-1">Archived Bookings</div>
                  <div className="text-2xl font-bold">
                    {archiveStats.archived_bookings?.toLocaleString() || 0}
                  </div>
                </div>
                <div>
                  <div className="text-sm text-gray-600 mb-1">Total Bookings</div>
                  <div className="text-2xl font-bold">
                    {archiveStats.total_bookings?.toLocaleString() || 0}
                  </div>
                </div>
                <div>
                  <div className="text-sm text-gray-600 mb-1">Archive Percentage</div>
                  <div className="text-2xl font-bold">
                    {archiveStats.archive_percentage?.toFixed(1) || 0}%
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </Layout>
  );
};

export default PerformanceMonitorDashboard;
