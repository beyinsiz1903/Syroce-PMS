import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';
import { ArrowRightLeft, RefreshCw, ArrowLeft } from 'lucide-react';

import { PageHeader } from '@/components/ui/page-header';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

const DEFAULT_LIMIT = 200;

function formatDateTime(value) {
  if (!value) return '—';
  try {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return value;
    return d.toLocaleString();
  } catch {
    return value;
  }
}

function formatQty(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return n.toLocaleString(undefined, { maximumFractionDigits: 3 });
}

export default function InventoryTransferHistory() {
  const navigate = useNavigate();
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [loading, setLoading] = useState(false);
  const [transfers, setTransfers] = useState([]);
  const [count, setCount] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: DEFAULT_LIMIT };
      if (startDate) params.start_date = new Date(startDate).toISOString();
      if (endDate) {
        const end = new Date(endDate);
        end.setHours(23, 59, 59, 999);
        params.end_date = end.toISOString();
      }
      const r = await axios.get('/accounting/inventory/transfers', { params });
      setTransfers(r.data?.transfers || []);
      setCount(r.data?.count || 0);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Transfer geçmişi yüklenemedi');
      setTransfers([]);
      setCount(0);
    } finally {
      setLoading(false);
    }
  }, [startDate, endDate]);

  useEffect(() => {
    load();
  }, [load]);

  const clearFilters = () => {
    setStartDate('');
    setEndDate('');
  };

  return (
    <div className="p-4 lg:p-6 space-y-4" data-testid="inventory-transfer-history-page">
      <PageHeader
        icon={ArrowRightLeft}
        title="Stok Transfer Geçmişi"
        subtitle="Depo/lokasyon arası stok transferlerinin mutabakat raporu"
        actions={
          <>
            <Button
              variant="outline"
              onClick={() => navigate('/hotel-inventory')}
              data-testid="back-to-inventory"
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              Stok Yönetimine Dön
            </Button>
            <Button variant="outline" onClick={load} data-testid="refresh-transfers">
              <RefreshCw className="w-4 h-4 mr-2" />
              Yenile
            </Button>
          </>
        }
      />

      <Card>
        <CardContent className="p-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="transfer-start-date">Başlangıç</Label>
              <Input
                id="transfer-start-date"
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                data-testid="filter-start-date"
                className="w-44"
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="transfer-end-date">Bitiş</Label>
              <Input
                id="transfer-end-date"
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                data-testid="filter-end-date"
                className="w-44"
              />
            </div>
            <Button
              variant="outline"
              onClick={clearFilters}
              disabled={!startDate && !endDate}
              data-testid="clear-filters"
            >
              Temizle
            </Button>
            <div className="ml-auto text-sm text-slate-500" data-testid="transfer-count">
              {count} transfer
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="transfer-history-table">
              <thead className="bg-slate-50 text-slate-600">
                <tr>
                  <th className="text-left p-3 font-medium">Tarih</th>
                  <th className="text-left p-3 font-medium">Kaynak</th>
                  <th className="text-left p-3 font-medium">Hedef</th>
                  <th className="text-right p-3 font-medium">Miktar</th>
                  <th className="text-left p-3 font-medium">Referans</th>
                  <th className="text-left p-3 font-medium">Kullanıcı</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={6} className="p-6 text-center text-slate-500">
                      <RefreshCw className="w-5 h-5 animate-spin inline mr-2" />
                      Yükleniyor...
                    </td>
                  </tr>
                ) : transfers.length === 0 ? (
                  <tr>
                    <td
                      colSpan={6}
                      className="p-6 text-center text-slate-500"
                      data-testid="no-transfers"
                    >
                      Seçili aralıkta transfer kaydı yok.
                    </td>
                  </tr>
                ) : (
                  transfers.map((t) => (
                    <tr
                      key={t.transfer_id}
                      className="border-t border-slate-100 hover:bg-slate-50"
                      data-testid={`transfer-row-${t.transfer_id}`}
                    >
                      <td className="p-3 whitespace-nowrap">{formatDateTime(t.created_at)}</td>
                      <td className="p-3">{t.source_item_name || t.source_item_id || '—'}</td>
                      <td className="p-3">
                        {t.destination_item_name || t.destination_item_id || '—'}
                      </td>
                      <td className="p-3 text-right tabular-nums">{formatQty(t.quantity)}</td>
                      <td className="p-3 text-slate-600">{t.reference || '—'}</td>
                      <td className="p-3 text-slate-600">{t.created_by || '—'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
