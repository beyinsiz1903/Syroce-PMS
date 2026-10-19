import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Leaf, Droplet, Zap, Trash2, FileText, Upload, RefreshCw } from 'lucide-react';
import apiErrorText from '@/utils/apiErrorText';

// Report period: the current calendar month by default (was fixed to July 2026).
const pad = (n) => String(n).padStart(2, '0');
const localDay = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export const currentMonth = (now = new Date()) => ({
  start: localDay(new Date(now.getFullYear(), now.getMonth(), 1)),
  end: localDay(new Date(now.getFullYear(), now.getMonth() + 1, 0)),
});

export default function SustainabilityReport() {
  const [factors, setFactors] = useState([]);
  const [records, setRecords] = useState([]);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [period, setPeriod] = useState(currentMonth);
  const [activeTab, setActiveTab] = useState("report"); // 'report' or 'entry'
  
  // Form state
  const [formType, setFormType] = useState("electricity");
  const [formAmount, setFormAmount] = useState("");
  const [formStart, setFormStart] = useState("");
  const [formEnd, setFormEnd] = useState("");

  const fetchData = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      const [f, r, rep] = await Promise.all([
        axios.get('/sustainability/factors'),
        axios.get('/sustainability/records'),
        axios.get('/sustainability/report', { params: { start_date: period.start, end_date: period.end } }),
      ]);
      setFactors(f.data);
      setRecords(r.data);
      setReport(rep.data);
    } catch (error) {
      // A failed load is an error, not an empty report.
      setReport(null);
      setLoadError(apiErrorText(error, 'Sürdürülebilirlik verileri yüklenemedi.'));
    } finally {
      setLoading(false);
    }
  }, [period.start, period.end]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formAmount || !formStart || !formEnd) return;
    
    try {
      await axios.post('/sustainability/records', {
        consumption_type: formType,
        period_start: formStart,
        period_end: formEnd,
        amount: parseFloat(formAmount),
      });
      setFormAmount("");
      fetchData();
      setActiveTab("report");
    } catch (err) {
      toast.error(apiErrorText(err, 'Kayıt eklenemedi.'));
    }
  };

  const getTypeIcon = (type) => {
    if (type.includes("electricity")) return <Zap className="w-5 h-5 text-yellow-500" />;
    if (type.includes("gas")) return <Droplet className="w-5 h-5 text-amber-500" />;
    if (type.includes("water")) return <Droplet className="w-5 h-5 text-blue-500" />;
    return <Trash2 className="w-5 h-5 text-gray-500" />;
  };

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Leaf className="text-green-600" /> Sürdürülebilirlik Raporu
          </h1>
          <p className="text-slate-500">Scope 1 & Scope 2 Karbon Ayak İzi ve Tüketim Takibi</p>
        </div>
        <Button onClick={fetchData} variant="outline" size="sm" disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} /> Yenile
        </Button>
      </div>

      <div className="flex space-x-2 border-b pb-2">
        <button 
          onClick={() => setActiveTab("report")}
          className={`px-4 py-2 font-medium rounded-t-lg ${activeTab === 'report' ? 'bg-green-50 text-green-700 border-b-2 border-green-600' : 'text-slate-600 hover:bg-slate-50'}`}
        >
          Rapor Özeti ({period.start} – {period.end})
        </button>
        <button 
          onClick={() => setActiveTab("entry")}
          className={`px-4 py-2 font-medium rounded-t-lg ${activeTab === 'entry' ? 'bg-green-50 text-green-700 border-b-2 border-green-600' : 'text-slate-600 hover:bg-slate-50'}`}
        >
          Veri Girişi & Kanıt Yükleme
        </button>
      </div>

      {activeTab === "report" && (
        <div className="flex flex-wrap items-end gap-3" data-testid="sustainability-period">
          <label className="text-sm">Başlangıç
            <input type="date" className="ml-2 rounded border px-2 py-1" value={period.start} max={period.end}
              onChange={(e) => e.target.value && setPeriod((p) => ({ ...p, start: e.target.value }))} />
          </label>
          <label className="text-sm">Bitiş
            <input type="date" className="ml-2 rounded border px-2 py-1" value={period.end} min={period.start}
              onChange={(e) => e.target.value && setPeriod((p) => ({ ...p, end: e.target.value }))} />
          </label>
        </div>
      )}

      {activeTab === "report" && loadError && (
        <div role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700" data-testid="sustainability-error">
          {loadError} <Button size="sm" variant="outline" className="ml-2" onClick={fetchData}>Tekrar dene</Button>
        </div>
      )}

      {activeTab === "report" && report && report.prorated_record_count > 0 && (
        <p className="rounded bg-amber-50 p-2 text-xs text-amber-800" data-testid="sustainability-allocation">
          {report.prorated_record_count} kaydın dönemi rapor dönemini aşıyor; tüketimi gün oranında bölüştürüldü. {report.allocation}
        </p>
      )}

      {activeTab === "report" && report && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <Card className="bg-slate-50">
              <CardContent className="p-6 text-center">
                <p className="text-sm font-medium text-slate-500">Toplam Scope 1</p>
                <h3 className="text-3xl font-bold text-amber-600">{report.total_scope_1.toLocaleString()}</h3>
                <p className="text-xs text-slate-500">kgCO2e</p>
              </CardContent>
            </Card>
            <Card className="bg-slate-50">
              <CardContent className="p-6 text-center">
                <p className="text-sm font-medium text-slate-500">Toplam Scope 2</p>
                <h3 className="text-3xl font-bold text-yellow-600">{report.total_scope_2.toLocaleString()}</h3>
                <p className="text-xs text-slate-500">kgCO2e</p>
              </CardContent>
            </Card>
            <Card className="bg-slate-50">
              <CardContent className="p-6 text-center">
                <p className="text-sm font-medium text-slate-500">Toplam Scope 3 (Atık/Su)</p>
                <h3 className="text-3xl font-bold text-blue-600">{report.total_scope_3.toLocaleString()}</h3>
                <p className="text-xs text-slate-500">kgCO2e</p>
              </CardContent>
            </Card>
            <Card className="bg-green-50 border-green-200">
              <CardContent className="p-6 text-center">
                <p className="text-sm font-medium text-green-700">Oda Gece Başına Emisyon</p>
                <h3 className="text-3xl font-bold text-green-700" data-testid="sustainability-per-night">{report.emissions_per_room_night == null ? 'Hesaplanamaz' : report.emissions_per_room_night.toLocaleString()}</h3>
                <p className="text-xs text-green-600">kgCO2e / Oda-Gece (dolu oda-gece: {report.total_room_nights}{report.total_room_nights === 0 ? ' — dönemde konaklama yok' : ''})</p>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Geçmiş Tüketim Kayıtları</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead className="text-xs text-slate-500 uppercase bg-slate-50">
                    <tr>
                      <th className="px-4 py-3">Tür</th>
                      <th className="px-4 py-3">Dönem</th>
                      <th className="px-4 py-3 text-right">Miktar</th>
                      <th className="px-4 py-3 text-right">CO2e (kg)</th>
                      <th className="px-4 py-3 text-center">Kanıt / Fatura</th>
                    </tr>
                  </thead>
                  <tbody>
                    {records.map(r => {
                      const factor = factors.find(f => f.id === r.consumption_type);
                      return (
                        <tr key={r.id} className="border-b hover:bg-slate-50">
                          <td className="px-4 py-3 flex items-center gap-2 font-medium">
                            {getTypeIcon(r.consumption_type)}
                            {factor ? factor.name : r.consumption_type}
                          </td>
                          <td className="px-4 py-3">{r.period_start} to {r.period_end}</td>
                          <td className="px-4 py-3 text-right">{r.amount.toLocaleString()} {factor?.unit}</td>
                          <td className="px-4 py-3 text-right font-medium">{r.emissions_kg_co2e.toLocaleString()}</td>
                          <td className="px-4 py-3 text-center">
                            {r.evidence_url ? (
                              <a href={r.evidence_url} target="_blank" rel="noreferrer" className="inline-flex items-center text-blue-600 hover:underline">
                                <FileText className="w-4 h-4 mr-1"/> Göster
                              </a>
                            ) : (
                              <span className="text-slate-400">-</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                    {records.length === 0 && (
                      <tr>
                        <td colSpan={5} className="text-center py-8 text-slate-500">Kayıt bulunamadı.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === "entry" && (
        <Card className="max-w-2xl mx-auto">
          <CardHeader>
            <CardTitle>Yeni Tüketim Ekle</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Tüketim Türü</label>
                  <select 
                    className="w-full border p-2 rounded focus:ring-2 focus:ring-green-500 outline-none"
                    value={formType}
                    onChange={e => setFormType(e.target.value)}
                  >
                    {factors.map(f => (
                      <option key={f.id} value={f.id}>{f.name} (Scope {f.scope})</option>
                    ))}
                  </select>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Miktar</label>
                  <div className="flex">
                    <input 
                      type="number" 
                      step="0.01" 
                      required
                      className="w-full border border-r-0 p-2 rounded-l focus:ring-2 focus:ring-green-500 outline-none"
                      value={formAmount}
                      onChange={e => setFormAmount(e.target.value)}
                    />
                    <span className="bg-slate-100 border border-l-0 p-2 rounded-r text-slate-500 text-sm flex items-center">
                      {factors.find(f => f.id === formType)?.unit || ""}
                    </span>
                  </div>
                </div>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Dönem Başlangıç</label>
                  <input 
                    type="date" 
                    required
                    className="w-full border p-2 rounded focus:ring-2 focus:ring-green-500 outline-none"
                    value={formStart}
                    onChange={e => setFormStart(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Dönem Bitiş</label>
                  <input 
                    type="date" 
                    required
                    className="w-full border p-2 rounded focus:ring-2 focus:ring-green-500 outline-none"
                    value={formEnd}
                    onChange={e => setFormEnd(e.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Kanıt / Fatura Yükle (Opsiyonel)</label>
                <div className="border-2 border-dashed rounded-lg p-6 flex flex-col items-center justify-center text-slate-500 hover:bg-slate-50 cursor-pointer">
                  <Upload className="w-8 h-8 mb-2 text-slate-400" />
                  <p className="text-sm">Fatura PDF veya Görselini sürükleyip bırakın</p>
                  <p className="text-xs mt-1">(Geçerli altyapı kurulumu bekleniyor, geçici olarak devre dışıdır)</p>
                </div>
              </div>

              <Button type="submit" className="w-full bg-green-600 hover:bg-green-700">
                Kaydet ve Hesapla
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
