import { useState, useEffect, useCallback } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { useTranslation } from "react-i18next";
import Layout from "../components/Layout";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import {
  ArrowRightLeft, FileText, DollarSign, CreditCard, AlertTriangle,
  ShieldCheck, RefreshCw, Ban, Receipt, ArrowUpRight,
  Clock, Building2, Plus, Printer
} from "lucide-react";
import { printFolio, printProformaInvoice } from "@/components/pms/PrintTemplates";
import { toast } from "sonner";

const API = "";

function TimelineItem({ event, t }) {
  const typeConfig = {
    charge: { icon: Receipt, color: "text-amber-600", bg: "bg-amber-50", sign: "+" },
    payment: { icon: CreditCard, color: "text-emerald-600", bg: "bg-emerald-50", sign: "-" },
    refund: { icon: ArrowRightLeft, color: "text-red-600", bg: "bg-red-50", sign: "-" },
  };
  const cfg = typeConfig[event.type] || typeConfig.charge;
  const Icon = cfg.icon;
  return (
    <div data-testid={`timeline-item-${event.id?.slice(0, 8)}`}
      className={`flex items-start gap-3 p-3 rounded-lg border ${event.voided ? "opacity-50 border-gray-200 bg-gray-50" : "border-gray-200 bg-white"}`}>
      <div className={`p-1.5 rounded-md ${cfg.bg} mt-0.5`}>
        <Icon className={`w-4 h-4 ${cfg.color}`} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-800">{event.description || event.type}</span>
            {event.voided && <Badge variant="destructive" className="text-xs">{t("folio.voided")}</Badge>}
            {event.category && <Badge variant="outline" className="text-xs text-gray-500 border-gray-300">{event.category}</Badge>}
          </div>
          <span className={`text-sm font-semibold ${event.voided ? "text-gray-400 line-through" : cfg.color}`}>
            {cfg.sign}{Math.abs(event.amount || 0).toFixed(2)}
          </span>
        </div>
        <div className="flex items-center justify-between mt-1">
          <span className="text-xs text-gray-400">{event.timestamp?.slice(0, 19).replace("T", " ")}</span>
          <span className="text-xs text-gray-500">{t("folio.balance")}: {event.running_balance?.toFixed(2)}</span>
        </div>
        {event.voided && event.void_reason && (
          <div className="mt-1.5 text-xs bg-red-50 border border-red-200 rounded px-2 py-1">
            <span className="text-red-600 font-medium">{t("folio.reason")}: </span>
            <span className="text-red-500">{event.void_reason}</span>
            {event.voided_by && <span className="text-gray-400 ml-1">{t("folio.by")} {event.voided_by}</span>}
          </div>
        )}
      </div>
    </div>
  );
}

