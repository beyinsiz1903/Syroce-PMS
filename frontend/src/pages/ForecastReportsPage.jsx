import { lazy, Suspense, useEffect, useState, useCallback, useRef } from "react";
import api from "@/api/axios";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { TrendingUp, RefreshCw, Loader2, BarChart3 } from "lucide-react";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend,
} from "recharts";
import { useTranslation } from 'react-i18next';
import { cachedTenantCurrency } from '@/lib/currency';
import { formatCurrencyBreakdown } from '@/lib/reportCurrency';
import { validateReportDate } from '@/utils/reportExports';
import { mergePaceSeries } from '@/lib/forecastReports';

const FrontdeskForecastReport = lazy(() => import('./reports/FrontdeskForecastReport'));

// Each tab owns its request generation and filter scope. A late response must
// neither overwrite a newer report nor stop another tab's loading indicator.
function useForecastReports() {
  const [reports, setReports] = useState({});
  const requests = useRef({ forecast: 0, pace: 0, pickup: 0 });
  useEffect(() => () => { for (const key of Object.keys(requests.current)) ++requests.current[key]; }, []);
  const load = useCallback(async (name, endpoint, params, scope) => {
    const id = ++requests.current[name];
    setReports(previous => ({ ...previous, [name]: { scope, loading: true, data: null, error: '' } }));
    try {
      if (name === 'pace') {
        validateReportDate(params.target_date);
        if (params.compare_year !== undefined && (!Number.isInteger(params.compare_year) || params.compare_year < 1 || params.compare_year > 9999)) {
          throw new Error('Geçerli bir karşılaştırma yılı seçin.');
        }
      }
      const { data } = await api.get(endpoint, { params });
      if (requests.current[name] === id) setReports(previous => ({ ...previous, [name]: { scope, loading: false, data, error: '' } }));
    } catch (error) {
      if (requests.current[name] === id) setReports(previous => ({ ...previous, [name]: {
        scope, loading: false, data: null, error: typeof error?.response?.data?.detail === 'string' ? error.response.data.detail : error.message || 'Rapor yüklenemedi.',
      } }));
    }
  }, []);
  return { reports, load };
}

/**
 * Opera #5 — Forecast / Pace / Pickup raporları.
 * Backend hazır (/api/analytics/forecast, /pickup-report, /pace).
 * Bu sürüm tablo + recharts grafikleri ile zenginleştirilmiş.
 */
