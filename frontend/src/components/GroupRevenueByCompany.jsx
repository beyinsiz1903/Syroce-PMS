import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';

const GroupRevenueByCompany = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [groups, setGroups] = useState([]);
  const [companyFilter, setCompanyFilter] = useState('all');
  const [startDate, setStartDate] = useState(() => {
    // Default to year-to-date for broader view
    const now = new Date();
    const startOfYear = new Date(now.getFullYear(), 0, 1);
    return startOfYear.toISOString().slice(0, 10);
  });
  const [endDate, setEndDate] = useState(() => new Date().toISOString().slice(0, 10));

  const loadGroups = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {
        start_date: startDate,
        end_date: endDate,
        min_rooms: 1,
      };
      const res = await axios.get('/deluxe/group-bookings', { params });
      setGroups(res.data?.groups || []);
    } catch (err) {
      console.error('Failed to load group bookings', err);
      setError(err.response?.data?.detail || 'Failed to load group bookings');
      toast.error('Failed to load group bookings');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadGroups();
  }, []);

  const companies = useMemo(() => {
    const unique = new Map();
    for (const g of groups) {
      if (!unique.has(g.company_id)) {
        unique.set(g.company_id, g.company_name || 'Unknown');
      }
    }
    return Array.from(unique.entries()).map(([id, name]) => ({ id, name }));
  }, [groups]);

  const aggregated = useMemo(() => {
    const map = new Map();
    for (const g of groups) {
      if (companyFilter !== 'all' && g.company_id !== companyFilter) continue;
      if (!map.has(g.company_id)) {
        map.set(g.company_id, {
          company_id: g.company_id,
          company_name: g.company_name || 'Unknown',
          room_count: 0,
          total_revenue: 0,
          group_count: 0,
        });
      }
      const acc = map.get(g.company_id);
      acc.room_count += g.room_count || 0;
      acc.total_revenue += g.total_revenue || 0;
      acc.group_count += 1;
    }
    return Array.from(map.values()).sort((a, b) => b.total_revenue - a.total_revenue);
  }, [groups, companyFilter]);

  const totalSummary = useMemo(() => {
    const total_rooms = aggregated.reduce((s, c) => s + c.room_count, 0);
    const total_revenue = aggregated.reduce((s, c) => s + c.total_revenue, 0);
    const total_groups = aggregated.reduce((s, c) => s + c.group_count, 0);
    return {
      total_rooms,
      total_revenue,
      total_groups,
    };
  }, [aggregated]);

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="grid grid-cols-4 gap-3 mb-2">
        <div>
          <Label className="text-xs text-gray-600">Start Date</Label>
          <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
        </div>
        <div>
          <Label className="text-xs text-gray-600">End Date</Label>
          <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
        </div>
        <div>
          <Label className="text-xs text-gray-600">Company</Label>
          <Select value={companyFilter} onValueChange={setCompanyFilter}>
            <SelectTrigger>
              <SelectValue placeholder="All companies" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              {companies.map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-end justify-end">
          <Button size="sm" onClick={loadGroups} disabled={loading}>
            {loading ? 'Loading…' : 'Refresh'}
          </Button>
        </div>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-4 mb-2 text-sm">
        <Card>
          <CardContent className="py-3">
            <div className="text-xs text-gray-500">Total Group Companies</div>
            <div className="text-xl font-bold">{aggregated.length}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3">
            <div className="text-xs text-gray-500">Total Group Revenue</div>
            <div className="text-xl font-bold text-blue-600">
              ${totalSummary.total_revenue.toFixed(2)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3">
            <div className="text-xs text-gray-500">Total Group Room Nights</div>
            <div className="text-xl font-bold text-green-600">{totalSummary.total_rooms}</div>
          </CardContent>
        </Card>
      </div>

      {/* Table */}
      {loading ? (
        <div className="space-y-2">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      ) : aggregated.length === 0 ? (
        <div className="text-sm text-gray-500 py-4 text-center">No group bookings found for selected period.</div>
      ) : (
        <div className="border rounded-md overflow-hidden">
          <div className="grid grid-cols-5 bg-gray-50 text-xs font-semibold text-gray-600 border-b">
            <div className="px-3 py-2">Company</div>
            <div className="px-3 py-2 text-right">Group Count</div>
            <div className="px-3 py-2 text-right">Room Nights</div>
            <div className="px-3 py-2 text-right">Total Revenue</div>
            <div className="px-3 py-2 text-right">Avg Rate</div>
          </div>
          {aggregated.map((row) => {
            const avgRate = row.room_count > 0 ? row.total_revenue / row.room_count : 0;
            return (
              <div
                key={row.company_id}
                className="grid grid-cols-5 text-xs border-b last:border-b-0 hover:bg-blue-50/40 cursor-pointer"
                onClick={() => {
                  // Drill-down: set pickup target to a representative date within the period
                  try {
                    const today = new Date();
                    const target = endDate || today.toISOString().slice(0, 10);
                    localStorage.setItem('pickup_target_date', target);
                    localStorage.setItem('pickup_company_id', row.company_id);
                  } catch (e) {
                    console.warn('Unable to persist pickup drilldown context', e);
                  }
                  window.open('/pms?tab=reports', '_blank');
                }}
              >
                <div className="px-3 py-2 font-medium truncate">{row.company_name}</div>
                <div className="px-3 py-2 text-right">{row.group_count}</div>
                <div className="px-3 py-2 text-right">{row.room_count}</div>
                <div className="px-3 py-2 text-right">${row.total_revenue.toFixed(2)}</div>
                <div className="px-3 py-2 text-right">${avgRate.toFixed(2)}</div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default GroupRevenueByCompany;
