import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';

const PickupPaceReport = () => {
  const [targetDate, setTargetDate] = useState(() => {
    try {
      const stored = localStorage.getItem('pickup_target_date');
      if (stored) return stored;
    } catch (e) {
      console.warn('Unable to read pickup_target_date from localStorage', e);
    }
    return new Date().toISOString().slice(0, 10);
  });
  const [lookbackDays, setLookbackDays] = useState(90);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [groupOnly, setGroupOnly] = useState(() => {
    try {
      const stored = localStorage.getItem('pickup_group_only');
      if (stored != null) return stored === 'true';
    } catch (e) {
      console.warn('Unable to read pickup_group_only from localStorage', e);
    }
    return false;
  });

  const [companyId, setCompanyId] = useState(() => {
    try {
      return localStorage.getItem('pickup_company_id') || null;
    } catch (e) {
      console.warn('Unable to read pickup_company_id from localStorage', e);
      return null;
    }
  });


  const loadPickup = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get('/deluxe/pickup-pace-analytics', {
        params: {
          target_date: targetDate,
          lookback_days: lookbackDays,
          group_only: groupOnly,
          company_id: companyId || undefined,
        },
      });
      setData(res.data);
    } catch (err) {
      console.error('Failed to load pickup pace analytics', err);
      setError(err.response?.data?.detail || 'Failed to load pickup pace analytics');
      toast.error('Failed to load pickup pace analytics');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPickup();
  }, []);

  const summary = data?.summary;
  const chartData = useMemo(() => data?.chart_data || [], [data]);

  // For a quick visual, compute max cumulative bookings and revenue for scaling
  const maxCumBookings = useMemo(
    () => (chartData.length ? Math.max(...chartData.map((d) => d.cumulative_bookings || 0)) : 0),
    [chartData]
  );
  const maxCumRevenue = useMemo(
    () => (chartData.length ? Math.max(...chartData.map((d) => d.cumulative_revenue || 0)) : 0),
    [chartData]
  );

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="grid grid-cols-4 gap-3 mb-2">
        <div>
          <Label className="text-xs text-gray-600">Arrival Date (Target)</Label>
          <Input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
        </div>
        <div>
          <Label className="text-xs text-gray-600">Lookback Window</Label>
          <Select value={String(lookbackDays)} onValueChange={(v) => setLookbackDays(parseInt(v, 10) || 30)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="30">Last 30 days</SelectItem>
      {/* Filters: group-only and company context */}
      <div className="grid grid-cols-4 gap-3 mb-2">
        <div>
          <Label className="text-xs text-gray-600">Filters</Label>
          <div className="flex items-center gap-3 mt-1 text-xs text-gray-700">
            <label className="inline-flex items-center gap-1 cursor-pointer">
              <input
                type="checkbox"
                className="rounded border-gray-300"
                checked={groupOnly}
                onChange={(e) => {
                  const value = e.target.checked;
                  setGroupOnly(value);
                  try {
                    localStorage.setItem('pickup_group_only', String(value));
                  } catch (err) {
                    console.warn('Unable to persist pickup_group_only', err);
                  }
                }}
              />
              <span>Only group bookings</span>
            </label>
            {companyId && (
              <span className="px-2 py-0.5 bg-blue-50 border border-blue-200 rounded-full text-[11px]">
                Filtered by company (Group drill-down)
              </span>
            )}
          </div>
        </div>
      </div>


              <SelectItem value="60">Last 60 days</SelectItem>
              <SelectItem value="90">Last 90 days</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-end justify-end col-span-2">
          <Button size="sm" onClick={loadPickup} disabled={loading}>
            {loading ? 'Loading…' : 'Refresh Pickup'}
          </Button>
        </div>
      </div>

      {/* If no bookings for this arrival date, show helpful message */}
      {!loading && data && summary && summary.total_bookings === 0 && (
        <div className="text-sm text-gray-600 py-3">
          Seçtiğiniz giriş tarihinde henüz rezervasyon yok. Lütfen dolu bir varış tarihi seçin veya
          Reservation Calendar üzerinden dolu bir günü kontrol ederek burada aynı tarihi seçin.
        </div>
      )}

      {/* Summary */}
      {summary && summary.total_bookings > 0 && (
        <div className="grid grid-cols-4 gap-4 mb-2 text-sm">
          <Card>
            <CardContent className="py-3">
              <div className="text-xs text-gray-500">Total Bookings</div>
              <div className="text-xl font-bold">{summary.total_bookings}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-3">
              <div className="text-xs text-gray-500">Total Revenue</div>
              <div className="text-xl font-bold text-blue-600">${summary.total_revenue.toFixed(2)}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-3">
              <div className="text-xs text-gray-500">7-Day Velocity (bkgs/day)</div>
              <div className="text-xl font-bold text-emerald-600">{summary.velocity_7day.toFixed(2)}</div>
            </CardContent>
          </Card>
      {/* Channel breakdown */}
      {summary && summary.total_bookings > 0 && data?.channels_summary && data.channels_summary.length > 0 && (
        <div className="grid grid-cols-3 gap-4 mb-2 text-sm">
          {data.channels_summary.map((ch) => {
            const share = (ch.bookings / summary.total_bookings) * 100;
            return (
              <Card key={ch.channel}>
                <CardContent className="py-3">
                  <div className="text-xs text-gray-500">{ch.channel === 'direct' ? 'Direct' : ch.channel}</div>
                  <div className="text-lg font-semibold">{ch.bookings} bookings</div>
                  <div className="mt-1 h-1.5 bg-gray-200 rounded">
                    <div
                      className="h-1.5 bg-indigo-500 rounded"
                      style={{ width: `${Math.min(100, share)}%` }}
                    />
                  </div>
                  <div className="text-[11px] text-gray-500 mt-1">{share.toFixed(1)}% of pickup</div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}


          <Card>
            <CardContent className="py-3">
              <div className="text-xs text-gray-500">30-Day Velocity (bkgs/day)</div>
              <div className="text-xl font-bold text-amber-600">{summary.velocity_30day.toFixed(2)}</div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Chart/Table */}
      {loading ? (
        <div className="space-y-2">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      ) : error ? (
        <div className="text-sm text-red-600 py-4">{error}</div>
      ) : !chartData.length ? (
        <div className="text-sm text-gray-500 py-4 text-center">No pickup data for this arrival date.</div>
      ) : (
        <div className="border rounded-md overflow-hidden">
          <div className="grid grid-cols-6 bg-gray-50 text-xs font-semibold text-gray-600 border-b">
            <div className="px-3 py-2">Days Before</div>
            <div className="px-3 py-2">Date</div>
            <div className="px-3 py-2 text-right">Daily Pickup</div>
            <div className="px-3 py-2 text-right">Cumulative Bkgs</div>
            <div className="px-3 py-2 text-right">Cumulative Rev</div>
            <div className="px-3 py-2">Visual</div>
          </div>
          {chartData.map((row) => {
            const bookingsRatio = maxCumBookings ? row.cumulative_bookings / maxCumBookings : 0;
            const revenueRatio = maxCumRevenue ? row.cumulative_revenue / maxCumRevenue : 0;
            return (
              <div
                key={row.days_before}
                className="grid grid-cols-6 text-xs border-b last:border-b-0 hover:bg-blue-50/40"
              >
                <div className="px-3 py-2">{row.days_before}</div>
                <div className="px-3 py-2">{row.date}</div>
                <div className="px-3 py-2 text-right">{row.daily_pickup}</div>
                <div className="px-3 py-2 text-right">{row.cumulative_bookings}</div>
                <div className="px-3 py-2 text-right">${row.cumulative_revenue.toFixed(2)}</div>
                <div className="px-3 py-2">
                  <div className="flex items-center gap-1">
                    <div className="h-2 bg-blue-500 rounded" style={{ width: `${bookingsRatio * 80 || 0}%` }} />
                    <div className="h-2 bg-emerald-400 rounded" style={{ width: `${revenueRatio * 80 || 0}%` }} />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default PickupPaceReport;