function TaxBreakdownTable({ taxData, t }) {
  if (!taxData?.lines?.length) return <p className="text-sm text-gray-400 py-4">{t("folio.noTaxData")}</p>;
  return (
    <div data-testid="tax-breakdown-table">
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
          {taxData.lines.map((l, i) => (
            <tr key={i} className="border-b border-gray-100">
              <td className="py-1.5 text-gray-700">{l.description?.slice(0, 40)}</td>
              <td className="py-1.5 text-gray-500">{l.category}</td>
              <td className="py-1.5 text-right text-gray-700">{l.net_amount?.toFixed(2)}</td>
              <td className="py-1.5 text-right text-gray-500">{l.tax_rate}%</td>
              <td className="py-1.5 text-right text-amber-600">{l.tax_amount?.toFixed(2)}</td>
              <td className="py-1.5 text-right text-gray-800 font-medium">{l.gross_amount?.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-gray-300">
            <td colSpan={2} className="py-2 text-gray-800 font-semibold">{t("folio.total")}</td>
            <td className="py-2 text-right text-gray-800 font-semibold">{taxData.totals?.net?.toFixed(2)}</td>
            <td></td>
            <td className="py-2 text-right text-amber-600 font-semibold">{taxData.totals?.tax?.toFixed(2)}</td>
            <td className="py-2 text-right text-gray-900 font-bold">{taxData.totals?.gross?.toFixed(2)}</td>
          </tr>
        </tfoot>
      </table>
      {taxData.by_tax_rate && Object.keys(taxData.by_tax_rate).length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {Object.entries(taxData.by_tax_rate).map(([rate, data]) => (
            <div key={rate} className="bg-gray-50 border border-gray-200 rounded px-3 py-1.5 text-xs">
              <span className="text-gray-500">{rate}:</span>
              <span className="text-amber-600 ml-1">{data.tax?.toFixed(2)} {t("folio.tax").toLowerCase()}</span>
              <span className="text-gray-400 ml-1">({data.count} {t("folio.items")})</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SplitFolioInfo({ splitInfo, t }) {
  if (!splitInfo?.has_splits) return <p className="text-sm text-gray-400 py-4">{t("folio.noSplitOperations")}</p>;
  return (
    <div data-testid="split-folio-info" className="space-y-3">
      {splitInfo.split_from_operations?.map((op, i) => (
        <div key={i} className="flex items-center gap-2 p-2 rounded bg-gray-50 border border-gray-200 text-xs">
          <ArrowUpRight className="w-3.5 h-3.5 text-blue-500" />
          <span className="text-gray-700">{t("folio.splitCharges", { count: op.charge_ids?.length })}</span>
          <span className="text-gray-500">{op.amount?.toFixed(2)}</span>
          <span className="text-gray-400">- {op.reason}</span>
        </div>
      ))}
      {splitInfo.related_folios?.map(f => (
        <div key={f.id} className="flex items-center justify-between p-2 rounded bg-gray-50 border border-gray-200 text-xs">
          <div className="flex items-center gap-2">
            <FileText className="w-3.5 h-3.5 text-gray-400" />
            <span className="text-gray-700">{f.folio_number}</span>
            <Badge variant="outline" className="text-xs">{f.folio_type}</Badge>
          </div>
          <div className="flex items-center gap-2">
            <Badge className={f.status === "open" ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-600"}>{f.status}</Badge>
            <span className="text-gray-700">{f.balance?.toFixed(2)}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function VoidDetailsPanel({ voidDetails, t }) {
  if (!voidDetails?.length) return <p className="text-sm text-gray-400 py-4">{t("folio.noVoidOperations")}</p>;
  return (
    <div data-testid="void-details-panel" className="space-y-2">
      {voidDetails.map((v, i) => (
        <div key={i} className="p-2.5 rounded-lg bg-red-50 border border-red-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Ban className="w-3.5 h-3.5 text-red-500" />
              <span className="text-xs font-medium text-red-600">{v.type === "charge_void" ? t("folio.chargeVoid") : t("folio.paymentVoid")}</span>
              {v.is_supervisor_override && <Badge className="text-xs bg-amber-100 text-amber-700">{t("folio.supervisorOverride")}</Badge>}
            </div>
            <span className="text-xs text-red-500">{v.original_amount?.toFixed(2)}</span>
          </div>
          <p className="text-xs text-gray-500 mt-1">{v.description}</p>
          <div className="flex items-center gap-2 mt-1 text-xs text-gray-400">
            <span>{t("folio.reason")}: {v.void_reason}</span>
            {v.voided_by && <span>| {t("folio.by")}: {v.voided_by}</span>}
            {v.voided_at && <span>| {v.voided_at?.slice(0, 19)}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function FolioDetailView({ user, tenant, onLogout, folioId: propFolioId, onClose }) {
  const { folioId: paramFolioId } = useParams();
  const { t } = useTranslation();
  const [folioId, setFolioId] = useState(propFolioId || paramFolioId || "");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState("timeline");
  const token = localStorage.getItem("token");
  const [showChargeForm, setShowChargeForm] = useState(false);
  const [chargeForm, setChargeForm] = useState({ description: "", amount: "", category: "room", quantity: 1 });
  const [chargeLoading, setChargeLoading] = useState(false);

  const fetchDetail = useCallback(async (id) => {
    if (!id) return;
    setLoading(true);
    try {
      const { data: d } = await axios.get(`/pms-core/folio/detail/${id}`, { headers: { Authorization: `Bearer ${token}` } });
      setData(d);
    } catch (e) { toast.error(e.response?.data?.detail || t("folio.failedToLoad")); }
    finally { setLoading(false); }
  }, [token, t]);

  useEffect(() => { 
    const id = propFolioId || paramFolioId;
    if (id) fetchDetail(id); 
  }, [propFolioId, paramFolioId, fetchDetail]);

  const summary = data?.summary;
  const folio = data?.folio;

  const content = (
    <div data-testid="folio-detail-view" className="max-w-[1400px] mx-auto px-4 py-6">
      {!propFolioId && (
        <div className="flex items-center gap-3 mb-6">
          <input data-testid="folio-search-input" type="text" placeholder={t("folio.enterFolioId")}
            value={folioId} onChange={e => setFolioId(e.target.value)}
            className="bg-white border border-gray-200 rounded-lg px-4 py-2 text-sm text-gray-700 w-96 focus:outline-none focus:ring-1 focus:ring-blue-500" />
          <Button data-testid="folio-search-btn" onClick={() => fetchDetail(folioId)} disabled={!folioId || loading}
            className="bg-blue-600 hover:bg-blue-700 text-white">
            {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : t("folio.loadFolio")}
          </Button>
          {onClose && <Button variant="ghost" onClick={onClose}>{t("folio.close")}</Button>}
        </div>
      )}

      {loading && !data && (
        <div className="flex items-center justify-center py-20">
          <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
        </div>
      )}

      {data && (
        <>
          <div className="flex items-start justify-between mb-6">
            <div>
              <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
                <FileText className="w-5 h-5 text-blue-600" />
                Folio {folio?.folio_number || folioId?.slice(0, 8)}
              </h1>
              <div className="flex items-center gap-3 mt-1">
                <Badge className={folio?.status === "open" ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-600"}>{folio?.status}</Badge>
                <Badge variant="outline" className="text-xs">{folio?.folio_type}</Badge>
                <span className="text-xs text-gray-500">{t("folio.booking")}: {folio?.booking_id?.slice(0, 8)}...</span>
              </div>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setShowChargeForm(true)} className="border-emerald-200 text-emerald-700 hover:bg-emerald-50">
                <Plus className="w-4 h-4 mr-2" /> Masraf Ekle
              </Button>
              <Button variant="outline" size="sm" onClick={() => printFolio(data, tenant)} className="border-blue-200 text-blue-700 hover:bg-blue-50">
                <Printer className="w-4 h-4 mr-2" /> Yazdir
              </Button>
              <Button variant="outline" size="sm" onClick={() => printProformaInvoice({ ...folio, total_amount: summary?.total_charges }, null, [], tenant)} className="border-purple-200 text-purple-700 hover:bg-purple-50">
                <FileText className="w-4 h-4 mr-2" /> Proforma
              </Button>
              <Button variant="outline" size="sm" onClick={() => fetchDetail(propFolioId || folioId)} className="border-gray-200">
                <RefreshCw className="w-4 h-4 mr-2" /> {t("folio.refresh")}
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
            <Card className="bg-white border-gray-200 shadow-sm"><CardContent className="p-3">
              <p className="text-xs text-gray-500">{t("folio.totalCharges")}</p>
              <p className="text-lg font-bold text-amber-600">{summary?.total_charges?.toFixed(2)}</p>
              <p className="text-xs text-gray-400">{summary?.charge_count} {t("folio.items")}</p>
            </CardContent></Card>
            <Card className="bg-white border-gray-200 shadow-sm"><CardContent className="p-3">
              <p className="text-xs text-gray-500">{t("folio.totalPayments")}</p>
              <p className="text-lg font-bold text-emerald-600">{summary?.total_payments?.toFixed(2)}</p>
              <p className="text-xs text-gray-400">{summary?.payment_count} {t("folio.items")}</p>
            </CardContent></Card>
            <Card className="bg-white border-gray-200 shadow-sm"><CardContent className="p-3">
              <p className="text-xs text-gray-500">{t("folio.balance")}</p>
              <p className={`text-lg font-bold ${(summary?.balance || 0) > 0 ? "text-red-600" : "text-emerald-600"}`}>{summary?.balance?.toFixed(2)}</p>
            </CardContent></Card>
            <Card className="bg-white border-gray-200 shadow-sm"><CardContent className="p-3">
              <p className="text-xs text-gray-500">{t("folio.voidedCharges")}</p>
              <p className="text-lg font-bold text-gray-500">{summary?.voided_charges || 0}</p>
            </CardContent></Card>
            <Card className="bg-white border-gray-200 shadow-sm"><CardContent className="p-3">
              <p className="text-xs text-gray-500">{t("folio.voidedPayments")}</p>
              <p className="text-lg font-bold text-gray-500">{summary?.voided_payments || 0}</p>
            </CardContent></Card>
          </div>

          <Tabs value={tab} onValueChange={setTab}>
            <TabsList className="bg-white border border-gray-200 mb-4">
              <TabsTrigger data-testid="folio-tab-timeline" value="timeline" className="data-[state=active]:bg-blue-50 data-[state=active]:text-blue-700">
                <Clock className="w-3.5 h-3.5 mr-1.5" /> {t("folio.timeline")}
              </TabsTrigger>
              <TabsTrigger data-testid="folio-tab-tax" value="tax" className="data-[state=active]:bg-blue-50 data-[state=active]:text-blue-700">
                <DollarSign className="w-3.5 h-3.5 mr-1.5" /> {t("folio.taxBreakdown")}
              </TabsTrigger>
              <TabsTrigger data-testid="folio-tab-splits" value="splits" className="data-[state=active]:bg-blue-50 data-[state=active]:text-blue-700">
                <ArrowRightLeft className="w-3.5 h-3.5 mr-1.5" /> {t("folio.splits")}
              </TabsTrigger>
              <TabsTrigger data-testid="folio-tab-voids" value="voids" className="data-[state=active]:bg-blue-50 data-[state=active]:text-blue-700">
                <Ban className="w-3.5 h-3.5 mr-1.5" /> {t("folio.voids")}
              </TabsTrigger>
              <TabsTrigger data-testid="folio-tab-city-ledger" value="city-ledger" className="data-[state=active]:bg-blue-50 data-[state=active]:text-blue-700">
                <Building2 className="w-3.5 h-3.5 mr-1.5" /> {t("folio.cityLedger")}
              </TabsTrigger>
              <TabsTrigger data-testid="folio-tab-audit" value="audit" className="data-[state=active]:bg-blue-50 data-[state=active]:text-blue-700">
                <ShieldCheck className="w-3.5 h-3.5 mr-1.5" /> {t("folio.audit")}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="timeline">
              <Card className="bg-white border-gray-200 shadow-sm">
                <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-gray-500">{t("folio.folioTimeline")} ({data?.timeline?.length || 0} {t("folio.events")})</CardTitle></CardHeader>
                <CardContent className="px-4 pb-4">
                  <div className="space-y-2 max-h-[600px] overflow-y-auto">
                    {data?.timeline?.length ? data.timeline.map(e => (
                      <TimelineItem key={e.id} event={e} t={t} />
                    )) : <p className="text-sm text-gray-400 py-4">{t("folio.noTransactions")}</p>}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="tax">
              <Card className="bg-white border-gray-200 shadow-sm">
                <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-gray-500">{t("folio.lineLevelTaxBreakdown")}</CardTitle></CardHeader>
                <CardContent className="px-4 pb-4"><TaxBreakdownTable taxData={data?.tax_breakdown} t={t} /></CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="splits">
              <Card className="bg-white border-gray-200 shadow-sm">
                <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-gray-500">{t("folio.splitFolioOperations")}</CardTitle></CardHeader>
                <CardContent className="px-4 pb-4"><SplitFolioInfo splitInfo={data?.split_folio_info} t={t} /></CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="voids">
              <Card className="bg-white border-gray-200 shadow-sm">
                <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-gray-500">{t("folio.voidReversalDetails")}</CardTitle></CardHeader>
                <CardContent className="px-4 pb-4"><VoidDetailsPanel voidDetails={data?.void_details} t={t} /></CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="city-ledger">
              <Card className="bg-white border-gray-200 shadow-sm">
                <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-gray-500">{t("folio.cityLedgerTransferHistory")}</CardTitle></CardHeader>
                <CardContent className="px-4 pb-4">
                  {data?.city_ledger_history?.length ? (
                    <div className="space-y-2">
                      {data.city_ledger_history.map((tr, i) => (
                        <div key={i} className="flex items-center justify-between p-2 rounded bg-gray-50 border border-gray-200 text-xs">
                          <div>
                            <span className="text-gray-700">{tr.description?.slice(0, 60)}</span>
                            <p className="text-gray-400">{tr.transaction_date?.slice(0, 19)}</p>
                          </div>
                          <span className="text-amber-600 font-medium">{tr.amount?.toFixed(2)}</span>
                        </div>
                      ))}
                    </div>
                  ) : <p className="text-sm text-gray-400 py-4">{t("folio.noCityLedgerTransfers")}</p>}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="audit">
              <Card className="bg-white border-gray-200 shadow-sm">
                <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-gray-500">{t("folio.folioAuditTrail")}</CardTitle></CardHeader>
                <CardContent className="px-4 pb-4">
                  {data?.audit_trail?.length ? (
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {data.audit_trail.map((e, i) => (
                        <div key={i} className="text-xs bg-gray-50 p-2 rounded border border-gray-200 flex items-start gap-2">
                          <ShieldCheck className="w-3.5 h-3.5 text-gray-400 mt-0.5 shrink-0" />
                          <div>
                            <span className="text-gray-700 font-medium">{e.action}</span>
                            {e.performed_by && <span className="text-gray-400 ml-1">{t("folio.by")} {e.performed_by?.slice(0, 8)}</span>}
                            <p className="text-gray-400">{e.timestamp?.slice(0, 19)}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : <p className="text-sm text-gray-400 py-4">{t("folio.noAuditEntries")}</p>}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>

          {data?.invoices?.length > 0 && (
            <Card className="bg-white border-gray-200 shadow-sm mt-4">
              <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-gray-500">{t("folio.associatedInvoices")} ({data.invoices.length})</CardTitle></CardHeader>
              <CardContent className="px-4 pb-4">
                <div className="space-y-2">
                  {data.invoices.map((inv, i) => (
                    <div key={i} className="flex items-center justify-between p-2 rounded bg-gray-50 border border-gray-200 text-xs">
                      <div className="flex items-center gap-2">
                        <FileText className="w-3.5 h-3.5 text-gray-400" />
                        <span className="text-gray-700">{inv.invoice_number || inv.id?.slice(0, 8)}</span>
                        <Badge variant="outline" className="text-xs">{inv.status}</Badge>
                      </div>
                      <span className="text-gray-700">{inv.total_amount?.toFixed(2) || "-"}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );

  const postCharge = async () => {
    if (!chargeForm.description || !chargeForm.amount) { toast.error("Açıklama ve tutar zorunludur"); return; }
    setChargeLoading(true);
    try {
      await axios.post(`/frontdesk/folio/${folio?.booking_id}/charge`, {
        charge_category: chargeForm.category,
        description: chargeForm.description,
        amount: parseFloat(chargeForm.amount) * (parseInt(chargeForm.quantity) || 1),
        quantity: parseInt(chargeForm.quantity) || 1,
      }, { headers: { Authorization: `Bearer ${token}` } });
      toast.success("Masraf eklendi");
      setShowChargeForm(false);
      setChargeForm({ description: "", amount: "", category: "room", quantity: 1 });
      fetchDetail(propFolioId || folioId);
    } catch (e) { toast.error(e.response?.data?.detail || "Masraf eklenemedi"); }
    setChargeLoading(false);
  };

  const chargeFormPanel = showChargeForm && (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md p-6 space-y-4">
        <h3 className="text-lg font-semibold flex items-center gap-2"><Plus className="w-5 h-5" /> Folioya Masraf Ekle</h3>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-500">Kategori</label>
            <select className="w-full border rounded-md p-2 text-sm" value={chargeForm.category} onChange={e => setChargeForm(p => ({ ...p, category: e.target.value }))}>
              <option value="room">Oda</option>
              <option value="food">Yiyecek & Icecek</option>
              <option value="minibar">Minibar</option>
              <option value="laundry">Camasirhane</option>
              <option value="spa">Spa</option>
              <option value="phone">Telefon</option>
              <option value="parking">Otopark</option>
              <option value="other">Diger</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500">Açıklama</label>
            <input className="w-full border rounded-md p-2 text-sm" value={chargeForm.description} onChange={e => setChargeForm(p => ({ ...p, description: e.target.value }))} placeholder="Minibar - Kola vb." />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-500">Tutar (TL)</label>
              <input type="number" className="w-full border rounded-md p-2 text-sm" value={chargeForm.amount} onChange={e => setChargeForm(p => ({ ...p, amount: e.target.value }))} />
            </div>
            <div>
              <label className="text-xs text-gray-500">Adet</label>
              <input type="number" min="1" className="w-full border rounded-md p-2 text-sm" value={chargeForm.quantity} onChange={e => setChargeForm(p => ({ ...p, quantity: e.target.value }))} />
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
    </div>
  );

  if (user && tenant) {
    return <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="folio_detail">{content}{chargeFormPanel}</Layout>;
  }
  return <>{content}{chargeFormPanel}</>;
}
