import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';

const formatDate = (d) => d.toISOString().slice(0, 10);

const FnBOutletDashboard = () => {
  const [outlets, setOutlets] = useState([]);
  const [selectedOutlet, setSelectedOutlet] = useState('all');
  const [startDate, setStartDate] = useState(() => {
    const now = new Date();
    const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
    return formatDate(startOfMonth);
  });
  const [endDate, setEndDate] = useState(() => formatDate(new Date()));
  const [loading, setLoading] = useState(false);
  const [menuData, setMenuData] = useState(null);

  const loadOutlets = async () => {
    try {
      const res = await axios.get('/pos/outlets');
      setOutlets(res.data?.outlets || []);
    } catch (err) {
      console.error('Failed to load outlets', err);
      toast.error('Failed to load outlets');
    }
  };

  const loadSales = async () => {
    setLoading(true);
    try {
      const res = await axios.get('/pos/menu-sales-breakdown', {
        params: {
          outlet_id: selectedOutlet === 'all' ? undefined : selectedOutlet,
          start_date: startDate,
          end_date: endDate,
        },
      });
      setMenuData(res.data);
    } catch (err) {
      console.error('Failed to load F&B sales', err);
      toast.error('Failed to load F&B sales');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadOutlets();
    loadSales();
  }, []);

  const summary = menuData?.summary;
  const byOutlet = menuData?.by_outlet || [];
  const topItems = useMemo(() => (menuData?.menu_items || []).slice(0, 15), [menuData]);
  const byCategory = menuData?.by_category || [];

  return (
    <div className="space-y-6">
      {/* Filters */}
      <Card>
        <CardHeader>
          <CardTitle>Outlet Sales Overview</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-5 gap-4 items-end">
            <div>
              <Label className="text-xs text-gray-600">Date From</Label>
              <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </div>
            <div>
              <Label className="text-xs text-gray-600">Date To</Label>
              <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
            </div>
            <div>
              <Label className="text-xs text-gray-600">Outlet</Label>
              <Select value={selectedOutlet} onValueChange={setSelectedOutlet}>
                <SelectTrigger>
                  <SelectValue placeholder="All outlets" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All outlets</SelectItem>
                  {outlets.map((o) => (
                    <SelectItem key={o.id} value={o.id}>
                      {o.outlet_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end justify-end col-span-2">
              <Button size="sm" onClick={loadSales} disabled={loading}>
                {loading ? 'Loading…' : 'Refresh'}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-4 gap-4 text-sm">
          <Card>
            <CardContent className="py-3">
              <div className="text-xs text-gray-500">Total Revenue</div>
              <div className="text-xl font-bold text-blue-600">${summary.total_revenue.toFixed(2)}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-3">
              <div className="text-xs text-gray-500">Total Cost</div>
              <div className="text-xl font-bold text-rose-600">${summary.total_cost.toFixed(2)}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-3">
              <div className="text-xs text-gray-500">Gross Profit</div>
              <div className="text-xl font-bold text-emerald-600">${summary.gross_profit.toFixed(2)}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-3">
              <div className="text-xs text-gray-500">Profit Margin</div>
              <div className="text-xl font-bold">{summary.profit_margin.toFixed(1)}%</div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Outlet breakdown (when All selected) */}
      {selectedOutlet === 'all' && byOutlet.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Revenue by Outlet</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-xs">
              {byOutlet.map((o) => (
                <div key={o.outlet_name} className="flex items-center justify-between gap-4">
                  <div className="w-32 truncate font-medium">{o.outlet_name}</div>
                  <div className="flex-1 h-2 bg-gray-200 rounded">
                    <div
                      className="h-2 bg-indigo-500 rounded"
                      style={{
                        width: `${
                          summary && summary.total_revenue > 0
                            ? Math.min(100, (o.revenue / summary.total_revenue) * 100)
                            : 0
                        }%`,
                      }}
                    />
                  </div>
                  <div className="w-24 text-right font-semibold">${o.revenue.toFixed(2)}</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Category breakdown */}
      {byCategory.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Revenue by Category</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-xs">
              {byCategory.map((c) => (
                <div key={c.category} className="flex items-center justify-between gap-4">
                  <div className="w-32 truncate font-medium">{c.category}</div>
                  <div className="flex-1 h-2 bg-gray-200 rounded">
                    <div
                      className="h-2 bg-emerald-500 rounded"
                      style={{
                        width: `${
                          summary && summary.total_revenue > 0
                            ? Math.min(100, (c.revenue / summary.total_revenue) * 100)
                            : 0
                        }%`,
                      }}
                    />
                  </div>
                  <div className="w-24 text-right font-semibold">${c.revenue.toFixed(2)}</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Top items */}
      <Card>
        <CardHeader>
          <CardTitle>Top Selling Menu Items</CardTitle>
        </CardHeader>
        <CardContent>
          {loading && !menuData ? (
            <div className="space-y-2">
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-6 w-full" />
            </div>
          ) : !topItems.length ? (
            <div className="text-sm text-gray-500 py-4 text-center">No sales data for selected period.</div>
          ) : (
            <div className="space-y-1 text-xs">
              <div className="grid grid-cols-5 font-semibold text-gray-600 border-b pb-1 mb-1">
                <div>Item</div>
                <div className="text-right">Qty</div>
                <div className="text-right">Revenue</div>
                <div className="text-right">Cost</div>
                <div className="text-right">Gross Profit</div>
              </div>
              {topItems.map((item) => (
                <div key={item.item_name} className="grid grid-cols-5 py-1 border-b last:border-b-0">
                  <div className="truncate font-medium">{item.item_name}</div>
                  <div className="text-right">{item.quantity_sold}</div>
                  <div className="text-right">${item.total_revenue.toFixed(2)}</div>
                  <div className="text-right">${item.total_cost.toFixed(2)}</div>
                  <div className="text-right">${item.gross_profit.toFixed(2)}</div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default FnBOutletDashboard;
