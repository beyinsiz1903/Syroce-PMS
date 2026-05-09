import { useEffect, useState, useCallback } from "react";
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
import { useToast } from "@/hooks/use-toast";
import { TrendingUp, RefreshCw, Loader2, BarChart3 } from "lucide-react";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend,
} from "recharts";
import { useTranslation } from 'react-i18next';

/**
 * Opera #5 — Forecast / Pace / Pickup raporları.
 * Backend hazır (/api/analytics/forecast, /pickup-report, /pace).
 * Bu sürüm tablo + recharts grafikleri ile zenginleştirilmiş.
 */
export default function ForecastReportsPage() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [tab, setTab] = useState("forecast");

  const [days, setDays] = useState(30);
  const [segment, setSegment] = useState("");
  const [forecast, setForecast] = useState(null);

  const [pickup, setPickup] = useState(null);
  const [pickupDays, setPickupDays] = useState(7);

  const [pace, setPace] = useState(null);
  const [paceDate, setPaceDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [paceCompare, setPaceCompare] = useState(() => new Date().getFullYear() - 1);

  const [loading, setLoading] = useState(false);

  const handleErr = useCallback((title, e) => {
    toast({
      title,
      description: e?.response?.data?.detail || e.message,
      variant: "destructive",
    });
  }, [toast]);

  const loadForecast = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/api/analytics/forecast", {
        params: { days, segment: segment || undefined },
      });
      setForecast(data);
    } catch (e) { handleErr("Forecast yüklenemedi", e); }
    finally { setLoading(false); }
  }, [days, segment, handleErr]);

  const loadPickup = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/api/analytics/pickup-report", {
        params: { period_days: pickupDays },
      });
      setPickup(data);
    } catch (e) { handleErr("Pickup yüklenemedi", e); }
    finally { setLoading(false); }
  }, [pickupDays, handleErr]);

  const loadPace = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/api/analytics/pace", {
        params: { target_date: paceDate, compare_year: paceCompare || undefined },
      });
      setPace(data);
    } catch (e) { handleErr("Pace yüklenemedi", e); }
    finally { setLoading(false); }
  }, [paceDate, paceCompare, handleErr]);

  // Tab değişiminde ilk yükleme; load fonksiyonları filtre tuş vuruşlarında
  // yeniden referans alır, deps'e koyarsak istemsiz API yağmuru olur.
  // Kullanıcı filtreleri değiştirip "Yenile"ye basar.
  useEffect(() => {
    if (tab === "forecast" && !forecast) loadForecast();
    if (tab === "pickup" && !pickup) loadPickup();
    if (tab === "pace" && !pace) loadPace();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [tab]);

  // Pace tablosu: günsayım → bu yıl + karşılaştırma yıl rooms_on_books
  // tek diziye birleştir (recharts xAxis ortak olsun).
  const paceMerged = pace
    ? (pace.current || []).map((p) => {
      const cmp = (pace.compare || []).find((c) => c.days_out === p.days_out);
      return {
        days_out: p.days_out,
        bu_yil: p.rooms_on_books,
        karsilastirma: cmp?.rooms_on_books ?? null,
      };
    }).sort((a, b) => b.days_out - a.days_out)
    : [];

  return (
    <div className="container mx-auto p-6 space-y-4 max-w-7xl">
      <div>
        <h2 className="text-2xl font-semibold flex items-center gap-2">
          <TrendingUp className="h-6 w-6" /> Forecast / Pace / Pickup
        </h2>
        <p className="text-sm text-muted-foreground">
          {t('cm.pages_ForecastReportsPage.10_30_90_gun_doluluk_tahmini_booking_pac')}
        </p>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="forecast" data-testid="tab-forecast">Forecast</TabsTrigger>
          <TabsTrigger value="pace" data-testid="tab-pace">Pace</TabsTrigger>
          <TabsTrigger value="pickup" data-testid="tab-pickup">Pickup</TabsTrigger>
        </TabsList>

        <TabsContent value="forecast">
          <Card>
            <CardHeader>
              <CardTitle>Doluluk Tahmini</CardTitle>
              <CardDescription>
                On-the-books + tahmin. Segment filtresi opsiyonel.
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
                  <Label>Segment (opsiyonel)</Label>
                  <Input
                    value={segment}
                    onChange={(e) => setSegment(e.target.value)}
                    placeholder="corporate, leisure…"
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
                  <div className="h-64 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={forecast.daily}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                        <YAxis tick={{ fontSize: 11 }} />
                        <Tooltip />
                        <Legend />
                        <Line type="monotone" dataKey="rooms_otb" name="OTB Oda" stroke="#94a3b8" />
                        <Line type="monotone" dataKey="rooms_forecast" name="Forecast Oda" stroke="#2563eb" strokeWidth={2} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>

                  <div className="overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>{t('cm.pages_ForecastReportsPage.tarih')}</TableHead>
                          <TableHead className="text-right">OTB</TableHead>
                          <TableHead className="text-right">Forecast</TableHead>
                          <TableHead className="text-right">Doluluk</TableHead>
                          <TableHead className="text-right">ADR</TableHead>
                          <TableHead className="text-right">RevPAR</TableHead>
                          <TableHead className="text-right">OTB Gelir</TableHead>
                          <TableHead className="text-right">Forecast Gelir</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {forecast.daily.map((d) => (
                          <TableRow key={d.date}>
                            <TableCell>{d.date}</TableCell>
                            <TableCell className="text-right">{d.rooms_otb}</TableCell>
                            <TableCell className="text-right">{d.rooms_forecast}</TableCell>
                            <TableCell className="text-right">{d.occupancy_pct}%</TableCell>
                            <TableCell className="text-right">{d.adr}</TableCell>
                            <TableCell className="text-right">{d.revpar}</TableCell>
                            <TableCell className="text-right">{d.revenue_otb}</TableCell>
                            <TableCell className="text-right">{d.revenue_forecast}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="pace">
          <Card>
            <CardHeader>
              <CardTitle>Booking Pace</CardTitle>
              <CardDescription>
                {t('cm.pages_ForecastReportsPage.hedef_tarih_icin_x_gun_once_kac_oda_elim')}
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
                  <div className="h-64 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={paceMerged}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="days_out" reversed tick={{ fontSize: 11 }}
                          label={{ value: "Gün önce", position: "insideBottom", offset: -2, fontSize: 11 }} />
                        <YAxis tick={{ fontSize: 11 }} />
                        <Tooltip />
                        <Legend />
                        <Line type="monotone" dataKey="bu_yil" name="Bu yıl" stroke="#2563eb" strokeWidth={2} />
                        <Line type="monotone" dataKey="karsilastirma" name="Karşılaştırma" stroke="#94a3b8" />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>

                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-center">{t('cm.pages_ForecastReportsPage.gun_once')}</TableHead>
                        <TableHead className="text-right">{t('cm.pages_ForecastReportsPage.bu_yil')}</TableHead>
                        <TableHead className="text-right">{t('cm.pages_ForecastReportsPage.karsilastirma')}</TableHead>
                        <TableHead className="text-right">Fark</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {paceMerged.map((p) => {
                        const diff = p.karsilastirma != null ? p.bu_yil - p.karsilastirma : null;
                        return (
                          <TableRow key={p.days_out}>
                            <TableCell className="text-center">-{p.days_out}</TableCell>
                            <TableCell className="text-right">{p.bu_yil}</TableCell>
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
              <CardTitle>Pickup Raporu</CardTitle>
              <CardDescription>
                {t('cm.pages_ForecastReportsPage.son_n_gunde_alinan_rezervasyonlarin_chec')}
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
                  <div className="grid grid-cols-2 gap-4">
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
                        <div className="text-xs text-muted-foreground">{t('cm.pages_ForecastReportsPage.toplam_gelir')}</div>
                        <div className="text-2xl font-semibold">
                          {(pickup.total_revenue_picked || 0).toLocaleString("tr-TR")} ₺
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
                            <TableHead>Check-in</TableHead>
                            <TableHead className="text-right">{t('cm.pages_ForecastReportsPage.oda')}</TableHead>
                            <TableHead className="text-right">Gelir</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {pickup.daily.map((d) => (
                            <TableRow key={d.check_in}>
                              <TableCell>{d.check_in}</TableCell>
                              <TableCell className="text-right">{d.rooms}</TableCell>
                              <TableCell className="text-right">{Number(d.revenue || 0).toLocaleString("tr-TR")} ₺</TableCell>
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