export default function ForecastReportsPage({ initialTab = 'operational' }) {
  const { t } = useTranslation();
  const [tab, setTab] = useState(initialTab);
  const { reports, load } = useForecastReports();

  const [days, setDays] = useState(30);
  const [segment, setSegment] = useState("");
  const [pickupDays, setPickupDays] = useState(7);
  const [paceDate, setPaceDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [paceCompare, setPaceCompare] = useState(() => new Date().getFullYear() - 1);

  const forecastScope = JSON.stringify([days, segment]);
  const pickupScope = JSON.stringify([pickupDays]);
  const paceScope = JSON.stringify([paceDate, paceCompare]);
  const scopes = { forecast: forecastScope, pickup: pickupScope, pace: paceScope };
  const forecast = reports.forecast?.scope === forecastScope ? reports.forecast.data : null;
  const pickup = reports.pickup?.scope === pickupScope ? reports.pickup.data : null;
  const pace = reports.pace?.scope === paceScope ? reports.pace.data : null;
  const active = reports[tab]?.scope === scopes[tab] ? reports[tab] : null;
  const loading = Boolean(active?.loading);

  const loadForecast = useCallback(() => load('forecast', '/analytics/forecast', { days, segment: segment || undefined }, forecastScope), [days, segment, forecastScope, load]);
  const loadPickup = useCallback(() => load('pickup', '/analytics/pickup-report', { period_days: pickupDays }, pickupScope), [pickupDays, pickupScope, load]);
  const loadPace = useCallback(() => load('pace', '/analytics/pace', { target_date: paceDate, compare_year: paceCompare || undefined }, paceScope), [paceDate, paceCompare, paceScope, load]);

  // Tab değişiminde ilk yükleme; load fonksiyonları filtre tuş vuruşlarında
  // yeniden referans alır, deps'e koyarsak istemsiz API yağmuru olur.
  // Kullanıcı filtreleri değiştirip "Yenile"ye basar.
  useEffect(() => {
    if (tab === "forecast" && !active?.data && !loading) loadForecast();
    if (tab === "pickup" && !active?.data && !loading) loadPickup();
    if (tab === "pace" && !active?.data && !loading) loadPace();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- Filters are applied explicitly with Refresh, not on every keystroke.
  }, [tab]);

  // Pace tablosu: günsayım → bu yıl + karşılaştırma yıl rooms_on_books
  // tek diziye birleştir (recharts xAxis ortak olsun).
  const paceMerged = pace ? mergePaceSeries(pace.current, pace.compare) : [];

  return (
    <div className="space-y-4 min-w-0">
      <div>
        <h2 className="text-2xl font-semibold flex items-center gap-2">
          <TrendingUp className="h-6 w-6" /> Doluluk / Forecast
        </h2>
        <p className="text-sm text-muted-foreground">
          Tarih tarih dolu oda, kalan oda ve doluluk yüzdesi.
        </p>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="grid h-auto w-full grid-cols-2 lg:inline-flex lg:w-auto">
          <TabsTrigger className="min-w-0 whitespace-normal px-2 text-xs sm:text-sm" value="operational" data-testid="tab-operational">Ön Büro Forecast</TabsTrigger>
          <TabsTrigger className="min-w-0 whitespace-normal px-2 text-xs sm:text-sm" value="forecast" data-testid="tab-forecast">İstatistiksel Tahmin</TabsTrigger>
          <TabsTrigger className="min-w-0 whitespace-normal px-2 text-xs sm:text-sm" value="pace" data-testid="tab-pace">Rezervasyon Hızı</TabsTrigger>
          <TabsTrigger className="min-w-0 whitespace-normal px-2 text-xs sm:text-sm" value="pickup" data-testid="tab-pickup">Yeni Rezervasyonlar</TabsTrigger>
        </TabsList>

        {loading && <p role="status" className="py-3 text-sm text-muted-foreground">Rapor yükleniyor…</p>}
        {active?.error && <p role="alert" className="my-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{active.error}</p>}
        {tab !== 'operational' && !active && <p role="status" className="py-3 text-sm text-amber-800">Filtreler değişti. Seçili kapsam için Yenile düğmesine basın.</p>}
        {active?.data && !(active.data.daily?.length || active.data.current?.length || active.data.compare?.length) && <p role="status" className="py-3 text-sm text-muted-foreground">Seçili kapsamda rapor kaydı bulunmuyor.</p>}

        <TabsContent value="operational">{tab === 'operational' && <Suspense fallback={<p role="status">Ön büro forecast hazırlanıyor…</p>}><FrontdeskForecastReport /></Suspense>}</TabsContent>
        <TabsContent value="forecast">
          <Card>
            <CardHeader>
              <CardTitle>Doluluk Tahmini</CardTitle>
              <CardDescription>
                Mevcut geçerli rezervasyonlar ve geçmiş konaklama gecelerine dayalı tahmin. Satışa kapalı odalar kapasiteden çıkarılır; fazla rezervasyon gizlenmez. ADR ücretsiz odaları dışarıda tutar. Gelirler tahsilat veya kesinleşmiş defter geliri değildir.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-end gap-3 flex-wrap">
                <div>
                  <Label>Ufuk</Label>
                  <Select value={String(days)} onValueChange={(v) => setDays(Number(v))}>
                    <SelectTrigger className="w-[120px]" data-testid="select-forecast-days">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {[10, 30, 90, 180].map((n) => (
                        <SelectItem key={n} value={String(n)}>{n} {t('cm.pages_ForecastReportsPage.gun')}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Pazar bölümü (isteğe bağlı)</Label>
                  <Input
                    value={segment}
                    onChange={(e) => setSegment(e.target.value)}
                    placeholder="Kurumsal, bireysel…"
                    className="w-[200px]"
                    data-testid="input-forecast-segment"
                  />
                </div>
                <Button onClick={loadForecast} disabled={loading} data-testid="button-load-forecast">
                  {loading ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <RefreshCw className="h-4 w-4 mr-1" />}
                  {t('cm.pages_ForecastReportsPage.yenile')}
                </Button>
              </div>

              {forecast?.daily?.length > 0 && (
                <>
                  {forecast.data_quality?.warning && <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">{forecast.data_quality.warning}</div>}
                  <div className="text-xs text-muted-foreground">
                    {forecast.start_date && <span>{forecast.start_date} – {forecast.end_date} · </span>}
                    Yöntem: {forecast.data_quality?.method === 'otb_plus_historical_weekday' ? 'Mevcut rezervasyon + son 364 günün hafta günü gerçekleşmeleri' : 'Yalnız mevcut rezervasyon'}
                    {' · '}Tarihsel oda-gece: {forecast.data_quality?.historical_room_nights || 0}
                  </div>
                  <div className="h-64 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={forecast.daily}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                        <YAxis tick={{ fontSize: 11 }} />
                        <Tooltip />
                        <Legend />
                        <Line type="monotone" dataKey="rooms_otb" name="Kesinleşmiş Oda" stroke="#94a3b8" />
                        <Line type="monotone" dataKey="rooms_forecast" name="Tahmini Oda" stroke="#2563eb" strokeWidth={2} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>

                  <div className="overflow-x-auto">
                    <Table className="min-w-[1100px]" data-testid="forecast-table">
                      <TableHeader>
                        <TableRow>
                          <TableHead>{t('cm.pages_ForecastReportsPage.tarih')}</TableHead>
                          <TableHead className="text-right">Kesinleşmiş Oda</TableHead>
                          <TableHead className="text-right">Tahmini Oda</TableHead>
                          <TableHead className="text-right">Satılabilir Oda</TableHead>
                          <TableHead className="text-right">Fazla Rezervasyon</TableHead>
                          <TableHead className="text-right">Doluluk</TableHead>
                          <TableHead className="text-right">ADR</TableHead>
                          <TableHead className="text-right">RevPAR</TableHead>
                          <TableHead className="text-right">Mevcut Rez. Bedeli</TableHead>
                          <TableHead className="text-right">Tahmini Gelir</TableHead>
                          <TableHead className="text-right">Model Göstergesi*</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {forecast.daily.map((d) => (
                          <TableRow key={d.date}>
                            <TableCell>{d.date}</TableCell>
                            <TableCell className="text-right">{d.rooms_otb}</TableCell>
                            <TableCell className="text-right">{d.rooms_forecast}</TableCell>
                            <TableCell className="text-right">{d.available_rooms ?? forecast.total_rooms ?? '—'}</TableCell>
                            <TableCell className={`text-right ${d.overbooked_rooms > 0 ? 'font-semibold text-red-700' : ''}`}>{d.overbooked_rooms ?? 0}</TableCell>
                            <TableCell className="text-right">{d.capacity_conflict ? 'Kapasite yok' : `${d.occupancy_pct}%`}</TableCell>
                            <TableCell className="text-right">{formatCurrencyBreakdown(d.adr_by_currency, d.adr, forecast.currency || cachedTenantCurrency())}</TableCell>
                            <TableCell className="text-right">{d.capacity_conflict ? '—' : formatCurrencyBreakdown(d.revpar_by_currency, d.revpar, forecast.currency || cachedTenantCurrency())}</TableCell>
                            <TableCell className="text-right">{formatCurrencyBreakdown(d.revenue_otb_by_currency, d.revenue_otb, forecast.currency || cachedTenantCurrency())}</TableCell>
                            <TableCell className="text-right">{formatCurrencyBreakdown(d.revenue_forecast_by_currency, d.revenue_forecast, forecast.currency || cachedTenantCurrency())}</TableCell>
                            <TableCell className="text-right">%{Math.round((d.confidence || 0) * 100)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                  <p className="text-xs text-muted-foreground">Tahmini oda sayısı istatistiksel beklentidir; kesirli olabilir. * Model göstergesi basit bir veri/ufuk puanıdır; gerçekleşme olasılığı olarak kalibre edilmiş bir güven yüzdesi değildir. ADR = tahmini oda geliri / ücretli oda-gece; RevPAR = tahmini oda geliri / o günün satılabilir oda sayısı.</p>
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="pace">
          <Card>
            <CardHeader>
              <CardTitle>Rezervasyon Hızı</CardTitle>
              <CardDescription>
                Hedef geceyi kapsayan geçerli rezervasyonların oluşturulma tarihine göre birikimi. Bugünkü kayıt durumunu kullanır; geçmiş iptal/değişiklik anlarının birebir fotoğrafı değildir. Henüz yaşanmamış günler veri gibi gösterilmez.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-end gap-3 flex-wrap">
                <div>
                  <Label>Hedef tarih</Label>
                  <Input
                    type="date"
                    value={paceDate}
                    onChange={(e) => setPaceDate(e.target.value)}
                    className="w-[180px]"
                    data-testid="input-pace-date"
                  />
                </div>
                <div>
                  <Label>{t('cm.pages_ForecastReportsPage.karsilastirma_yili')}</Label>
                  <Input
                    type="number"
                    min="1"
                    max="9999"
                    value={paceCompare}
                    onChange={(e) => setPaceCompare(Number(e.target.value) || "")}
                    className="w-[140px]"
                    data-testid="input-pace-compare"
                  />
                </div>
                <Button onClick={loadPace} disabled={loading} data-testid="button-load-pace">
                  {loading ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <RefreshCw className="h-4 w-4 mr-1" />}
                  {t('cm.pages_ForecastReportsPage.yenile_aedf3')}
                </Button>
              </div>

              {paceMerged.length > 0 && (
                <>
                  {pace.as_of_date && <p className="text-xs text-muted-foreground">Rapor günü: {pace.as_of_date}</p>}
                  <div className="h-64 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={paceMerged}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="days_out" tick={{ fontSize: 11 }}
                          label={{ value: "Gün önce", position: "insideBottom", offset: -2, fontSize: 11 }} />
                        <YAxis tick={{ fontSize: 11 }} />
                        <Tooltip />
                        <Legend />
                        <Line type="stepAfter" connectNulls={false} dataKey="bu_yil" name="Seçili Dönem" stroke="#2563eb" strokeWidth={2} />
                        <Line type="stepAfter" connectNulls={false} dataKey="karsilastirma" name="Karşılaştırma" stroke="#94a3b8" />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>

                  <Table data-testid="pace-table">
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-center">{t('cm.pages_ForecastReportsPage.gun_once')}</TableHead>
                        <TableHead className="text-right">Seçili Dönem</TableHead>
                        <TableHead className="text-right">{t('cm.pages_ForecastReportsPage.karsilastirma')}</TableHead>
                        <TableHead className="text-right">Fark</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {paceMerged.map((p) => {
                        const diff = p.bu_yil != null && p.karsilastirma != null ? p.bu_yil - p.karsilastirma : null;
                        return (
                          <TableRow key={p.days_out}>
                            <TableCell className="text-center">{p.days_out ? `-${p.days_out}` : '0'}</TableCell>
                            <TableCell className="text-right">{p.bu_yil ?? '—'}</TableCell>
                            <TableCell className="text-right text-muted-foreground">{p.karsilastirma ?? "-"}</TableCell>
                            <TableCell className={`text-right ${diff > 0 ? "text-emerald-600" : diff < 0 ? "text-red-600" : ""}`}>
                              {diff != null ? (diff > 0 ? `+${diff}` : diff) : "-"}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="pickup">
          <Card>
            <CardHeader>
              <CardTitle>Yeni Rezervasyon Kazanımı</CardTitle>
              <CardDescription>
                Son günlerde oluşturulan, bugün geçerli rezervasyonların giriş tarihine göre oda ve konaklama bedeli. Ücretsiz odaların referans fiyatı gelir değildir. İptal/değişiklik hareketlerini içeren net pickup veya tahsilat raporu değildir.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-end gap-3 flex-wrap">
                <div>
                  <Label>Periyot</Label>
                  <Select value={String(pickupDays)} onValueChange={(v) => setPickupDays(Number(v))}>
                    <SelectTrigger className="w-[140px]" data-testid="select-pickup-days">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {[1, 7, 14, 30].map((n) => (
                        <SelectItem key={n} value={String(n)}>Son {n} {t('cm.pages_ForecastReportsPage.gun_54e78')}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <Button onClick={loadPickup} disabled={loading} data-testid="button-load-pickup">
                  {loading ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <RefreshCw className="h-4 w-4 mr-1" />}
                  {t('cm.pages_ForecastReportsPage.yenile_aedf3')}
                </Button>
              </div>

              {pickup && (
                <>
                  {pickup.start_at && <p className="text-xs text-muted-foreground">Oluşturulma aralığı: {new Date(pickup.start_at).toLocaleString('tr-TR')} – {new Date(pickup.end_at).toLocaleString('tr-TR')}</p>}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <Card>
                      <CardContent className="pt-4">
                        <div className="text-xs text-muted-foreground">{t('cm.pages_ForecastReportsPage.toplam_oda')}</div>
                        <div className="text-2xl font-semibold flex items-center gap-2">
                          <BarChart3 className="h-5 w-5 text-blue-600" />
                          {pickup.total_rooms_picked || 0}
                        </div>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardContent className="pt-4">
                        <div className="text-xs text-muted-foreground">Toplam Rezervasyon Bedeli</div>
                        <div className="text-2xl font-semibold [overflow-wrap:anywhere]">
                          {formatCurrencyBreakdown(pickup.total_revenue_picked_by_currency, pickup.total_revenue_picked, pickup.currency || cachedTenantCurrency())}
                        </div>
                      </CardContent>
                    </Card>
                  </div>

                  {(pickup.daily || []).length > 0 && (
                    <>
                      <div className="h-56 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={pickup.daily}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="check_in" tick={{ fontSize: 11 }} />
                            <YAxis tick={{ fontSize: 11 }} />
                            <Tooltip />
                            <Bar dataKey="rooms" fill="#2563eb" name="Oda" />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>

                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Giriş tarihi</TableHead>
                            <TableHead className="text-right">{t('cm.pages_ForecastReportsPage.oda')}</TableHead>
                            <TableHead className="text-right">Rezervasyon Bedeli</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {pickup.daily.map((d) => (
                            <TableRow key={d.check_in}>
                              <TableCell>{d.check_in}</TableCell>
                              <TableCell className="text-right">{d.rooms}</TableCell>
                              <TableCell className="text-right">{formatCurrencyBreakdown(d.revenue_by_currency, d.revenue, d.currency || pickup.currency || cachedTenantCurrency())}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
