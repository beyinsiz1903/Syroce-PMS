import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import {
  ArrowRightLeft, FileText, DollarSign, CreditCard, AlertTriangle,
  ShieldCheck, RefreshCw, Ban, Receipt, ArrowUpRight,
  ChevronDown, ChevronUp, Clock, Building2
} from "lucide-react";
import { toast } from "sonner";

const API = process.env.REACT_APP_BACKEND_URL;

/* ─── TIMELINE ITEM ─── */
function TimelineItem({ event }) {
  const typeConfig = {
    charge: { icon: Receipt, color: "text-amber-400", bg: "bg-amber-500/10", sign: "+" },
    payment: { icon: CreditCard, color: "text-emerald-400", bg: "bg-emerald-500/10", sign: "-" },
    refund: { icon: ArrowRightLeft, color: "text-red-400", bg: "bg-red-500/10", sign: "-" },
  };
  const cfg = typeConfig[event.type] || typeConfig.charge;
  const Icon = cfg.icon;

  return (
    <div data-testid={`timeline-item-${event.id?.slice(0, 8)}`}
      className={`flex items-start gap-3 p-3 rounded-lg border ${event.voided ? "opacity-50 border-slate-700/30 bg-slate-900/30" : "border-slate-700/50 bg-slate-800/40"}`}>
      <div className={`p-1.5 rounded-md ${cfg.bg} mt-0.5`}>
        <Icon className={`w-4 h-4 ${cfg.color}`} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-slate-200">{event.description || event.type}</span>
            {event.voided && <Badge variant="destructive" className="text-xs">VOIDED</Badge>}
            {event.category && <Badge variant="outline" className="text-xs text-slate-400 border-slate-600">{event.category}</Badge>}
          </div>
          <span className={`text-sm font-semibold ${event.voided ? "text-slate-500 line-through" : cfg.color}`}>
            {cfg.sign}{Math.abs(event.amount || 0).toFixed(2)}
          </span>
        </div>
        <div className="flex items-center justify-between mt-1">
          <span className="text-xs text-slate-500">{event.timestamp?.slice(0, 19).replace("T", " ")}</span>
          <span className="text-xs text-slate-400">Balance: {event.running_balance?.toFixed(2)}</span>
        </div>
        {event.voided && event.void_reason && (
          <div className="mt-1.5 text-xs bg-red-950/30 border border-red-800/30 rounded px-2 py-1">
            <span className="text-red-400 font-medium">Void: </span>
            <span className="text-red-300">{event.void_reason}</span>
            {event.voided_by && <span className="text-slate-500 ml-1">by {event.voided_by}</span>}
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── TAX BREAKDOWN TABLE ─── */
function TaxBreakdownTable({ taxData }) {
  if (!taxData?.lines?.length) return <p className="text-sm text-slate-500 py-4">No tax data</p>;
  return (
    <div data-testid="tax-breakdown-table">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-slate-700">
            <th className="text-left py-2 text-slate-400 font-medium">Description</th>
            <th className="text-left py-2 text-slate-400 font-medium">Category</th>
            <th className="text-right py-2 text-slate-400 font-medium">Net</th>
            <th className="text-right py-2 text-slate-400 font-medium">Tax Rate</th>
            <th className="text-right py-2 text-slate-400 font-medium">Tax</th>
            <th className="text-right py-2 text-slate-400 font-medium">Gross</th>
          </tr>
        </thead>
        <tbody>
          {taxData.lines.map((l, i) => (
            <tr key={i} className="border-b border-slate-800/50">
              <td className="py-1.5 text-slate-300">{l.description?.slice(0, 40)}</td>
              <td className="py-1.5 text-slate-500">{l.category}</td>
              <td className="py-1.5 text-right text-slate-300">{l.net_amount?.toFixed(2)}</td>
              <td className="py-1.5 text-right text-slate-500">{l.tax_rate}%</td>
              <td className="py-1.5 text-right text-amber-400">{l.tax_amount?.toFixed(2)}</td>
              <td className="py-1.5 text-right text-slate-200 font-medium">{l.gross_amount?.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-slate-600">
            <td colSpan={2} className="py-2 text-slate-300 font-semibold">Total</td>
            <td className="py-2 text-right text-slate-200 font-semibold">{taxData.totals?.net?.toFixed(2)}</td>
            <td></td>
            <td className="py-2 text-right text-amber-400 font-semibold">{taxData.totals?.tax?.toFixed(2)}</td>
            <td className="py-2 text-right text-slate-100 font-bold">{taxData.totals?.gross?.toFixed(2)}</td>
          </tr>
        </tfoot>
      </table>

      {/* By Tax Rate Summary */}
      {taxData.by_tax_rate && Object.keys(taxData.by_tax_rate).length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {Object.entries(taxData.by_tax_rate).map(([rate, data]) => (
            <div key={rate} className="bg-slate-800/50 border border-slate-700/50 rounded px-3 py-1.5 text-xs">
              <span className="text-slate-400">{rate}:</span>
              <span className="text-amber-400 ml-1">{data.tax?.toFixed(2)} tax</span>
              <span className="text-slate-500 ml-1">({data.count} items)</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── SPLIT FOLIO INFO ─── */
function SplitFolioInfo({ splitInfo }) {
  if (!splitInfo?.has_splits) return <p className="text-sm text-slate-500 py-4">No split operations</p>;
  return (
    <div data-testid="split-folio-info" className="space-y-3">
      {splitInfo.split_from_operations?.map((op, i) => (
        <div key={i} className="flex items-center gap-2 p-2 rounded bg-slate-800/40 border border-slate-700/40 text-xs">
          <ArrowUpRight className="w-3.5 h-3.5 text-blue-400" />
          <span className="text-slate-300">Split {op.charge_ids?.length} charges to new folio</span>
          <span className="text-slate-500">{op.amount?.toFixed(2)}</span>
          <span className="text-slate-600">- {op.reason}</span>
        </div>
      ))}
      {splitInfo.related_folios?.map(f => (
        <div key={f.id} className="flex items-center justify-between p-2 rounded bg-slate-800/40 border border-slate-700/40 text-xs">
          <div className="flex items-center gap-2">
            <FileText className="w-3.5 h-3.5 text-slate-500" />
            <span className="text-slate-300">{f.folio_number}</span>
            <Badge variant="outline" className="text-xs">{f.folio_type}</Badge>
          </div>
          <div className="flex items-center gap-2">
            <Badge className={f.status === "open" ? "bg-emerald-500/20 text-emerald-400" : "bg-slate-500/20 text-slate-400"}>{f.status}</Badge>
            <span className="text-slate-300">{f.balance?.toFixed(2)}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ─── VOID DETAILS ─── */
function VoidDetailsPanel({ voidDetails }) {
  if (!voidDetails?.length) return <p className="text-sm text-slate-500 py-4">No void/reversal operations</p>;
  return (
    <div data-testid="void-details-panel" className="space-y-2">
      {voidDetails.map((v, i) => (
        <div key={i} className="p-2.5 rounded-lg bg-red-950/20 border border-red-800/30">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Ban className="w-3.5 h-3.5 text-red-400" />
              <span className="text-xs font-medium text-red-300">{v.type === "charge_void" ? "Charge Void" : "Payment Void"}</span>
              {v.is_supervisor_override && (
                <Badge className="text-xs bg-amber-500/20 text-amber-400">Supervisor Override</Badge>
              )}
            </div>
            <span className="text-xs text-red-400">{v.original_amount?.toFixed(2)}</span>
          </div>
          <p className="text-xs text-slate-400 mt-1">{v.description}</p>
          <div className="flex items-center gap-2 mt-1 text-xs text-slate-500">
            <span>Reason: {v.void_reason}</span>
            {v.voided_by && <span>| By: {v.voided_by}</span>}
            {v.voided_at && <span>| {v.voided_at?.slice(0, 19)}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ══════════════════════════════════════════════ */
/* FOLIO DETAIL VIEW                             */
/* ══════════════════════════════════════════════ */

export default function FolioDetailView({ folioId: propFolioId, onClose }) {
  const [folioId, setFolioId] = useState(propFolioId || "");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState("timeline");
  const token = localStorage.getItem("token");

  const fetchDetail = useCallback(async (id) => {
    if (!id) return;
    setLoading(true);
    try {
      const { data: d } = await axios.get(`${API}/api/pms-core/folio/detail/${id}`, { headers: { Authorization: `Bearer ${token}` } });
      setData(d);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load folio detail");
    } finally { setLoading(false); }
  }, [token]);

  useEffect(() => { if (propFolioId) fetchDetail(propFolioId); }, [propFolioId, fetchDetail]);

  const summary = data?.summary;
  const folio = data?.folio;

  return (
    <div data-testid="folio-detail-view" className="min-h-screen bg-slate-950 text-slate-100">
      <div className="max-w-[1400px] mx-auto px-4 py-6">
        {/* Search bar for folio */}
        {!propFolioId && (
          <div className="flex items-center gap-3 mb-6">
            <input
              data-testid="folio-search-input"
              type="text"
              placeholder="Enter Folio ID..."
              value={folioId}
              onChange={e => setFolioId(e.target.value)}
              className="bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 text-sm text-slate-200 w-96 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            <Button data-testid="folio-search-btn" onClick={() => fetchDetail(folioId)} disabled={!folioId || loading}
              className="bg-indigo-600 hover:bg-indigo-700">
              {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : "Load Folio"}
            </Button>
            {onClose && <Button variant="ghost" onClick={onClose} className="text-slate-400">Close</Button>}
          </div>
        )}

        {loading && !data && (
          <div className="flex items-center justify-center py-20">
            <RefreshCw className="w-8 h-8 animate-spin text-indigo-400" />
          </div>
        )}

        {data && (
          <>
            {/* Folio Header */}
            <div className="flex items-start justify-between mb-6">
              <div>
                <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2">
                  <FileText className="w-5 h-5 text-indigo-400" />
                  Folio {folio?.folio_number || folioId?.slice(0, 8)}
                </h1>
                <div className="flex items-center gap-3 mt-1">
                  <Badge className={folio?.status === "open" ? "bg-emerald-500/20 text-emerald-400" : "bg-slate-500/20 text-slate-400"}>
                    {folio?.status}
                  </Badge>
                  <Badge variant="outline" className="text-xs">{folio?.folio_type}</Badge>
                  <span className="text-xs text-slate-500">Booking: {folio?.booking_id?.slice(0, 8)}...</span>
                </div>
              </div>
              <Button variant="outline" size="sm" onClick={() => fetchDetail(propFolioId || folioId)}
                className="border-slate-700 text-slate-300">
                <RefreshCw className="w-4 h-4 mr-2" /> Refresh
              </Button>
            </div>

            {/* Summary Cards */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
              <Card className="bg-slate-900/50 border-slate-800">
                <CardContent className="p-3">
                  <p className="text-xs text-slate-400">Total Charges</p>
                  <p className="text-lg font-bold text-amber-400">{summary?.total_charges?.toFixed(2)}</p>
                  <p className="text-xs text-slate-500">{summary?.charge_count} items</p>
                </CardContent>
              </Card>
              <Card className="bg-slate-900/50 border-slate-800">
                <CardContent className="p-3">
                  <p className="text-xs text-slate-400">Total Payments</p>
                  <p className="text-lg font-bold text-emerald-400">{summary?.total_payments?.toFixed(2)}</p>
                  <p className="text-xs text-slate-500">{summary?.payment_count} items</p>
                </CardContent>
              </Card>
              <Card className="bg-slate-900/50 border-slate-800">
                <CardContent className="p-3">
                  <p className="text-xs text-slate-400">Balance</p>
                  <p className={`text-lg font-bold ${(summary?.balance || 0) > 0 ? "text-red-400" : "text-emerald-400"}`}>
                    {summary?.balance?.toFixed(2)}
                  </p>
                </CardContent>
              </Card>
              <Card className="bg-slate-900/50 border-slate-800">
                <CardContent className="p-3">
                  <p className="text-xs text-slate-400">Voided Charges</p>
                  <p className="text-lg font-bold text-slate-400">{summary?.voided_charges || 0}</p>
                </CardContent>
              </Card>
              <Card className="bg-slate-900/50 border-slate-800">
                <CardContent className="p-3">
                  <p className="text-xs text-slate-400">Voided Payments</p>
                  <p className="text-lg font-bold text-slate-400">{summary?.voided_payments || 0}</p>
                </CardContent>
              </Card>
            </div>

            {/* Tabbed Detail Content */}
            <Tabs value={tab} onValueChange={setTab}>
              <TabsList className="bg-slate-900 border border-slate-800 mb-4">
                <TabsTrigger data-testid="folio-tab-timeline" value="timeline" className="data-[state=active]:bg-indigo-600/20 data-[state=active]:text-indigo-300">
                  <Clock className="w-3.5 h-3.5 mr-1.5" /> Timeline
                </TabsTrigger>
                <TabsTrigger data-testid="folio-tab-tax" value="tax" className="data-[state=active]:bg-indigo-600/20 data-[state=active]:text-indigo-300">
                  <DollarSign className="w-3.5 h-3.5 mr-1.5" /> Tax Breakdown
                </TabsTrigger>
                <TabsTrigger data-testid="folio-tab-splits" value="splits" className="data-[state=active]:bg-indigo-600/20 data-[state=active]:text-indigo-300">
                  <ArrowRightLeft className="w-3.5 h-3.5 mr-1.5" /> Splits
                </TabsTrigger>
                <TabsTrigger data-testid="folio-tab-voids" value="voids" className="data-[state=active]:bg-indigo-600/20 data-[state=active]:text-indigo-300">
                  <Ban className="w-3.5 h-3.5 mr-1.5" /> Voids
                </TabsTrigger>
                <TabsTrigger data-testid="folio-tab-city-ledger" value="city-ledger" className="data-[state=active]:bg-indigo-600/20 data-[state=active]:text-indigo-300">
                  <Building2 className="w-3.5 h-3.5 mr-1.5" /> City Ledger
                </TabsTrigger>
                <TabsTrigger data-testid="folio-tab-audit" value="audit" className="data-[state=active]:bg-indigo-600/20 data-[state=active]:text-indigo-300">
                  <ShieldCheck className="w-3.5 h-3.5 mr-1.5" /> Audit
                </TabsTrigger>
              </TabsList>

              <TabsContent value="timeline">
                <Card className="bg-slate-900/50 border-slate-800">
                  <CardHeader className="pb-2 pt-3 px-4">
                    <CardTitle className="text-sm text-slate-400">Folio Timeline ({data?.timeline?.length || 0} events)</CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-4">
                    <div className="space-y-2 max-h-[600px] overflow-y-auto">
                      {data?.timeline?.length ? data.timeline.map(e => (
                        <TimelineItem key={e.id} event={e} />
                      )) : <p className="text-sm text-slate-500 py-4">No transactions</p>}
                    </div>
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="tax">
                <Card className="bg-slate-900/50 border-slate-800">
                  <CardHeader className="pb-2 pt-3 px-4">
                    <CardTitle className="text-sm text-slate-400">Line-Level Tax Breakdown</CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-4">
                    <TaxBreakdownTable taxData={data?.tax_breakdown} />
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="splits">
                <Card className="bg-slate-900/50 border-slate-800">
                  <CardHeader className="pb-2 pt-3 px-4">
                    <CardTitle className="text-sm text-slate-400">Split Folio Operations</CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-4">
                    <SplitFolioInfo splitInfo={data?.split_folio_info} />
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="voids">
                <Card className="bg-slate-900/50 border-slate-800">
                  <CardHeader className="pb-2 pt-3 px-4">
                    <CardTitle className="text-sm text-slate-400">Void & Reversal Details</CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-4">
                    <VoidDetailsPanel voidDetails={data?.void_details} />
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="city-ledger">
                <Card className="bg-slate-900/50 border-slate-800">
                  <CardHeader className="pb-2 pt-3 px-4">
                    <CardTitle className="text-sm text-slate-400">City Ledger Transfer History</CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-4">
                    {data?.city_ledger_history?.length ? (
                      <div className="space-y-2">
                        {data.city_ledger_history.map((t, i) => (
                          <div key={i} className="flex items-center justify-between p-2 rounded bg-slate-800/40 border border-slate-700/40 text-xs">
                            <div>
                              <span className="text-slate-300">{t.description?.slice(0, 60)}</span>
                              <p className="text-slate-500">{t.transaction_date?.slice(0, 19)}</p>
                            </div>
                            <span className="text-amber-400 font-medium">{t.amount?.toFixed(2)}</span>
                          </div>
                        ))}
                      </div>
                    ) : <p className="text-sm text-slate-500 py-4">No city ledger transfers</p>}
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="audit">
                <Card className="bg-slate-900/50 border-slate-800">
                  <CardHeader className="pb-2 pt-3 px-4">
                    <CardTitle className="text-sm text-slate-400">Folio Audit Trail</CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-4">
                    {data?.audit_trail?.length ? (
                      <div className="space-y-2 max-h-96 overflow-y-auto">
                        {data.audit_trail.map((e, i) => (
                          <div key={i} className="text-xs bg-slate-800/40 p-2 rounded border border-slate-700/40 flex items-start gap-2">
                            <ShieldCheck className="w-3.5 h-3.5 text-slate-500 mt-0.5 shrink-0" />
                            <div>
                              <span className="text-slate-300 font-medium">{e.action}</span>
                              {e.performed_by && <span className="text-slate-500 ml-1">by {e.performed_by?.slice(0, 8)}</span>}
                              <p className="text-slate-600">{e.timestamp?.slice(0, 19)}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : <p className="text-sm text-slate-500 py-4">No audit entries for this folio</p>}
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>

            {/* Invoice Association */}
            {data?.invoices?.length > 0 && (
              <Card className="bg-slate-900/50 border-slate-800 mt-4">
                <CardHeader className="pb-2 pt-3 px-4">
                  <CardTitle className="text-sm text-slate-400">Associated Invoices ({data.invoices.length})</CardTitle>
                </CardHeader>
                <CardContent className="px-4 pb-4">
                  <div className="space-y-2">
                    {data.invoices.map((inv, i) => (
                      <div key={i} className="flex items-center justify-between p-2 rounded bg-slate-800/40 border border-slate-700/40 text-xs">
                        <div className="flex items-center gap-2">
                          <FileText className="w-3.5 h-3.5 text-slate-500" />
                          <span className="text-slate-300">{inv.invoice_number || inv.id?.slice(0, 8)}</span>
                          <Badge variant="outline" className="text-xs">{inv.status}</Badge>
                        </div>
                        <span className="text-slate-300">{inv.total_amount?.toFixed(2) || "-"}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </>
        )}
      </div>
    </div>
  );
}
