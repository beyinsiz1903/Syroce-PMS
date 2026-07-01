import { useEffect, useState, useCallback } from "react";
import api from "@/api/axios";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useToast } from "@/hooks/use-toast";
import {
  ClipboardCheck, RefreshCw, TrendingUp, Users, Wallet,
  CheckCircle2, AlertCircle, Building, ArrowDownToLine, ArrowUpFromLine,
} from "lucide-react";
import { useTranslation } from 'react-i18next';

/**
 * Opera #8 — Trial Balance / Daily Operations Resume.
 * Gece auditi sonrası tek özet rapor: gelir, ödeme, doluluk, AR, depozito,
 * açık folio, balans kontrolü.
 *
 * Backend: GET /api/trial-balance?date=YYYY-MM-DD
 */

const PAYMENT_LABELS = {
  cash: "Nakit",
  card: "Kart",
  credit_card: "Kredi Kartı",
  bank_transfer: "Havale/EFT",
  ar: "Cari Hesap",
  deposit: "Depozit Düşümü",
  voucher: "Voucher",
  other: "Diğer",
};

const CATEGORY_LABELS = {
  rooms: "Oda",
  room: "Oda",
  fnb: "Yiyecek-İçecek",
  food: "Yiyecek",
  beverage: "İçecek",
  spa: "Spa",
  laundry: "Çamaşır",
  minibar: "Minibar",
  phone: "Telefon",
  parking: "Otopark",
  other: "Diğer",
};

const fmt = (n) => new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n || 0);

function MetricCard({ icon: Icon, label, value, sub, color = "text-foreground" }) {
  const { t } = useTranslation();
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xs text-muted-foreground">{label}</div>
            <div className={`text-2xl font-semibold mt-1 ${color}`}>{value}</div>
            {sub && <div className="text-xs text-muted-foreground mt-1">{sub}</div>}
          </div>
          <Icon className="h-5 w-5 text-muted-foreground" />
        </div>
      </CardContent>
    </Card>
  );
}

