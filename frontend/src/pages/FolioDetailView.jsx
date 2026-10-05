import { useState, useEffect, useCallback } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { ArrowRightLeft, FileText, DollarSign, CreditCard, AlertTriangle, ShieldCheck, RefreshCw, Ban, Receipt, ArrowUpRight, Clock, Building2, Plus, Printer, Layers } from "lucide-react";
import { printFolio, printProformaInvoice } from "@/components/pms/PrintTemplates";
import { toast } from "sonner";
import FolioWindowsPanel from "@/components/folio/FolioWindowsPanel";
import { cachedTenantCurrency, formatCurrency } from "@/lib/currency";
import { moneyInputProps, parseMoneyInput } from '@/lib/moneyInput';
const API = "";

const CATEGORY_LABELS = {
  cash: "Nakit",
  card: "Kart",
  credit_card: "Kredi Kartı",
  bank_transfer: "Banka Transferi",
  room: "Konaklama",
  other: "Diğer"
};

const FOLIO_TYPE_LABELS = {
  guest: "Misafir hesabı",
  company: "Firma hesabı",
  agency: "Acente hesabı",
  master: "Ana hesap"
};

const AUDIT_ACTION_LABELS = {
  folio_created: "Folyo oluşturuldu",
  charge_added: "Masraf eklendi",
  charge_voided: "Masraf iptal edildi",
  payment_added: "Tahsilat kaydedildi",
  payment_voided: "Tahsilat iade edildi",
  folio_payment_voided: "Tahsilat iade edildi",
  folio_split: "Folyo paylaştırıldı",
  city_ledger_transfer: "Cari hesaba aktarıldı",
  night_audit_room_charge: "Konaklama ücreti işlendi"
};

function friendlyAuditAction(action) {
  return AUDIT_ACTION_LABELS[action] || "Folyo işlemi kaydedildi";
}

function friendlyEventTitle(event) {
  if (event.type === "refund") return "Ödeme iadesi";
  if (event.type === "payment") return `${CATEGORY_LABELS[event.category] || "Ödeme"} tahsilatı`;
  if (/^room charge/i.test(event.description || "")) return "Konaklama ücreti";
  return event.description || "Folyo işlemi";
}

