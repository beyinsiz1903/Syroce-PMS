import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import axios from 'axios';

import { Button } from '@/components/ui/button';
import {
  Package, AlertTriangle, ClipboardList, CheckCircle2, Truck,
  PackageCheck, ArrowRight, ShoppingCart, Sparkles, RefreshCw,
  ChevronDown, ChevronUp, FileText, Wallet, Clock, Users,
} from 'lucide-react';

// Static color tokens — Tailwind JIT cannot resolve `bg-${color}-100` strings,
// so every class is written out fully here and safelisted automatically by JIT
// scanning the source file.
const COLORS = {
  orange: {
    iconBg: 'bg-amber-100', iconFg: 'text-amber-600',
    badgeBg: 'bg-amber-50', badgeFg: 'text-amber-700',
    border: 'hover:border-amber-200',
  },
  blue: {
    iconBg: 'bg-blue-100', iconFg: 'text-blue-600',
    badgeBg: 'bg-blue-50', badgeFg: 'text-blue-700',
    border: 'hover:border-blue-200',
  },
  indigo: {
    iconBg: 'bg-indigo-100', iconFg: 'text-indigo-600',
    badgeBg: 'bg-indigo-50', badgeFg: 'text-indigo-700',
    border: 'hover:border-indigo-200',
  },
  purple: {
    iconBg: 'bg-indigo-100', iconFg: 'text-indigo-600',
    badgeBg: 'bg-indigo-50', badgeFg: 'text-indigo-700',
    border: 'hover:border-indigo-200',
  },
  emerald: {
    iconBg: 'bg-emerald-100', iconFg: 'text-emerald-600',
    badgeBg: 'bg-emerald-50', badgeFg: 'text-emerald-700',
    border: 'hover:border-emerald-200',
  },
  rose: {
    iconBg: 'bg-rose-100', iconFg: 'text-rose-600',
    badgeBg: 'bg-rose-50', badgeFg: 'text-rose-700',
    border: 'hover:border-rose-200',
  },
};

const fmtMoney = (n, lang) => {
  try {
    return new Intl.NumberFormat(lang || 'tr-TR', {
      style: 'currency', currency: 'TRY', maximumFractionDigits: 0,
    }).format(Number(n) || 0);
  } catch { return `${Number(n || 0).toFixed(0)} ₺`; }
};

const fmtDate = (iso, lang) => {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString(lang || 'tr-TR'); }
  catch { return String(iso).slice(0, 10) || '—'; }
};

const KpiCard = ({ icon: Icon, label, value, sub, color, onClick }) => {
  const c = COLORS[color] || COLORS.blue;
  return (
    <button
      type="button"
      onClick={onClick}
      className={`text-left bg-white border border-gray-100 rounded-2xl p-5 shadow-sm
        hover:shadow-md ${c.border} transition group w-full`}
    >
      <div className="flex items-center justify-between mb-3">
        <div className={`w-10 h-10 rounded-xl ${c.iconBg} ${c.iconFg} flex items-center justify-center`}>
          <Icon className="w-5 h-5" />
        </div>
        {onClick && <ArrowRight className="w-4 h-4 text-gray-300 group-hover:text-gray-500 transition" />}
      </div>
      <div className="text-2xl font-bold text-gray-900 leading-tight">{value}</div>
      <div className="text-sm font-medium text-gray-700 mt-1">{label}</div>
      {sub && <div className="text-xs text-gray-500 mt-0.5">{sub}</div>}
    </button>
  );
};