export default function TrialBalancePage() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get("/trial-balance", { params: { date } });
      setData(r.data);
    } catch (e) {
      toast({
        title: "Yüklenemedi",
        description: e?.response?.data?.detail || e.message,
        variant: "destructive",
      });
    } finally { setLoading(false); }
  }, [date, toast]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="container mx-auto p-6 space-y-4 max-w-7xl">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-2xl font-semibold flex items-center gap-2">
            <ClipboardCheck className="h-6 w-6" /> {t('cm.pages_TrialBalancePage.trial_balance_gunluk_ozet')}
          </h2>
          <p className="text-sm text-muted-foreground">
            {t('cm.pages_TrialBalancePage.gece_auditi_sonrasi_gelir_odeme_doluluk_')}
          </p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <Label>{t('cm.pages_TrialBalancePage.tarih')}</Label>
            <Input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="w-[160px]"
              data-testid="input-tb-date"
            />
          </div>
          <Button variant="outline" onClick={load} disabled={loading} data-testid="button-tb-refresh">
            <RefreshCw className={`h-4 w-4 mr-1 ${loading ? "animate-spin" : ""}`} /> {t('cm.pages_TrialBalancePage.yenile')}
          </Button>
        </div>
      </div>

      {!data && loading && (
        <div className="text-center py-12 text-muted-foreground">{t('cm.pages_TrialBalancePage.yukleniyor')}</div>
      )}

      {data && (
        <>
          {/* Balans alarmı */}
          <Card className={data.balance_check.in_balance ? "border-emerald-500" : "border-amber-500"}>
            <CardContent className="pt-6 flex items-center gap-3">
              {data.balance_check.in_balance ? (
                <CheckCircle2 className="h-6 w-6 text-emerald-600" />
              ) : (
                <AlertCircle className="h-6 w-6 text-amber-600" />
              )}
              <div className="flex-1">
                <div className="font-medium">
                  {data.balance_check.in_balance
                    ? "Gelir ve ödemeler dengeli"
                    : "Gelir ↔ Ödeme dengesizliği"}
                </div>
                <div className="text-xs text-muted-foreground">
                  Fark: ₺{fmt(data.balance_check.revenue_minus_payments)}
                  {" · "}{t('cm.pages_TrialBalancePage.ar_cari_a_yansiyacak_tutar')}
                </div>
              </div>
              {data.last_night_audit && (
                <Badge variant="outline">
                  Son audit: {data.last_night_audit.status || "—"}
                  {data.last_night_audit.audit_date ? ` · ${data.last_night_audit.audit_date.slice(0, 10)}` : ""}
                </Badge>
              )}
            </CardContent>
          </Card>

          {/* KPI grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard
              icon={Building}
              label="Doluluk"
              value={`%${data.occupancy.occupancy_pct}`}
              sub={`${data.occupancy.occupied}/${data.occupancy.total_rooms} oda · ${data.occupancy.out_of_order} OOO${data.occupancy.basis === "booking_span" ? " · tarih bazlı" : ""}`}
            />
            <MetricCard
              icon={TrendingUp}
              label="ADR"
              value={`₺${fmt(data.revenue.adr)}`}
              sub={`RevPAR ₺${fmt(data.revenue.revpar)}`}
            />
            <MetricCard
              icon={Wallet}
              label={t('cm.pages_TrialBalancePage.toplam_gelir')}
              value={`₺${fmt(data.revenue.total)}`}
              sub={`Oda ₺${fmt(data.revenue.rooms)} · F&B ₺${fmt(data.revenue.fnb)}`}
              color="text-emerald-600"
            />
            <MetricCard
              icon={ArrowDownToLine}
              label={t('cm.pages_TrialBalancePage.toplam_tahsilat')}
              value={`₺${fmt(data.payments.total)}`}
              sub={`${Object.keys(data.payments.by_method).length} ödeme yöntemi`}
              color="text-blue-600"
            />
          </div>

          {/* Hareket grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard
              icon={ArrowDownToLine}
              label={t('cm.pages_TrialBalancePage.gelis_arrival')}
              value={data.movements.arrivals}
              sub="Bugün check-in"
            />
            <MetricCard
              icon={ArrowUpFromLine}
              label={t('cm.pages_TrialBalancePage.cikis_departure')}
              value={data.movements.departures}
              sub="Bugün check-out"
            />
            <MetricCard
              icon={Users}
              label="In-House"
              value={data.movements.in_house}
              sub="Otelde misafir"
            />
            <MetricCard
              icon={AlertCircle}
              label="No-show"
              value={data.movements.no_shows}
              sub="Gelmeyen rezervasyon"
              color={data.movements.no_shows > 0 ? "text-amber-600" : ""}
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Gelir kategori */}
            <Card>
              <CardHeader>
                <CardTitle>{t('cm.pages_TrialBalancePage.gelir_kategori_bazli')}</CardTitle>
                <CardDescription>{t('cm.pages_TrialBalancePage.folio_charges_uzerinden_kategori_dagilim')}</CardDescription>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Kategori</TableHead>
                      <TableHead className="text-right">{t('cm.pages_TrialBalancePage.tutar')}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    <TableRow>
                      <TableCell className="font-medium">{t('cm.pages_TrialBalancePage.oda_geliri')}</TableCell>
                      <TableCell className="text-right font-medium">₺{fmt(data.revenue.rooms)}</TableCell>
                    </TableRow>
                    {Object.keys(data.revenue.by_category).length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={2} className="text-center text-muted-foreground py-4">
                          {t('cm.pages_TrialBalancePage.bu_gune_ait_folio_charge_yok')}
                        </TableCell>
                      </TableRow>
                    ) : (
                      Object.entries(data.revenue.by_category).map(([k, v]) => (
                        <TableRow key={k}>
                          <TableCell>{CATEGORY_LABELS[k] || k}</TableCell>
                          <TableCell className="text-right">₺{fmt(v)}</TableCell>
                        </TableRow>
                      ))
                    )}
                    <TableRow className="border-t-2">
                      <TableCell className="font-semibold">{t('cm.pages_TrialBalancePage.toplam')}</TableCell>
                      <TableCell className="text-right font-semibold text-emerald-700">
                        ₺{fmt(data.revenue.total)}
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            {/* Ödeme yöntemi */}
            <Card>
              <CardHeader>
                <CardTitle>{t('cm.pages_TrialBalancePage.tahsilat_odeme_yontemi')}</CardTitle>
                <CardDescription>{t('cm.pages_TrialBalancePage.bugunun_payment_koleksiyonu_kayitlari')}</CardDescription>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t('cm.pages_TrialBalancePage.yontem')}</TableHead>
                      <TableHead className="text-right">Adet</TableHead>
                      <TableHead className="text-right">{t('cm.pages_TrialBalancePage.tutar_5c5cd')}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {Object.keys(data.payments.by_method).length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={3} className="text-center text-muted-foreground py-4">
                          {t('cm.pages_TrialBalancePage.bu_gune_ait_tahsilat_yok')}
                        </TableCell>
                      </TableRow>
                    ) : (
                      Object.entries(data.payments.by_method).map(([k, v]) => (
                        <TableRow key={k}>
                          <TableCell>{PAYMENT_LABELS[k] || k}</TableCell>
                          <TableCell className="text-right">{v.count}</TableCell>
                          <TableCell className="text-right">₺{fmt(v.total)}</TableCell>
                        </TableRow>
                      ))
                    )}
                    <TableRow className="border-t-2">
                      <TableCell className="font-semibold">{t('cm.pages_TrialBalancePage.toplam_29757')}</TableCell>
                      <TableCell />
                      <TableCell className="text-right font-semibold text-blue-700">
                        ₺{fmt(data.payments.total)}
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>

          {/* Ledger durumu */}
          <Card>
            <CardHeader>
              <CardTitle>Defter Durumu</CardTitle>
              <CardDescription>{t('cm.pages_TrialBalancePage.ar_cari_depozito_ve_acik_folio_bakiyeler')}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <MetricCard
                  icon={Wallet}
                  label="AR Bakiyesi"
                  value={`₺${fmt(data.ledger.ar_balance)}`}
                  sub="Tahsil edilmemiş cari"
                  color={data.ledger.ar_balance > 0 ? "text-amber-600" : ""}
                />
                <MetricCard
                  icon={ArrowDownToLine}
                  label="Depozito Bakiyesi"
                  value={`₺${fmt(data.ledger.deposit_balance)}`}
                  sub="Henüz uygulanmamış depozit"
                />
                <MetricCard
                  icon={ClipboardCheck}
                  label={t('cm.pages_TrialBalancePage.acik_folio')}
                  value={data.ledger.open_folios}
                  sub="Kapanmamış folio sayısı"
                  color={data.ledger.open_folios > 0 ? "text-amber-600" : ""}
                />
              </div>
            </CardContent>
          </Card>

          <div className="text-xs text-muted-foreground text-right">
            {t('cm.pages_TrialBalancePage.uretildi')} {data.generated_at?.slice(0, 19).replace("T", " ")}
          </div>
        </>
      )}
    </div>
  );
}