function friendlyDateTime(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value).slice(0, 19).replace("T", " ");
  return new Intl.DateTimeFormat("tr-TR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(parsed);
}
function TimelineItem({
  event,
  t,
  currency,
  onVoidPayment
}) {
  const typeConfig = {
    charge: {
      icon: Receipt,
      color: "text-amber-600",
      bg: "bg-amber-50",
      sign: "+"
    },
    payment: {
      icon: CreditCard,
      color: "text-emerald-600",
      bg: "bg-emerald-50",
      sign: "-"
    },
    refund: {
      icon: ArrowRightLeft,
      color: "text-red-600",
      bg: "bg-red-50",
      sign: "-"
    }
  };
  const cfg = typeConfig[event.type] || typeConfig.charge;
  const Icon = cfg.icon;
  return <div data-testid={`timeline-item-${event.id?.slice(0, 8)}`} className={`flex items-start gap-3 rounded-xl border p-4 transition-colors ${event.voided ? "border-gray-200 bg-gray-50/80" : "border-gray-100 bg-white hover:border-gray-200"}`}>
      <div className={`p-2 rounded-lg ${cfg.bg} mt-0.5`}>
        <Icon className={`w-4 h-4 ${cfg.color}`} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className={`text-sm font-semibold ${event.voided ? "text-gray-500" : "text-gray-800"}`}>{friendlyEventTitle(event)}</span>
            {event.voided && <Badge variant="destructive" className="text-xs">{t("folio.voided")}</Badge>}
            {event.category && <Badge variant="outline" className="text-xs text-gray-500 border-gray-200">{CATEGORY_LABELS[event.category] || event.category}</Badge>}
          </div>
          <span className={`text-sm font-semibold ${event.voided ? "text-gray-400 line-through" : cfg.color}`}>
            {cfg.sign}{formatCurrency(Math.abs(event.display_amount ?? event.amount ?? 0), event.display_currency || event.currency || currency)}
          </span>
        </div>
        <div className="flex items-center justify-between mt-1">
          <span className="text-xs text-gray-400">{friendlyDateTime(event.timestamp)}</span>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">{t("folio.balance")}: {formatCurrency(event.running_balance || 0, currency)}</span>
            {event.type === "payment" && !event.voided && onVoidPayment && <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 border-red-200 px-2 text-xs text-red-700 hover:bg-red-50"
              onClick={() => onVoidPayment(event)}
            >
              <Ban className="mr-1 h-3 w-3" /> İade
            </Button>}
          </div>
        </div>
        {event.voided && event.void_reason && <div className="mt-1.5 text-xs bg-red-50 border border-red-200 rounded px-2 py-1">
            <span className="text-red-600 font-medium">{t("folio.reason")}: </span>
            <span className="text-red-500">{event.void_reason}</span>
          </div>}
        {event.type === "payment" && event.received_currency && !event.voided && <div className="mt-1 text-xs font-semibold text-emerald-700">
            Alınan: {formatCurrency(event.received_amount ?? event.amount, event.received_currency)}
            {event.exchange_rate && Number(event.exchange_rate) !== 1 ? ` · Kur ${Number(event.exchange_rate).toFixed(4)}` : ""}
          </div>}
      </div>
    </div>;
}
function TaxBreakdownTable({
  taxData,
  t,
  currency,
}) {
  if (!taxData?.lines?.length) return <p className="text-sm text-gray-400 py-4">{t("folio.noTaxData")}</p>;
  return <div data-testid="tax-breakdown-table">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-200">
            <th className="text-left py-2 text-gray-500 font-medium">{t("folio.description")}</th>
            <th className="text-left py-2 text-gray-500 font-medium">{t("folio.category")}</th>
            <th className="text-right py-2 text-gray-500 font-medium">{t("folio.net")}</th>
            <th className="text-right py-2 text-gray-500 font-medium">{t("folio.taxRate")}</th>
            <th className="text-right py-2 text-gray-500 font-medium">{t("folio.tax")}</th>
            <th className="text-right py-2 text-gray-500 font-medium">{t("folio.gross")}</th>
          </tr>
        </thead>
        <tbody>
          {taxData.lines.map((l, i) => <tr key={l.id || i} className="border-b border-gray-100">
              <td className="py-1.5 text-gray-700">{l.description?.slice(0, 40)}</td>
              <td className="py-1.5 text-gray-500">{l.category}</td>
              <td className="py-1.5 text-right text-gray-700">{formatCurrency(l.net_amount || 0, l.currency || currency)}</td>
              <td className="py-1.5 text-right text-gray-500">{l.tax_rate}%</td>
              <td className="py-1.5 text-right text-amber-600">{formatCurrency(l.tax_amount || 0, l.currency || currency)}</td>
              <td className="py-1.5 text-right text-gray-800 font-medium">{formatCurrency(l.gross_amount || 0, l.currency || currency)}</td>
            </tr>)}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-gray-300">
            <td colSpan={2} className="py-2 text-gray-800 font-semibold">{t("folio.total")}</td>
            <td className="py-2 text-right text-gray-800 font-semibold">{formatCurrency(taxData.totals?.net || 0, currency)}</td>
            <td></td>
            <td className="py-2 text-right text-amber-600 font-semibold">{formatCurrency(taxData.totals?.tax || 0, currency)}</td>
            <td className="py-2 text-right text-gray-900 font-bold">{formatCurrency(taxData.totals?.gross || 0, currency)}</td>
          </tr>
        </tfoot>
      </table>
      {taxData.by_tax_rate && Object.keys(taxData.by_tax_rate).length > 0 && <div className="mt-3 flex flex-wrap gap-2">
          {Object.entries(taxData.by_tax_rate).map(([rate, data]) => <div key={rate} className="bg-gray-50 border border-gray-200 rounded px-3 py-1.5 text-xs">
              <span className="text-gray-500">{rate}:</span>
              <span className="text-amber-600 ml-1">{formatCurrency(data.tax || 0, currency)} {t("folio.tax").toLowerCase()}</span>
              <span className="text-gray-400 ml-1">({data.count} {t("folio.items")})</span>
            </div>)}
        </div>}
    </div>;
}
function SplitFolioInfo({
  splitInfo,
  t,
  currency,
}) {
  if (!splitInfo?.has_splits) return <p className="text-sm text-gray-400 py-4">{t("folio.noSplitOperations")}</p>;
  return <div data-testid="split-folio-info" className="space-y-3">
      {splitInfo.split_from_operations?.map((op, i) => <div key={i} className="flex items-center gap-2 p-2 rounded bg-gray-50 border border-gray-200 text-xs">
          <ArrowUpRight className="w-3.5 h-3.5 text-blue-500" />
          <span className="text-gray-700">{t("folio.splitCharges", {
          count: op.charge_ids?.length
        })}</span>
          <span className="text-gray-500">{formatCurrency(op.amount || 0, op.currency || currency)}</span>
          <span className="text-gray-400">- {op.reason}</span>
        </div>)}
      {splitInfo.related_folios?.map(f => <div key={f.id} className="flex items-center justify-between p-2 rounded bg-gray-50 border border-gray-200 text-xs">
          <div className="flex items-center gap-2">
            <FileText className="w-3.5 h-3.5 text-gray-400" />
            <span className="text-gray-700">{f.folio_number}</span>
            <Badge variant="outline" className="text-xs">{FOLIO_TYPE_LABELS[f.folio_type] || "Bağlı hesap"}</Badge>
          </div>
          <div className="flex items-center gap-2">
            <Badge className={f.status === "open" ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-600"}>{f.status === "open" ? "Aktif" : "Kapalı"}</Badge>
            <span className="text-gray-700">{formatCurrency(f.balance || 0, f.currency || currency)}</span>
          </div>
        </div>)}
    </div>;
}
function VoidDetailsPanel({
  voidDetails,
  t,
  currency,
}) {
  if (!voidDetails?.length) return <p className="text-sm text-gray-400 py-4">{t("folio.noVoidOperations")}</p>;
  return <div data-testid="void-details-panel" className="space-y-2">
      {voidDetails.map((v, i) => <div key={v.id || i} className="p-2.5 rounded-lg bg-red-50 border border-red-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Ban className="w-3.5 h-3.5 text-red-500" />
              <span className="text-xs font-medium text-red-600">{v.type === "charge_void" ? t("folio.chargeVoid") : t("folio.paymentVoid")}</span>
              {v.is_supervisor_override && <Badge className="text-xs bg-amber-100 text-amber-700">{t("folio.supervisorOverride")}</Badge>}
            </div>
            <span className="text-xs text-red-500">{formatCurrency(v.original_amount || 0, v.currency || currency)}</span>
          </div>
          <p className="text-xs text-gray-500 mt-1">{v.description}</p>
          <div className="flex items-center gap-2 mt-1 text-xs text-gray-400">
            <span>{t("folio.reason")}: {v.void_reason}</span>
            {v.voided_at && <span>· {friendlyDateTime(v.voided_at)}</span>}
          </div>
        </div>)}
    </div>;
}

// Folio records can use legacy Mongo ObjectIds or the UUID identifiers emitted
// by the current PMS folio service.
const OBJECT_ID_RE = /^[a-f0-9]{24}$/i;
const UUID_RE = /^[a-f0-9]{8}-[a-f0-9]{4}-[1-8][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i;

export function isSupportedFolioId(value) {
  const id = String(value || "").trim();
  return OBJECT_ID_RE.test(id) || UUID_RE.test(id);
}

export default function FolioDetailView({
  user,
  tenant,
  onLogout,
  folioId: propFolioId,
  onClose
}) {
  const {
    folioId: paramFolioId
  } = useParams();
  const {
    t
  } = useTranslation();
  const [folioId, setFolioId] = useState(propFolioId || paramFolioId || "");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState("timeline");
  const [notFound, setNotFound] = useState(false);
  const [notFoundReason, setNotFoundReason] = useState(""); // 'invalid_format' | 'not_found' | 'forbidden'

  const [showChargeForm, setShowChargeForm] = useState(false);
  const [chargeForm, setChargeForm] = useState({
    description: "",
    amount: "",
    category: "room",
    quantity: 1
  });
  const [chargeLoading, setChargeLoading] = useState(false);
  const [voidTarget, setVoidTarget] = useState(null);
  const [voidReason, setVoidReason] = useState("");
  const [supervisorPin, setSupervisorPin] = useState("");
  const [voidLoading, setVoidLoading] = useState(false);
  const fetchDetail = useCallback(async id => {
    if (!id) return;
    setNotFound(false);
    setNotFoundReason("");
    // Reject malformed external input before it reaches the backend while
    // accepting both identifier formats persisted by the PMS.
    // (P2 cleanup — sahte/yanıltıcı sayfa shell render etmesin).
    // Mevcut `data` sadece kesin NotFound (invalid format / 404 / 401 / 403) durumunda
    // veya başarılı fetch'te değişir; transient 5xx/network hatasında önceki folio
    // ekrandan kaybolmaz (refresh sırasında boş shell regression riski yok).
    if (!isSupportedFolioId(id)) {
      setData(null);
      setNotFound(true);
      setNotFoundReason("invalid_format");
      return;
    }
    setLoading(true);
    try {
      const {
        data: d
      } = await axios.get(`/pms-core/folio/detail/${id}`, {
        headers: {}
      });
      setData(d);
    } catch (e) {
      const status = e?.response?.status;
      if (status === 404) {
        setData(null);
        setNotFound(true);
        setNotFoundReason("not_found");
      } else if (status === 403 || status === 401) {
        setData(null);
        setNotFound(true);
        setNotFoundReason("forbidden");
      } else {
        // Transient (5xx / network): mevcut data'yı koru, sadece toast
        toast.error(e?.response?.data?.detail || t("folio.failedToLoad"));
      }
    } finally {
      setLoading(false);
    }
  }, [t]);
  useEffect(() => {
    const id = propFolioId || paramFolioId;
    if (id) fetchDetail(id);
  }, [propFolioId, paramFolioId, fetchDetail]);
  const summary = data?.summary;
  const folio = data?.folio;
  const currency = folio?.currency || data?.currency || tenant?.currency || cachedTenantCurrency();
  const content = <div data-testid="folio-detail-view" className="max-w-[1400px] mx-auto px-4 py-6">
      {!propFolioId && <div className="mb-5 flex items-center gap-3 rounded-xl border border-gray-100 bg-white/70 p-3 shadow-sm">
          <div className="min-w-0 flex-1">
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-400">Folyo görüntüle</p>
            <input data-testid="folio-search-input" type="text" aria-label="Folyo numarası veya kayıt kodu" placeholder="Folyo numarası veya kayıt kodu" value={folioId} onChange={e => setFolioId(e.target.value)} className="w-full bg-transparent text-sm text-gray-700 outline-none" />
          </div>
          <Button data-testid="folio-search-btn" onClick={() => fetchDetail(folioId)} disabled={!folioId || loading} className="bg-blue-600 hover:bg-blue-700 text-white">
            {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : "Görüntüle"}
          </Button>
          {onClose && <Button variant="ghost" onClick={onClose}>{t("folio.close")}</Button>}
        </div>}

      {loading && !data && <div className="flex items-center justify-center py-20">
          <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
        </div>}

      {notFound && !loading && <Card data-testid="folio-not-found" className="bg-white border-gray-200 shadow-sm max-w-xl mx-auto mt-12">
          <CardContent className="py-10 px-6 text-center">
            <AlertTriangle className="w-10 h-10 text-amber-500 mx-auto mb-3" />
            <h2 className="text-lg font-semibold text-gray-800 mb-2">
              {notFoundReason === "forbidden" ? "Erişim yetkisi yok" : "Folio bulunamadı"}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {notFoundReason === "invalid_format" && "Geçersiz folio kimliği formatı."}
              {notFoundReason === "not_found" && "Bu ID ile bir folio kaydı bulunamadı veya farklı bir tenant'a ait."}
              {notFoundReason === "forbidden" && "Bu folioyu görüntüleme yetkiniz yok (403)."}
            </p>
            {!propFolioId && <Button variant="outline" size="sm" onClick={() => {
          setNotFound(false);
          setFolioId("");
        }}>
                Yeni arama
              </Button>}
          </CardContent>
        </Card>}

      {data && !notFound && <>
          <div className="mb-5 flex flex-col gap-4 rounded-2xl border border-slate-100 bg-gradient-to-r from-slate-50 via-white to-blue-50/50 p-5 shadow-sm md:flex-row md:items-center md:justify-between">
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-[0.16em] text-blue-600">Misafir hesabı</p>
              <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
                <span className="rounded-lg bg-blue-600 p-2 text-white"><FileText className="h-5 w-5" /></span>
                Folyo {folio?.folio_number || folioId?.slice(0, 8)}
              </h1>
              <div className="flex items-center gap-3 mt-1">
                <Badge className={folio?.status === "open" ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-600"}>{folio?.status === "open" ? "Aktif" : "Kapalı"}</Badge>
                <span className="text-xs text-gray-500">Rezervasyona bağlı misafir folyosu</span>
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowChargeForm(true)}
                disabled={folio?.status !== "open"}
                title={folio?.status !== "open" ? "Kapalı folyoya masraf eklenemez" : undefined}
                className="border-emerald-200 text-emerald-700 hover:bg-emerald-50"
              >
                <Plus className="w-4 h-4 mr-2" /> Masraf Ekle
              </Button>
              <Button variant="outline" size="sm" onClick={() => printFolio(data, tenant)} className="border-blue-200 text-blue-700 hover:bg-blue-50">
                <Printer className="w-4 h-4 mr-2" /> Yazdır
              </Button>
              <Button variant="outline" size="sm" onClick={() => printProformaInvoice({
            ...folio,
            total_amount: summary?.total_charges
          }, null, [], tenant)} className="border-indigo-200 text-indigo-700 hover:bg-indigo-50">
                <FileText className="w-4 h-4 mr-2" /> Proforma
              </Button>
              <Button variant="outline" size="sm" onClick={() => fetchDetail(propFolioId || folioId)} className="border-gray-200">
                <RefreshCw className="w-4 h-4 mr-2" /> {t("folio.refresh")}
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 mb-6 md:grid-cols-5">
            <Card className="border-amber-100 bg-gradient-to-br from-white to-amber-50/60 shadow-sm"><CardContent className="p-4">
              <p className="text-xs text-gray-500">{t("folio.totalCharges")}</p>
              <p className="text-lg font-bold text-amber-600">{formatCurrency(summary?.total_charges || 0, currency)}</p>
              <p className="text-xs text-gray-400">{summary?.charge_count} {t("folio.items")}</p>
            </CardContent></Card>
            <Card className="border-emerald-100 bg-gradient-to-br from-white to-emerald-50/60 shadow-sm"><CardContent className="p-4">
              <p className="text-xs text-gray-500">{t("folio.totalPayments")}</p>
              <p className="text-lg font-bold text-emerald-600">{formatCurrency(summary?.total_payments || 0, currency)}</p>
              <p className="text-xs text-gray-400">{summary?.payment_count} {t("folio.items")}</p>
            </CardContent></Card>
            <Card className="border-blue-100 bg-gradient-to-br from-white to-blue-50/70 shadow-sm"><CardContent className="p-4">
              <p className="text-xs text-gray-500">{t("folio.balance")}</p>
              <p className={`text-lg font-bold ${(summary?.balance || 0) > 0 ? "text-red-600" : "text-emerald-600"}`}>{formatCurrency(summary?.balance || 0, currency)}</p>
            </CardContent></Card>
            <Card className="border-gray-100 bg-white shadow-sm"><CardContent className="p-4">
              <p className="text-xs text-gray-500">{t("folio.voidedCharges")}</p>
              <p className="text-lg font-bold text-gray-500">{summary?.voided_charges || 0}</p>
            </CardContent></Card>
            <Card className="border-gray-100 bg-white shadow-sm"><CardContent className="p-4">
              <p className="text-xs text-gray-500">{t("folio.voidedPayments")}</p>
              <p className="text-lg font-bold text-gray-500">{summary?.voided_payments || 0}</p>
            </CardContent></Card>
          </div>

          <Tabs value={tab} onValueChange={setTab}>
            <TabsList className="mb-4 h-auto max-w-full flex-wrap justify-start gap-1 rounded-xl border border-gray-100 bg-white p-1.5 shadow-sm">
              <TabsTrigger data-testid="folio-tab-timeline" value="timeline" className="data-[state=active]:bg-blue-50 data-[state=active]:text-blue-700">
                <Clock className="w-3.5 h-3.5 mr-1.5" /> {t("folio.timeline")}
              </TabsTrigger>
              <TabsTrigger data-testid="folio-tab-tax" value="tax" className="data-[state=active]:bg-blue-50 data-[state=active]:text-blue-700">
                <DollarSign className="w-3.5 h-3.5 mr-1.5" /> Vergi Detayı
              </TabsTrigger>
              <TabsTrigger data-testid="folio-tab-splits" value="splits" className="data-[state=active]:bg-blue-50 data-[state=active]:text-blue-700">
                <ArrowRightLeft className="w-3.5 h-3.5 mr-1.5" /> Folyo Paylaşımı
              </TabsTrigger>
              <TabsTrigger data-testid="folio-tab-voids" value="voids" className="data-[state=active]:bg-blue-50 data-[state=active]:text-blue-700">
                <Ban className="w-3.5 h-3.5 mr-1.5" /> {t("folio.voids")}
              </TabsTrigger>
              <TabsTrigger data-testid="folio-tab-city-ledger" value="city-ledger" className="data-[state=active]:bg-blue-50 data-[state=active]:text-blue-700">
                <Building2 className="w-3.5 h-3.5 mr-1.5" /> Cari Aktarımlar
              </TabsTrigger>
              <TabsTrigger data-testid="folio-tab-audit" value="audit" className="data-[state=active]:bg-blue-50 data-[state=active]:text-blue-700">
                <ShieldCheck className="w-3.5 h-3.5 mr-1.5" /> İşlem Geçmişi
              </TabsTrigger>
              <TabsTrigger data-testid="folio-tab-windows" value="windows" className="data-[state=active]:bg-blue-50 data-[state=active]:text-blue-700">
                <Layers className="w-3.5 h-3.5 mr-1.5" /> Hesap Dağılımı
              </TabsTrigger>
            </TabsList>

            <TabsContent value="windows">
              <FolioWindowsPanel bookingId={folio?.booking_id} currentFolioId={folio?.id} />
            </TabsContent>

            <TabsContent value="timeline">
              <Card className="overflow-hidden border-gray-100 bg-white shadow-sm">
                <CardHeader className="border-b border-gray-50 bg-slate-50/50 px-5 py-4"><CardTitle className="text-sm font-semibold text-gray-700">Hesap hareketleri <span className="ml-1 font-normal text-gray-400">· {data?.timeline?.length || 0} işlem</span></CardTitle></CardHeader>
                <CardContent className="px-4 pb-4">
                  <div className="mt-4 space-y-3 max-h-[600px] overflow-y-auto pr-1">
                    {data?.timeline?.length ? data.timeline.map(e => <TimelineItem key={e.id} event={e} t={t} currency={currency} onVoidPayment={setVoidTarget} />) : <p className="text-sm text-gray-400 py-4">{t("folio.noTransactions")}</p>}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="tax">
              <Card className="bg-white border-gray-200 shadow-sm">
                <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-gray-500">{t("folio.lineLevelTaxBreakdown")}</CardTitle></CardHeader>
                <CardContent className="px-4 pb-4"><TaxBreakdownTable taxData={data?.tax_breakdown} t={t} currency={currency} /></CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="splits">
              <Card className="bg-white border-gray-200 shadow-sm">
                <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-gray-500">{t("folio.splitFolioOperations")}</CardTitle></CardHeader>
                <CardContent className="px-4 pb-4"><SplitFolioInfo splitInfo={data?.split_folio_info} t={t} currency={currency} /></CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="voids">
              <Card className="bg-white border-gray-200 shadow-sm">
                <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-gray-500">{t("folio.voidReversalDetails")}</CardTitle></CardHeader>
                <CardContent className="px-4 pb-4"><VoidDetailsPanel voidDetails={data?.void_details} t={t} currency={currency} /></CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="city-ledger">
              <Card className="bg-white border-gray-200 shadow-sm">
                <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-gray-500">{t("folio.cityLedgerTransferHistory")}</CardTitle></CardHeader>
                <CardContent className="px-4 pb-4">
                  {data?.city_ledger_history?.length ? <div className="space-y-2">
                      {(data.city_ledger_history || []).map((tr, i) => <div key={tr.id || i} className="flex items-center justify-between p-2 rounded bg-gray-50 border border-gray-200 text-xs">
                          <div>
                            <span className="text-gray-700">{tr.description?.slice(0, 60)}</span>
                            <p className="text-gray-400">{friendlyDateTime(tr.transaction_date)}</p>
                          </div>
                          <span className="text-amber-600 font-medium">{formatCurrency(tr.amount || 0, tr.currency || currency)}</span>
                        </div>)}
                    </div> : <p className="text-sm text-gray-400 py-4">{t("folio.noCityLedgerTransfers")}</p>}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="audit">
              <Card className="bg-white border-gray-200 shadow-sm">
                <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-gray-500">{t("folio.folioAuditTrail")}</CardTitle></CardHeader>
                <CardContent className="px-4 pb-4">
                  {data?.audit_trail?.length ? <div className="space-y-2 max-h-96 overflow-y-auto">
                      {(data.audit_trail || []).map((e, i) => <div key={e.id || i} className="text-xs bg-gray-50 p-2 rounded border border-gray-200 flex items-start gap-2">
                          <ShieldCheck className="w-3.5 h-3.5 text-gray-400 mt-0.5 shrink-0" />
                          <div>
                            <span className="text-gray-700 font-medium">{friendlyAuditAction(e.action)}</span>
                            <p className="text-gray-400">{friendlyDateTime(e.timestamp)}</p>
                          </div>
                        </div>)}
                    </div> : <p className="text-sm text-gray-400 py-4">{t("folio.noAuditEntries")}</p>}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>

          {data?.invoices?.length > 0 && <Card className="bg-white border-gray-200 shadow-sm mt-4">
              <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-gray-500">{t("folio.associatedInvoices")} ({data.invoices.length})</CardTitle></CardHeader>
              <CardContent className="px-4 pb-4">
                <div className="space-y-2">
                  {(data.invoices || []).map((inv, i) => <div key={inv.id || i} className="flex items-center justify-between p-2 rounded bg-gray-50 border border-gray-200 text-xs">
                      <div className="flex items-center gap-2">
                        <FileText className="w-3.5 h-3.5 text-gray-400" />
                        <span className="text-gray-700">{inv.invoice_number || inv.id?.slice(0, 8)}</span>
                        <Badge variant="outline" className="text-xs">{inv.status === "paid" ? "Ödendi" : inv.status === "cancelled" ? "İptal" : "Açık"}</Badge>
                      </div>
                      <span className="text-gray-700">{inv.total_amount == null ? "-" : formatCurrency(inv.total_amount, inv.currency || currency)}</span>
                    </div>)}
                </div>
              </CardContent>
            </Card>}
        </>}
    </div>;
  const postCharge = async () => {
    if (!folio?.id || folio.status !== "open") {
      toast.error("Kapalı folyoya masraf eklenemez");
      setShowChargeForm(false);
      return;
    }
    const amount = parseMoneyInput(chargeForm.amount);
    if (!chargeForm.description || !Number.isFinite(amount) || amount < 0) {
      toast.error("Açıklama ve tutar zorunludur");
      return;
    }
    setChargeLoading(true);
    try {
      const idempotencyKey = window.crypto?.randomUUID?.() || `folio-charge-${Date.now()}`;
      const response = await axios.post(`/folio/${folio.id}/charge`, {
        charge_category: chargeForm.category,
        description: chargeForm.description,
        amount,
        quantity: parseInt(chargeForm.quantity) || 1
      }, {
        headers: { "Idempotency-Key": idempotencyKey }
      });
      if (!response?.data?.id) {
        throw new Error("CHARGE_WRITE_NOT_CONFIRMED");
      }
      toast.success("Masraf eklendi");
      setShowChargeForm(false);
      setChargeForm({
        description: "",
        amount: "",
        category: "room",
        quantity: 1
      });
      fetchDetail(propFolioId || folioId);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Masraf eklenemedi");
    }
    setChargeLoading(false);
  };
  const chargeFormPanel = showChargeForm && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md p-6 space-y-4">
        <h3 className="text-lg font-semibold flex items-center gap-2"><Plus className="w-5 h-5" /> Folyoya Masraf Ekle</h3>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-500">Kategori</label>
            <select className="w-full border rounded-md p-2 text-sm" value={chargeForm.category} onChange={e => setChargeForm(p => ({
            ...p,
            category: e.target.value
          }))}>
              <option value="room">Oda</option>
              <option value="food">Yiyecek & İçecek</option>
              <option value="minibar">Minibar</option>
              <option value="laundry">Çamaşırhane</option>
              <option value="spa">Spa</option>
              <option value="phone">Telefon</option>
              <option value="parking">Otopark</option>
              <option value="other">Diğer</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500">Açıklama</label>
            <input className="w-full border rounded-md p-2 text-sm" value={chargeForm.description} onChange={e => setChargeForm(p => ({
            ...p,
            description: e.target.value
          }))} placeholder="Minibar - Kola vb." />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-500">Tutar ({currency})</label>
              <input {...moneyInputProps} className="w-full border rounded-md p-2 text-sm" placeholder="Örn. 150,74" value={chargeForm.amount} onChange={e => setChargeForm(p => ({
              ...p,
              amount: e.target.value
            }))} />
            </div>
            <div>
              <label className="text-xs text-gray-500">Adet</label>
              <input type="number" min="1" className="w-full border rounded-md p-2 text-sm" value={chargeForm.quantity} onChange={e => setChargeForm(p => ({
              ...p,
              quantity: e.target.value
            }))} />
            </div>
          </div>
        </div>
        <div className="flex gap-2 justify-end">
          <Button variant="ghost" onClick={() => setShowChargeForm(false)}>İptal</Button>
          <Button onClick={postCharge} disabled={chargeLoading} className="bg-emerald-600 hover:bg-emerald-700 text-white">
            {chargeLoading ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />}
            Masraf Ekle
          </Button>
        </div>
      </div>
    </div>;
  const closeVoidPanel = () => {
    setVoidTarget(null);
    setVoidReason("");
    setSupervisorPin("");
  };
  const voidPayment = async () => {
    if (!folio?.id || !voidTarget?.id || !voidReason.trim() || !supervisorPin.trim()) {
      toast.error("İade nedeni ve yetkili PIN'i zorunludur");
      return;
    }
    setVoidLoading(true);
    try {
      await axios.post(
        "/cashier/peer-verify",
        { pin: supervisorPin.trim() },
        { _skipAuthRetry: true },
      );
      await axios.post(`/folio/${folio.id}/payment/${voidTarget.id}/void`, {
        reason: voidReason.trim()
      });
      toast.success("Ödeme iade edildi");
      closeVoidPanel();
      await fetchDetail(propFolioId || folioId);
    } catch (e) {
      if (e?.response?.status === 429) {
        toast.error(e.response?.data?.detail || "Çok fazla PIN denemesi, lütfen bekleyin");
      } else if (e?.response?.status === 401) {
        toast.error(e.response?.data?.detail || "PIN hatalı");
      } else {
        toast.error(e.response?.data?.detail || "İade tamamlanamadı; otomatik tekrar yapılmadı");
      }
      setSupervisorPin("");
    } finally {
      setVoidLoading(false);
    }
  };
  const voidPaymentPanel = voidTarget && <div role="dialog" aria-modal="true" aria-label="Ödeme İadesi" className="fixed inset-0 z-[80] flex items-center justify-center bg-black/40 px-4">
      <div className="w-full max-w-md space-y-4 rounded-xl bg-white p-6 shadow-2xl">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">Ödeme İadesi</h3>
          <p className="mt-1 text-sm text-gray-500">
            {voidTarget.method?.toUpperCase()} ödemesi {formatCurrency(Math.abs(voidTarget.amount || 0), voidTarget.currency || currency)} iade edilecek.
            {voidTarget.method === "cash" && " Nakit iadesi için açık vardiya gerekir."}
          </p>
        </div>
        <div>
          <label htmlFor="folio-void-reason" className="text-xs text-gray-600">İade Nedeni *</label>
          <textarea id="folio-void-reason" rows={3} className="mt-1 w-full rounded-md border p-2 text-sm" value={voidReason} onChange={e => setVoidReason(e.target.value)} placeholder="Ör: yanlış tutar" />
        </div>
        <div>
          <label htmlFor="folio-void-pin" className="text-xs text-gray-600">Yetkili PIN *</label>
          <input id="folio-void-pin" type="password" autoComplete="off" className="mt-1 w-full rounded-md border p-2 text-sm" value={supervisorPin} onChange={e => setSupervisorPin(e.target.value)} />
        </div>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={closeVoidPanel} disabled={voidLoading}>Vazgeç</Button>
          <Button type="button" className="bg-red-600 text-white hover:bg-red-700" onClick={voidPayment} disabled={voidLoading || !voidReason.trim() || !supervisorPin.trim()}>
            {voidLoading ? "İşleniyor..." : "İadeyi Onayla"}
          </Button>
        </div>
      </div>
    </div>;
  if (user && tenant) {
    return <>{content}{chargeFormPanel}{voidPaymentPanel}</>;
  }
  return <>{content}{chargeFormPanel}{voidPaymentPanel}</>;
}
