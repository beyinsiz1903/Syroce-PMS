import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';

import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Calendar } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const BOOL = (v) => (v ? '✅' : '❌');

const OfficialGuestList = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [date, setDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get('/reports/official-guest-list', {
        params: { date },
      });
      setRows(res.data?.rows || []);
    } catch (err) {
      console.error('Failed to load official guest list', err);
      setError('Resmi müşteri listesi yüklenirken bir hata oluştu');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  const totalGuests = useMemo(
    () => rows.reduce((acc, r) => acc + (r.adults || 0) + (r.children || 0), 0),
    [rows]
  );

  const totalRevenue = useMemo(
    () => rows.reduce((acc, r) => acc + (r.total_amount || 0), 0),
    [rows]
  );

  const handleExportCsv = () => {
    if (!rows.length) return;

    const headers = [
      'booking_id',
      'guest_name',
      'national_id',
      'passport_number',
      'country',
      'city',
      'date_of_birth',
      'room_number',
      'check_in',
      'check_out',
      'adults',
      'children',
      'total_amount',
      'billing_tax_number',
      'billing_address',
      'company_id',
      'market_segment',
    ];

    const lines = [];
    lines.push(headers.join(','));

    rows.forEach((r) => {
      const row = [
        r.booking_id || '',
        (r.guest_name || '').replace(/,/g, ' '),
        r.national_id || '',
        r.passport_number || '',
        (r.country || '').replace(/,/g, ' '),
        (r.city || '').replace(/,/g, ' '),
        r.date_of_birth || '',
        r.room_number || '',
        r.check_in || '',
        r.check_out || '',
        String(r.adults ?? ''),
        String(r.children ?? ''),
        String(r.total_amount ?? ''),
        r.billing_tax_number || '',
        (r.billing_address || '').replace(/,/g, ' '),
        r.company_id || '',
        r.market_segment || '',
      ];
      lines.push(row.join(','));
    });

    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `official_guest_list_${date}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <div className="p-4 md:p-6 space-y-4 max-w-7xl mx-auto">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold">Resmi Müşteri Listesi</h1>
            <p className="text-sm text-gray-600 max-w-2xl">
              Maliye ve diğer resmi denetimler için, seçtiğiniz tarihte otelde konaklayan tüm
              misafirlerin resmi listesini görüntüleyin. Liste, check-in / check-out tarihleri
              ve toplam konaklama tutarını içerir.
            </p>
          </div>
          <div className="flex flex-col md:flex-row gap-2 md:items-center">
            <div className="flex items-center gap-2">
              <Calendar className="w-4 h-4 text-gray-500" />
              <Input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="h-8 text-xs"
              />
            </div>
            <Button size="sm" onClick={loadData} disabled={loading}>
              Listeyi Getir
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleExportCsv}
              disabled={loading || !rows.length}
            >
              CSV Dışa Aktar
            </Button>
          </div>
        </div>

        {error && (
          <div className="p-3 rounded-md bg-red-50 text-red-700 text-sm">{error}</div>
        )}

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center justify-between">
              <span>
                {date} tarihi için konaklayan misafirler
              </span>
              <span className="text-xs text-gray-500 flex gap-4">
                <span>Toplam kayıt: {rows.length}</span>
                <span>Toplam kişi: {totalGuests}</span>
                <span>Toplam tutar: {totalRevenue.toLocaleString('tr-TR', { style: 'currency', currency: 'TRY' })}</span>
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs border-t">
                <thead className="bg-gray-50 border-b">
                  <tr className="text-left whitespace-nowrap">
                    <th className="px-3 py-2 font-medium text-gray-700">Misafir</th>
                    <th className="px-3 py-2 font-medium text-gray-700">TCKN / Pasaport</th>
                    <th className="px-3 py-2 font-medium text-gray-700">Ülke / Şehir</th>
                    <th className="px-3 py-2 font-medium text-gray-700">Oda</th>
                    <th className="px-3 py-2 font-medium text-gray-700">Giriş / Çıkış</th>
                    <th className="px-3 py-2 font-medium text-gray-700">Kişi Sayısı</th>
                    <th className="px-3 py-2 font-medium text-gray-700">Toplam Tutar</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.booking_id} className="border-b hover:bg-gray-50/60">
                      <td className="px-3 py-2">
                        <div className="flex flex-col">
                          <span className="font-medium text-gray-800">{r.guest_name || 'Misafir'}</span>
                          <span className="text-[10px] text-gray-400">RezID: {r.booking_id}</span>
                        </div>
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex flex-col text-[11px] text-gray-700">
                          <span>TCKN: {r.national_id || '-'}</span>
                          <span>Pasaport: {r.passport_number || '-'}</span>
                        </div>
                      </td>
                      <td className="px-3 py-2 text-gray-700">
                        <div className="flex flex-col text-[11px]">
                          <span>{r.country || '-'}</span>
                          <span className="text-gray-500">{r.city || ''}</span>
                        </div>
                      </td>
                      <td className="px-3 py-2">{r.room_number || '-'}</td>
                      <td className="px-3 py-2 text-[11px] text-gray-700">
                        <div className="flex flex-col">
                          <span>{r.check_in}</span>
                          <span>{r.check_out}</span>
                        </div>
                      </td>
                      <td className="px-3 py-2 text-center">
                        {r.adults || 0} + {r.children || 0}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {Number(r.total_amount || 0).toLocaleString('tr-TR', {
                          style: 'currency',
                          currency: 'TRY',
                        })}
                      </td>
                    </tr>
                  ))}
                  {!rows.length && !loading && (
                    <tr>
                      <td className="px-3 py-6 text-center text-gray-500 text-xs" colSpan={7}>
                        Bu tarih için konaklayan misafir bulunamadı.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>
    </>
  );
};

export default OfficialGuestList;