const Panel = ({ icon: Icon, title, count, color, empty, children, footerLabel, onFooter }) => {
  const c = COLORS[color] || COLORS.blue;
  return (
    <div className="bg-white border border-gray-100 rounded-2xl shadow-sm overflow-hidden flex flex-col">
      <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={`w-8 h-8 rounded-lg ${c.iconBg} ${c.iconFg} flex items-center justify-center`}>
            <Icon className="w-4 h-4" />
          </div>
          <h3 className="font-semibold text-gray-900">{title}</h3>
        </div>
        <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${c.badgeBg} ${c.badgeFg}`}>
          {count}
        </span>
      </div>
      <div className="flex-1 divide-y divide-gray-100 max-h-[420px] overflow-y-auto">
        {count === 0
          ? <div className="p-6 text-center text-sm text-gray-400">{empty}</div>
          : children}
      </div>
      {onFooter && count > 0 && (
        <button
          type="button"
          onClick={onFooter}
          className="px-5 py-3 border-t border-gray-100 text-sm font-medium text-gray-600 hover:bg-gray-50 flex items-center justify-center gap-1"
        >
          {footerLabel} <ArrowRight className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
};

const InventoryProcurementGuide = ({ user, tenant, onLogout }) => {
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const lang = i18n.language || 'tr';

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [pendingPRs, setPendingPRs] = useState([]);
  const [openPOs, setOpenPOs] = useState([]);
  const [showGuide, setShowGuide] = useState(false);
  const [partialError, setPartialError] = useState(null); // {failed: string[]}

  const safeArray = (v) => (Array.isArray(v) ? v : []);

  const load = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true); else setLoading(true);

    const calls = [
      ['summary', () => axios.get('/procurement/summary')],
      ['alerts', () => axios.get('/inventory/alerts')],
      ['pendingPRs', () => axios.get('/procurement/purchase-requests', { params: { status: 'submitted' } })],
      ['openPOs', () => axios.get('/procurement/purchase-orders')],
    ];
    const results = await Promise.allSettled(calls.map(([, fn]) => fn()));
    const failed = [];

    results.forEach((res, idx) => {
      const [key] = calls[idx];
      if (res.status === 'rejected') {
        failed.push(key);
        console.error('[OpsCenter] failed:', key, res.reason);
        return;
      }
      const data = res.value?.data;
      if (key === 'summary') {
        setSummary(data && typeof data === 'object' ? data : null);
      } else if (key === 'alerts') {
        const list = safeArray(data?.alerts) .length ? data.alerts
          : safeArray(data?.items).length ? data.items
            : safeArray(data);
        setAlerts(list.slice(0, 50));
      } else if (key === 'pendingPRs') {
        setPendingPRs(safeArray(data?.items).slice(0, 8));
      } else if (key === 'openPOs') {
        const all = safeArray(data?.items);
        setOpenPOs(
          all.filter(p => ['sent', 'partially_received'].includes(p?.status))
            .slice(0, 8),
        );
      }
    });

    setPartialError(failed.length ? { failed } : null);
    setLoading(false); setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const criticalCount = alerts.length;
  const pendingCount = summary?.pr_pending ?? pendingPRs.length;
  const openPoCount = summary?.po_open ?? openPOs.length;
  const receivedCount = summary?.po_received ?? 0;
  const suppliersActive = summary?.suppliers_active ?? 0;
  const openCommit = summary?.open_commitment_value ?? 0;

  // Deep-link helpers — use react-router state (matches existing newPRItem
  // handler in ProcurementPage.jsx). Tab keys here MUST match the
  // <TabsTrigger value="..."> values in ProcurementPage: summary | pos | suppliers.
  const goToTab = (initialTab) =>
    navigate('/app/procurement', { state: { initialTab } });

  const goToNewPR = (alert) => {
    const seed = alert ? {
      name: alert.name || alert.item_name || alert.product || alert.title || '',
      sku: alert.sku || '',
      id: alert.id || alert.item_id || null,
      unit: alert.unit || 'adet',
      unit_cost: alert.unit_cost || 0,
      quantity: alert.current_stock ?? alert.stock ?? alert.quantity ?? 0,
      reorder_level: alert.min_stock ?? alert.critical_level
        ?? alert.threshold ?? alert.reorder_point ?? 0,
      department: alert.department || '',
    } : null;
    navigate('/app/procurement', seed ? { state: { newPRItem: seed } } : undefined);
  };

  const steps = [
    { num: 1, icon: AlertTriangle, color: 'bg-amber-500' },
    { num: 2, icon: ClipboardList, color: 'bg-blue-500' },
    { num: 3, icon: CheckCircle2, color: 'bg-emerald-500' },
    { num: 4, icon: Truck, color: 'bg-indigo-500' },
    { num: 5, icon: PackageCheck, color: 'bg-indigo-500' },
    { num: 6, icon: Package, color: 'bg-pink-500' },
  ];

  return (
    <>
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        {/* Header strip */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Sparkles className="w-4 h-4 text-blue-500" />
            <span>{t('opsCenter.headerHint')}</span>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => load(true)} disabled={refreshing}>
              <RefreshCw className={`w-4 h-4 mr-1 ${refreshing ? 'animate-spin' : ''}`} />
              {t('opsCenter.refresh')}
            </Button>
            <Button size="sm" variant="outline" onClick={() => navigate('/hotel-inventory')}>
              <Package className="w-4 h-4 mr-1" /> {t('opsCenter.goStock')}
            </Button>
            <Button size="sm" onClick={() => goToNewPR(null)}>
              <ShoppingCart className="w-4 h-4 mr-1" /> {t('opsCenter.newPR')}
            </Button>
          </div>
        </div>

        {partialError && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-sm text-amber-800 flex items-center justify-between gap-3">
            <span>
              {t('opsCenter.errorPartial', { count: partialError.failed.length })}
              {' · '}
              <span className="text-xs text-amber-600">
                ({partialError.failed.join(', ')})
              </span>
            </span>
            <Button size="sm" variant="outline" onClick={() => load(true)}>
              {t('opsCenter.retry')}
            </Button>
          </div>
        )}

        {/* KPI grid */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <KpiCard icon={AlertTriangle} color="orange"
            label={t('opsCenter.kpi.critical')}
            value={loading ? '—' : criticalCount}
            sub={t('opsCenter.kpi.criticalSub')}
            onClick={() => navigate('/hotel-inventory')} />
          <KpiCard icon={Clock} color="blue"
            label={t('opsCenter.kpi.pending')}
            value={loading ? '—' : pendingCount}
            sub={t('opsCenter.kpi.pendingSub')}
            onClick={() => goToTab('summary')} />
          <KpiCard icon={Truck} color="indigo"
            label={t('opsCenter.kpi.openPO')}
            value={loading ? '—' : openPoCount}
            sub={t('opsCenter.kpi.openPOSub')}
            onClick={() => goToTab('pos')} />
          <KpiCard icon={PackageCheck} color="purple"
            label={t('opsCenter.kpi.received')}
            value={loading ? '—' : receivedCount}
            sub={t('opsCenter.kpi.receivedSub')}
            onClick={() => goToTab('pos')} />
          <KpiCard icon={Users} color="emerald"
            label={t('opsCenter.kpi.suppliers')}
            value={loading ? '—' : suppliersActive}
            sub={t('opsCenter.kpi.suppliersSub')}
            onClick={() => goToTab('suppliers')} />
          <KpiCard icon={Wallet} color="rose"
            label={t('opsCenter.kpi.commitment')}
            value={loading ? '—' : fmtMoney(openCommit, lang)}
            sub={t('opsCenter.kpi.commitmentSub')} />
        </div>

        {/* 3-column action panels */}
        <div className="grid lg:grid-cols-3 gap-4">
          {/* Critical stock */}
          <Panel
            icon={AlertTriangle} color="orange"
            title={t('opsCenter.panels.critical.title')}
            count={criticalCount}
            empty={t('opsCenter.panels.critical.empty')}
            footerLabel={t('opsCenter.panels.critical.footer')}
            onFooter={() => navigate('/hotel-inventory')}
          >
            {alerts.slice(0, 8).map((a, i) => {
              const name = a.name || a.item_name || a.product || a.title || '—';
              const stock = a.current_stock ?? a.stock ?? a.quantity ?? '?';
              const min = a.min_stock ?? a.critical_level
                ?? a.threshold ?? a.reorder_point ?? '?';
              return (
                <div key={a.id || a.item_id || i} className="px-5 py-3 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-medium text-gray-900 truncate">{name}</div>
                    <div className="text-xs text-gray-500">
                      {t('opsCenter.panels.critical.stockInfo', { stock, min })}
                    </div>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => goToNewPR(a)}>
                    {t('opsCenter.panels.critical.action')}
                  </Button>
                </div>
              );
            })}
          </Panel>

          {/* Pending approvals — uses backend PR shape: lines + lines_total */}
          <Panel
            icon={ClipboardList} color="blue"
            title={t('opsCenter.panels.pending.title')}
            count={pendingPRs.length}
            empty={t('opsCenter.panels.pending.empty')}
            footerLabel={t('opsCenter.panels.pending.footer')}
            onFooter={() => goToTab('summary')}
          >
            {pendingPRs.map(pr => {
              const lineCount = safeArray(pr.lines).length;
              const total = pr.lines_total ?? pr.estimated_total ?? pr.total ?? 0;
              return (
                <button key={pr.id} type="button"
                  onClick={() => goToTab('summary')}
                  className="w-full text-left px-5 py-3 hover:bg-blue-50/50 transition">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="font-medium text-gray-900 truncate">
                        {pr.pr_no || pr.id?.slice(0, 8)}
                      </div>
                      <div className="text-xs text-gray-500 truncate">
                        {pr.department || '—'} · {lineCount} {t('opsCenter.panels.pending.items')}
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-sm font-semibold text-blue-700">
                        {fmtMoney(total, lang)}
                      </div>
                      <div className="text-[10px] text-gray-400">{fmtDate(pr.created_at, lang)}</div>
                    </div>
                  </div>
                </button>
              );
            })}
          </Panel>

          {/* Open POs */}
          <Panel
            icon={Truck} color="indigo"
            title={t('opsCenter.panels.incoming.title')}
            count={openPOs.length}
            empty={t('opsCenter.panels.incoming.empty')}
            footerLabel={t('opsCenter.panels.incoming.footer')}
            onFooter={() => goToTab('pos')}
          >
            {openPOs.map(po => (
              <button key={po.id} type="button"
                onClick={() => goToTab('pos')}
                className="w-full text-left px-5 py-3 hover:bg-indigo-50/50 transition">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="font-medium text-gray-900 truncate">
                      {po.po_no || po.id?.slice(0, 8)}
                    </div>
                    <div className="text-xs text-gray-500 truncate">
                      {po.supplier_name || po.supplier_id?.slice(0, 8) || '—'}
                      {po.status === 'partially_received'
                        ? ` · ${t('opsCenter.panels.incoming.partial')}`
                        : ''}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-sm font-semibold text-indigo-700">
                      {fmtMoney(po.grand_total || 0, lang)}
                    </div>
                    <div className="text-[10px] text-gray-400">
                      {po.expected_delivery_date
                        ? fmtDate(po.expected_delivery_date, lang)
                        : fmtDate(po.created_at, lang)}
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </Panel>
        </div>

        {/* Collapsible "How it works" guide — small, no longer the page */}
        <div className="bg-white border border-gray-100 rounded-2xl shadow-sm overflow-hidden">
          <button
            type="button"
            onClick={() => setShowGuide(v => !v)}
            className="w-full px-5 py-3 flex items-center justify-between text-left hover:bg-gray-50"
          >
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-gray-400" />
              <span className="font-medium text-gray-700">{t('opsCenter.guide.title')}</span>
              <span className="text-xs text-gray-400">— {t('opsCenter.guide.subtitle')}</span>
            </div>
            {showGuide ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
          </button>
          {showGuide && (
            <div className="px-6 pb-6 pt-2">
              <div className="flex flex-wrap items-start justify-center gap-y-6">
                {steps.map((s, i) => (
                  <React.Fragment key={s.num}>
                    <div className="flex-1 min-w-[140px] text-center">
                      <div className={`w-10 h-10 rounded-xl ${s.color} text-white flex items-center justify-center shadow mb-2 mx-auto`}>
                        <s.icon className="w-5 h-5" />
                      </div>
                      <div className="text-[10px] font-bold text-gray-400 mb-0.5">
                        {t('opsCenter.guide.stepLabel', { num: s.num })}
                      </div>
                      <div className="text-sm font-semibold text-gray-900">
                        {t(`opsCenter.guide.steps.${s.num}.title`)}
                      </div>
                      <div className="text-xs text-gray-500 mt-0.5">
                        {t(`opsCenter.guide.steps.${s.num}.desc`)}
                      </div>
                    </div>
                    {i < steps.length - 1 && (
                      <div className="hidden md:flex items-center text-gray-300 px-1 self-center">
                        <ArrowRight className="w-4 h-4" />
                      </div>
                    )}
                  </React.Fragment>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
};

export default InventoryProcurementGuide;
