import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Calendar, Loader2, Search, Download, Printer, Shield } from 'lucide-react';
import { SectionHeader } from './ReportHelpers';
import { GuestTable } from './GuestSection';

export const OfficialSection = ({
  officialDate, setOfficialDate, officialRows, officialLoading,
  officialError, officialSearch, setOfficialSearch,
  fetchOfficialGuests, handleOfficialExportCsv, handleOfficialPrint,
  filteredOfficialRows, officialTotalGuests, officialTotalRevenue,
}) => (
  <div className="space-y-4" data-testid="section-official">
    <SectionHeader title="Resmi Müşteri Listesi (Maliye Raporu)" description="Maliye ve resmi denetimler için seçtiğiniz tarihte otelde konaklayan tüm misafirlerin listesi" />
    <Card>
      <CardContent className="p-4">
        <div className="flex flex-col md:flex-row md:items-center gap-3">
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-gray-500" />
            <Input type="date" value={officialDate} onChange={e => setOfficialDate(e.target.value)} className="h-9 text-sm w-[170px] bg-white border-gray-300 text-gray-900" data-testid="official-date-input" />
          </div>
          <Button size="sm" onClick={() => fetchOfficialGuests(officialDate)} disabled={officialLoading} className="bg-blue-600 hover:bg-blue-700 text-white" data-testid="official-fetch-btn">
            {officialLoading ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Search className="w-3.5 h-3.5 mr-1.5" />}
            Listeyi Getir
          </Button>
          <div className="flex items-center gap-2 md:ml-auto">
            <Button variant="outline" size="sm" onClick={handleOfficialExportCsv} disabled={officialLoading || !officialRows.length} data-testid="official-csv-btn">
              <Download className="w-3.5 h-3.5 mr-1.5" />CSV İndir
            </Button>
            <Button variant="outline" size="sm" onClick={handleOfficialPrint} disabled={officialLoading || !officialRows.length} data-testid="official-print-btn">
              <Printer className="w-3.5 h-3.5 mr-1.5" />Yazdır
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>

    {officialError && (
      <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">{officialError}</div>
    )}

    {officialRows.length > 0 && (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="p-3 bg-blue-50 rounded-lg border border-blue-100 text-center">
          <p className="text-xs text-blue-600 font-medium">Toplam Kayıt</p>
          <p className="text-xl font-bold text-blue-800">{officialRows.length}</p>
        </div>
        <div className="p-3 bg-emerald-50 rounded-lg border border-emerald-100 text-center">
          <p className="text-xs text-emerald-600 font-medium">Toplam Kişi</p>
          <p className="text-xl font-bold text-emerald-800">{officialTotalGuests}</p>
        </div>
        <div className="p-3 bg-amber-50 rounded-lg border border-amber-100 text-center">
          <p className="text-xs text-amber-600 font-medium">Toplam Tutar</p>
          <p className="text-xl font-bold text-amber-800">{officialTotalRevenue.toLocaleString('tr-TR', { style: 'currency', currency: 'TRY' })}</p>
        </div>
        <div className="p-3 bg-violet-50 rounded-lg border border-violet-100 text-center">
          <p className="text-xs text-violet-600 font-medium">Seçili Tarih</p>
          <p className="text-xl font-bold text-violet-800">{new Date(officialDate).toLocaleDateString('tr-TR')}</p>
        </div>
      </div>
    )}

    {officialRows.length > 0 && (
      <div className="relative">
        <Search className="w-4 h-4 absolute left-3 top-2.5 text-gray-400 z-10" />
        <Input placeholder="İsim, oda no, TCKN veya pasaport ile filtrele..." value={officialSearch} onChange={e => setOfficialSearch(e.target.value)} className="pl-9 bg-white border-gray-300 text-gray-900 placeholder:text-gray-400 focus:border-blue-400 focus:ring-blue-200" data-testid="official-search-input" />
      </div>
    )}

    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1">
          <span>{officialDate} tarihi için konaklayan misafirler</span>
          {officialRows.length > 0 && (
            <span className="text-xs text-gray-500 flex gap-3 flex-wrap">
              <span>{filteredOfficialRows.length} kayıt gösteriliyor</span>
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="min-w-full text-xs border-t" data-testid="official-guest-table">
            <thead className="bg-gray-50 border-b">
              <tr className="text-left whitespace-nowrap">
                <th className="px-3 py-2.5 font-semibold text-gray-600">Misafir</th>
                <th className="px-3 py-2.5 font-semibold text-gray-600">TCKN / Pasaport</th>
                <th className="px-3 py-2.5 font-semibold text-gray-600">Ülke / Şehir</th>
                <th className="px-3 py-2.5 font-semibold text-gray-600">Oda</th>
                <th className="px-3 py-2.5 font-semibold text-gray-600">Giriş / Çıkış</th>
                <th className="px-3 py-2.5 font-semibold text-gray-600">Kişi</th>
                <th className="px-3 py-2.5 font-semibold text-gray-600 text-right">Tutar</th>
              </tr>
            </thead>
            <tbody>
              {officialLoading ? (
                <tr><td colSpan={7} className="py-12 text-center"><Loader2 className="w-5 h-5 animate-spin text-blue-500 mx-auto mb-2" /><span className="text-gray-400 text-xs">Yükleniyor...</span></td></tr>
              ) : filteredOfficialRows.length > 0 ? filteredOfficialRows.map((r, i) => (
                <tr key={r.booking_id || i} className="border-b hover:bg-blue-50/30 transition-colors">
                  <td className="px-3 py-2"><div className="font-medium text-gray-800">{r.guest_name || 'Misafir'}</div><div className="text-[10px] text-gray-400">Rez: {r.booking_id}</div></td>
                  <td className="px-3 py-2"><div className="text-[11px] text-gray-700">TCKN: {r.national_id || '-'}</div><div className="text-[11px] text-gray-500">Pasaport: {r.passport_number || '-'}</div></td>
                  <td className="px-3 py-2"><div className="text-[11px] text-gray-700">{r.country || '-'}</div><div className="text-[11px] text-gray-500">{r.city || ''}</div></td>
                  <td className="px-3 py-2 font-medium">{r.room_number || '-'}</td>
                  <td className="px-3 py-2 text-[11px] text-gray-700"><div>{r.check_in ? new Date(r.check_in).toLocaleDateString('tr-TR') : '-'}</div><div>{r.check_out ? new Date(r.check_out).toLocaleDateString('tr-TR') : '-'}</div></td>
                  <td className="px-3 py-2 text-center">{(r.adults || 0)} + {(r.children || 0)}</td>
                  <td className="px-3 py-2 text-right font-medium">{Number(r.total_amount || 0).toLocaleString('tr-TR', { style: 'currency', currency: 'TRY' })}</td>
                </tr>
              )) : (
                <tr><td colSpan={7} className="py-10 text-center text-gray-400 text-xs">
                  {officialRows.length === 0 ? 'Listeyi getirmek için tarih seçip "Listeyi Getir" butonuna tıklayın.' : 'Arama kriterlerine uygun kayıt bulunamadı.'}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  </div>
);

export const PoliceSection = ({ filteredGuests, searchGuest, setSearchGuest }) => (
  <div data-testid="section-police">
    <Card className="mb-5 border-blue-200 bg-blue-50/30">
      <CardContent className="p-4 flex items-start gap-3">
        <Shield className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
        <div>
          <h4 className="font-semibold text-gray-900 text-sm">Polis Bildirimi (Emniyet Listesi)</h4>
          <p className="text-xs text-gray-600 mt-0.5">Emniyet Müdürlüğü'ne bildirilmesi gereken konaklayan misafir listesi. TC Kimlik No ve pasaport bilgileri dahildir.</p>
        </div>
      </CardContent>
    </Card>
    <GuestTable guests={filteredGuests} title="Polis Bildirimi Listesi" showId={true} searchGuest={searchGuest} setSearchGuest={setSearchGuest} />
  </div>
);
