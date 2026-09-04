import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useCurrency } from '@/context/CurrencyContext';
import { localIsoDate, useBusinessDate } from '@/hooks/useBusinessDate';
import AccountingSetupWizard from '@/pages/accounting/AccountingSetupWizard';
import { AccountLedgerView } from '@/pages/accounting/AccountLedgerView';
import { GeneralLedgerNavigation } from '@/pages/accounting/GeneralLedgerNavigation';
import { GeneralLedgerOverview } from '@/pages/accounting/GeneralLedgerOverview';
import { Plus, Save, FileText, AlertCircle, CalendarRange, LockKeyhole, Unlock, RotateCcw, Landmark, TrendingUp, PackageOpen, Cable, ReceiptText, Send, CheckCircle2, XCircle, ShieldCheck } from 'lucide-react';

export const GL_ENDPOINTS = {
  setup: '/gl/setup',
  setupProfile: '/gl/setup/profile',
  setupInitialize: '/gl/setup/initialize',
  setupOpeningBalances: '/gl/setup/opening-balances',
  setupComplete: '/gl/setup/complete',
  accounts: '/gl/accounts',
  initializeAccounts: '/gl/accounts/initialize',
  journal: '/gl/journal',
  vouchers: '/gl/vouchers',
  sequenceAudit: '/gl/sequence-audit',
  integrityAudit: '/gl/integrity-audit',
  trialBalance: '/gl/trial-balance',
  periods: '/gl/periods',
  initializePeriods: '/gl/periods/initialize',
  yearEnd: '/gl/year-end',
  closeYear: '/gl/year-end/close',
  incomeStatement: '/gl/statements/income-statement',
  balanceSheet: '/gl/statements/balance-sheet',
  comparativeIncome: '/gl/statements/comparative-income-statement',
  comparativeBalance: '/gl/statements/comparative-balance-sheet',
  exportReport: '/gl/reports/export',
  fxRevalue: '/gl/fx/revalue',
  chainConsolidated: '/gl/chain/consolidated',
  intercompanyRules: '/gl/chain/intercompany-rules',
  eledgerSettings: '/gl/e-ledger/settings',
  eledgerPreflight: '/gl/e-ledger/preflight',
  eledgerSourcePackage: '/gl/e-ledger/source-package',
  operationalMapping: '/gl/integrations/operational/mapping',
  operationalStatus: '/gl/integrations/operational/status',
  nilveraSettings: '/gl/integrations/nilvera/settings',
  nilveraQueue: '/gl/integrations/nilvera/queue',
  apGLMapping: '/ap/gl-mapping',
  fixedAssetGLMapping: '/fixed-assets/gl-mapping',
};

const DEFAULT_NILVERA_GL_SETTINGS = {
  incoming_mode: 'review',
  outgoing_mode: 'review',
  incoming_purchase_account_code: '153',
  incoming_vat_account_code: '191',
  incoming_payable_account_code: '320',
  incoming_other_tax_account_code: '',
  incoming_deduction_account_code: '',
  incoming_other_tax_accounts_by_code: {},
  incoming_deduction_accounts_by_code: {},
  outgoing_revenue_account_code: '600',
  outgoing_receivable_account_code: '120',
  outgoing_discount_account_code: '611',
  outgoing_vat_account_code: '391',
  outgoing_accommodation_tax_account_code: '360',
  outgoing_vat_accounts_by_rate: {},
  outgoing_accommodation_tax_accounts_by_rate: {},
};

const DEFAULT_AP_GL_MAPPING = {
  enabled: false,
  expense_account_code: '770',
  input_vat_account_code: '191',
  payable_account_code: '320',
  bank_account_code: '102',
  cash_account_code: '100',
};

const DEFAULT_FIXED_ASSET_GL_MAPPING = {
  enabled: false,
  depreciation_expense_account_code: '770',
  accumulated_depreciation_account_code: '257',
};

const EMPTY_NILVERA_MAPPING_TEXT = {
  incoming_other_tax_accounts_by_code: '',
  incoming_deduction_accounts_by_code: '',
  outgoing_vat_accounts_by_rate: '',
  outgoing_accommodation_tax_accounts_by_rate: '',
};

export const formatAccountMapping = (mapping = {}) => Object.entries(mapping)
  .sort(([left], [right]) => left.localeCompare(right, 'tr'))
  .map(([key, account]) => `${key}=${account}`)
  .join(', ');

export const parseAccountMapping = (value, label = 'Hesap eşlemesi') => {
  const normalized = String(value || '').trim();
  if (!normalized) return {};

  return normalized.split(/[;,\n]+/).reduce((mapping, token) => {
    const pair = token.trim().split(/\s*(?:=|:)\s*/);
    if (pair.length !== 2 || !pair[0] || !pair[1]) {
      throw new Error(`${label}: eşlemeleri kod=hesap biçiminde girin.`);
    }
    if (pair[0].length > 40 || pair[1].length > 40) {
      throw new Error(`${label}: kod ve hesap en fazla 40 karakter olabilir.`);
    }
    mapping[pair[0]] = pair[1];
    return mapping;
  }, {});
};

export const collectIntegrationAccountCodes = (nilvera = {}, ap = {}, fixedAsset = {}) => {
  const directKeys = [
    'incoming_purchase_account_code',
    'incoming_vat_account_code',
    'incoming_payable_account_code',
    'incoming_other_tax_account_code',
    'incoming_deduction_account_code',
    'outgoing_revenue_account_code',
    'outgoing_receivable_account_code',
    'outgoing_discount_account_code',
    'outgoing_vat_account_code',
    'outgoing_accommodation_tax_account_code',
  ];
  const mappedKeys = [
    'incoming_other_tax_accounts_by_code',
    'incoming_deduction_accounts_by_code',
    'outgoing_vat_accounts_by_rate',
    'outgoing_accommodation_tax_accounts_by_rate',
  ];
  const candidates = [
    ...directKeys.map((key) => nilvera[key]),
    ...mappedKeys.flatMap((key) => Object.values(nilvera[key] || {})),
    ap.expense_account_code,
    ap.input_vat_account_code,
    ap.payable_account_code,
    ap.bank_account_code,
    ap.cash_account_code,
    fixedAsset.depreciation_expense_account_code,
    fixedAsset.accumulated_depreciation_account_code,
  ];
  return [...new Set(candidates.map((value) => String(value || '').trim()).filter(Boolean))].sort();
};

const VOUCHER_TYPE_BY_LABEL = {
  Mahsup: 'mahsup',
  Tahsilat: 'tahsil',
  Tediye: 'tediye',
  Açılış: 'acilis',
  Kapanış: 'kapanis',
};

export const isForeignCurrency = (currency, baseCurrency = 'TRY') => {
  const normalized = String(currency || '').trim().toUpperCase();
  return Boolean(normalized) && normalized !== String(baseCurrency || 'TRY').trim().toUpperCase();
};

export const toVoucherPayload = (journal, baseCurrency = 'TRY') => ({
  date: journal.date,
  memo: journal.description.trim(),
  voucher_type: VOUCHER_TYPE_BY_LABEL[journal.type] || 'mahsup',
  lines: journal.lines.map((line) => ({
    account_code: line.account_code.trim(),
    debit: Number(line.debit) || 0,
    credit: Number(line.credit) || 0,
    memo: line.description?.trim() || null,
    ...(isForeignCurrency(line.currency, baseCurrency) ? {
      currency: line.currency.trim().toUpperCase(),
      foreign_amount: Number(line.foreign_amount),
      exchange_rate: Number(line.exchange_rate),
    } : {}),
  })),
});

// Kept as an export while callers migrate; it now creates a controlled
// voucher payload and can no longer bypass the approval lifecycle.
export const toJournalPayload = toVoucherPayload;

export const getJournalValidationError = (journal, baseCurrency = 'TRY') => {
  const lines = journal.lines || [];
  const totalDebit = lines.reduce((sum, line) => sum + (Number(line.debit) || 0), 0);
  const totalCredit = lines.reduce((sum, line) => sum + (Number(line.credit) || 0), 0);
  if (Math.abs(totalDebit - totalCredit) > 0.01) return `Borç (${totalDebit}) ve Alacak (${totalCredit}) toplamları eşit olmalıdır.`;
  if (totalDebit <= 0) return 'Fiş toplamı 0 olamaz.';
  if (!String(journal.description || '').trim()) return 'Fiş açıklaması zorunludur.';
  if (lines.some((line) => !String(line.account_code || '').trim())) return 'Her satır için hesap kodu zorunludur.';
  if (lines.some((line) => (Number(line.debit) > 0) === (Number(line.credit) > 0))) {
    return 'Her satırda yalnızca borç veya alacak tutarı olmalıdır.';
  }
  if (lines.some((line) => isForeignCurrency(line.currency, baseCurrency) && (!Number(line.foreign_amount) || !Number(line.exchange_rate)))) {
    return 'Dövizli satırlarda yabancı tutar ve kur zorunludur.';
  }
  return '';
};

const newRequestKey = () => {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `manual-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const emptyJournal = (businessDate = localIsoDate()) => ({
  type: 'Mahsup',
  description: '',
  idempotency_key: newRequestKey(),
  lines: [
    { account_code: '', debit: 0, credit: 0, description: '', currency: '', foreign_amount: '', exchange_rate: '' },
    { account_code: '', debit: 0, credit: 0, description: '', currency: '', foreign_amount: '', exchange_rate: '' }
  ]
});

const VOUCHER_STATUS = {
  draft: { label: 'Taslak', className: 'bg-slate-100 text-slate-700' },
  submitted: { label: 'İncelemede', className: 'bg-amber-100 text-amber-800' },
  approved: { label: 'Onaylandı', className: 'bg-blue-100 text-blue-800' },
  posting: { label: 'Kaydediliyor', className: 'bg-indigo-100 text-indigo-800' },
  posted: { label: 'Yevmiyede', className: 'bg-emerald-100 text-emerald-800' },
  rejected: { label: 'Reddedildi', className: 'bg-red-100 text-red-800' },
  cancelled: { label: 'İptal', className: 'bg-gray-100 text-gray-600' },
};

export const voucherActionNames = (status) => ({
  draft: ['edit', 'submit', 'cancel'],
  submitted: ['approve', 'reject'],
  approved: ['post'],
  posting: ['post'],
  rejected: ['edit', 'cancel'],
}[status] || []);

const VOUCHER_LABEL_BY_TYPE = {
  mahsup: 'Mahsup',
  tahsil: 'Tahsilat',
  tediye: 'Tediye',
  acilis: 'Açılış',
  kapanis: 'Kapanış',
};

const journalFromVoucher = (voucher) => ({
  date: voucher.date,
  type: VOUCHER_LABEL_BY_TYPE[voucher.voucher_type] || 'Mahsup',
  description: voucher.memo || '',
  idempotency_key: newRequestKey(),
  lines: (voucher.lines || []).map((line) => ({
    account_code: line.account_code || '',
    debit: line.debit || 0,
    credit: line.credit || 0,
    description: line.memo || '',
    currency: line.currency || '',
    foreign_amount: line.foreign_amount || '',
    exchange_rate: line.exchange_rate || '',
  })),
});

export const normalizeTrialBalance = (data = {}) => ({
  lines: (data.rows || []).map((row) => ({
    code: row.account_code,
    name: row.account_name,
    total_debit: row.total_debit || 0,
    total_credit: row.total_credit || 0,
    balance_type: row.debit_balance > 0 ? 'Borç' : row.credit_balance > 0 ? 'Alacak' : '-',
    balance: row.debit_balance || row.credit_balance || 0,
  })),
  totals: {
    total_debit: data.totals?.debit_balance || 0,
    total_credit: data.totals?.credit_balance || 0,
    balanced: data.totals?.balanced ?? true,
  },
});

// Older reversal rows predate `reversal_status` on the source entry. The
// linked contra entry remains authoritative, so derive the display state from
// that immutable relationship while loading the journal list.
export const markReversedJournalEntries = (entries = []) => {
  const reversedSourceIds = new Set(
    entries
      .filter((entry) => entry.source === 'reversal')
      .map((entry) => entry.reverses_entry_id || entry.source_ref)
      .filter(Boolean),
  );
  return entries.map((entry) => (
    reversedSourceIds.has(entry.id) && entry.reversal_status !== 'reversed'
      ? { ...entry, reversal_status: 'reversed' }
      : entry
  ));
};

export const mergeAccountBalances = (accounts = [], trialBalance = {}) => {
  const balances = new Map(
    (trialBalance.rows || []).map((row) => [
      row.account_code,
      (Number(row.debit_balance) || 0) - (Number(row.credit_balance) || 0),
    ])
  );
  return accounts.map((account) => ({ ...account, balance: balances.get(account.code) || 0 }));
};

const GL_TABS = ['overview', 'journals', 'account-ledger', 'accounts', 'trial-balance', 'statements', 'periods', 'workspace', 'integrations', 'setup'];

const GeneralLedgerModule = () => {
  const { amount: fmtMoney } = useCurrency();
  const businessDate = useBusinessDate();
  const businessDateDefaults = useRef(localIsoDate());
  const [ledgerCurrency, setLedgerCurrency] = useState('TRY');
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get('tab');
  const [activeTab, setActiveTab] = useState(GL_TABS.includes(requestedTab) ? requestedTab : 'overview');
  
  const [accounts, setAccounts] = useState([]);
  const [journals, setJournals] = useState([]);
  const [vouchers, setVouchers] = useState([]);
  const [sequenceAudit, setSequenceAudit] = useState(null);
  const [integrityAudit, setIntegrityAudit] = useState(null);
  const [trialBalance, setTrialBalance] = useState({ lines: [], totals: {} });
  const [initializingAccounts, setInitializingAccounts] = useState(false);
  const [periods, setPeriods] = useState([]);
  const [periodYear, setPeriodYear] = useState(() => Number(localIsoDate().slice(0, 4)));
  const [periodBusy, setPeriodBusy] = useState('');
  const [yearEndStatus, setYearEndStatus] = useState(null);
  const [periodActionDialog, setPeriodActionDialog] = useState(null);
  const [periodActionReason, setPeriodActionReason] = useState('');
  const [voucherActionDialog, setVoucherActionDialog] = useState(null);
  const [voucherActionReason, setVoucherActionReason] = useState('');
  const [reversalDialog, setReversalDialog] = useState(null);
  const [reversalReason, setReversalReason] = useState('');
  const [reversalDate, setReversalDate] = useState(businessDate);
  const [journalSaving, setJournalSaving] = useState(false);
  const [voucherBusy, setVoucherBusy] = useState('');
  const [editingVoucher, setEditingVoucher] = useState(null);
  const [reversalBusy, setReversalBusy] = useState('');
  const reversalKeys = useRef({});
  const [statements, setStatements] = useState({ income: null, balance: null });
  const [comparison, setComparison] = useState({ income: null, balance: null });
  const [chainFinance, setChainFinance] = useState(null);
  const [intercompany, setIntercompany] = useState({ rules: [], properties: [], can_manage: false });
  const [intercompanyForm, setIntercompanyForm] = useState({ name: '', kind: 'balance', tenant_a_id: '', account_a_code: '', tenant_b_id: '', account_b_code: '' });
  const [intercompanyBusy, setIntercompanyBusy] = useState(false);
  const [eledgerPeriod, setEledgerPeriod] = useState(() => localIsoDate().slice(0, 7));
  const [eledgerSettings, setEledgerSettings] = useState({ taxpayer_id: '', legal_name: '', source_application: 'Syroce PMS', source_application_version: '', software_approval_reference: '' });
  const [eledgerPreflight, setEledgerPreflight] = useState(null);
  const [eledgerBusy, setEledgerBusy] = useState('');
  const [fxForm, setFxForm] = useState(() => ({ date: localIsoDate(), currency: 'USD', closing_rate: '' }));
  const [fxBusy, setFxBusy] = useState(false);
  const [workspace, setWorkspace] = useState({ aging: null, expenseBudget: null, revenueBudget: null, assets: [] });
  const [operationalBridge, setOperationalBridge] = useState(null);
  const [operationalBusy, setOperationalBusy] = useState(false);
  const [nilveraGL, setNilveraGL] = useState({ settings: DEFAULT_NILVERA_GL_SETTINGS, queue: [], counts: {} });
  const [nilveraMappingText, setNilveraMappingText] = useState(EMPTY_NILVERA_MAPPING_TEXT);
  const [apGLMapping, setApGLMapping] = useState(DEFAULT_AP_GL_MAPPING);
  const [fixedAssetGLMapping, setFixedAssetGLMapping] = useState(DEFAULT_FIXED_ASSET_GL_MAPPING);
  const [integrationBusy, setIntegrationBusy] = useState('');

  const handleTabChange = (value) => {
    setActiveTab(value);
    const next = new URLSearchParams(searchParams);
    next.set('tab', value);
    setSearchParams(next, { replace: true });
  };

  useEffect(() => {
    if (GL_TABS.includes(requestedTab)) setActiveTab(requestedTab);
  }, [requestedTab]);
  
  // New Journal Entry State
  const [newJournal, setNewJournal] = useState(() => emptyJournal());

  useEffect(() => {
    let active = true;
    axios.get(GL_ENDPOINTS.setup)
      .then(({ data }) => {
        const currency = String(data?.profile?.currency || '').trim().toUpperCase();
        if (active && /^[A-Z]{3}$/.test(currency)) setLedgerCurrency(currency);
      })
      .catch(() => {});
    return () => { active = false; };
  }, []);

  useEffect(() => {
    setNewJournal((current) => {
      const hasEntry = current.description.trim()
        || current.lines.some((line) => line.account_code || Number(line.debit) || Number(line.credit));
      return hasEntry ? current : { ...current, date: businessDate };
    });
  }, [businessDate]);

  useEffect(() => {
    const previousDefault = businessDateDefaults.current;
    if (businessDate === previousDefault) return;
    setPeriodYear((current) => current === Number(previousDefault.slice(0, 4)) ? Number(businessDate.slice(0, 4)) : current);
    setEledgerPeriod((current) => current === previousDefault.slice(0, 7) ? businessDate.slice(0, 7) : current);
    setFxForm((current) => current.date === previousDefault ? { ...current, date: businessDate } : current);
    businessDateDefaults.current = businessDate;
  }, [businessDate]);

  const fetchAccounts = async () => {
    try {
      const [accountsRes, balanceRes] = await Promise.all([
        axios.get(GL_ENDPOINTS.accounts),
        axios.get(GL_ENDPOINTS.trialBalance),
      ]);
      setAccounts(mergeAccountBalances(accountsRes.data?.accounts || [], balanceRes.data));
    } catch {
      toast.error('Hesap planı yüklenemedi.');
    }
  };

  const initializeAccounts = async () => {
    setInitializingAccounts(true);
    try {
      await axios.post(GL_ENDPOINTS.initializeAccounts);
      await fetchAccounts();
      toast.success('Standart hesap planı oluşturuldu.');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Hesap planı oluşturulamadı.');
    } finally {
      setInitializingAccounts(false);
    }
  };

  const fetchJournals = async () => {
    try {
      const [journalRes, voucherRes, auditRes, integrityRes] = await Promise.all([
        axios.get(GL_ENDPOINTS.journal, { params: { limit: 1000 } }),
        axios.get(GL_ENDPOINTS.vouchers),
        axios.get(GL_ENDPOINTS.sequenceAudit, { params: { fiscal_year: Number(businessDate.slice(0, 4)) } }),
        axios.get(GL_ENDPOINTS.integrityAudit, { params: { fiscal_year: Number(businessDate.slice(0, 4)) } }),
      ]);
      setJournals(markReversedJournalEntries(journalRes.data?.entries || []));
      setVouchers(voucherRes.data?.vouchers || []);
      setSequenceAudit(auditRes.data || null);
      setIntegrityAudit(integrityRes.data || null);
    } catch {
      toast.error('Yevmiye fişleri yüklenemedi.');
    }
  };

  const fetchTrialBalance = async () => {
    try {
      const res = await axios.get(GL_ENDPOINTS.trialBalance);
      setTrialBalance(normalizeTrialBalance(res.data));
    } catch {
      toast.error('Mizan yüklenemedi.');
    }
  };

  const fetchPeriods = async () => {
    try {
      const [periodRes, yearEndRes] = await Promise.all([
        axios.get(GL_ENDPOINTS.periods, { params: { fiscal_year: periodYear } }),
        axios.get(`${GL_ENDPOINTS.yearEnd}/${periodYear}`),
      ]);
      setPeriods(periodRes.data?.periods || []);
      setYearEndStatus(yearEndRes.data || null);
    } catch {
      toast.error('Mali dönemler yüklenemedi.');
    }
  };

  const fetchStatements = async () => {
    const today = businessDate;
    const start = `${today.slice(0, 4)}-01-01`;
    const previousYear = Number(today.slice(0, 4)) - 1;
    const previousStart = `${previousYear}-01-01`;
    const previousEnd = `${previousYear}${today.slice(4)}`;
    try {
      const [incomeRes, balanceRes, chainRes, rulesRes, eledgerSettingsRes, eledgerPreflightRes] = await Promise.all([
        axios.get(GL_ENDPOINTS.comparativeIncome, { params: { start, end: today, comparison_start: previousStart, comparison_end: previousEnd } }),
        axios.get(GL_ENDPOINTS.comparativeBalance, { params: { as_of: today, comparison_as_of: previousEnd } }),
        axios.get(GL_ENDPOINTS.chainConsolidated, { params: { start, end: today, as_of: today } }),
        axios.get(GL_ENDPOINTS.intercompanyRules),
        axios.get(GL_ENDPOINTS.eledgerSettings),
        axios.get(GL_ENDPOINTS.eledgerPreflight, { params: { period: eledgerPeriod } }),
      ]);
      setStatements({ income: incomeRes.data?.current, balance: balanceRes.data?.current });
      setComparison({ income: incomeRes.data, balance: balanceRes.data });
      setChainFinance(chainRes.data || null);
      setIntercompany(rulesRes.data || { rules: [], properties: [], can_manage: false });
      if (eledgerSettingsRes.data?.settings) {
        setEledgerSettings({
          taxpayer_id: '', legal_name: '', source_application: 'Syroce PMS', source_application_version: '', software_approval_reference: '',
          ...eledgerSettingsRes.data.settings,
        });
      }
      setEledgerPreflight(eledgerPreflightRes.data || null);
    } catch {
      toast.error('Mali tablolar yüklenemedi.');
    }
  };

  const revalueCurrency = async () => {
    if (!fxForm.closing_rate || Number(fxForm.closing_rate) <= 0) {
      toast.error('Pozitif bir dönem sonu kuru girin.');
      return;
    }
    setFxBusy(true);
    try {
      const res = await axios.post(GL_ENDPOINTS.fxRevalue, {
        ...fxForm,
        currency: fxForm.currency.trim().toUpperCase(),
        closing_rate: Number(fxForm.closing_rate),
      });
      toast.success(res.data?.entry ? `Kur değerleme fişi oluşturuldu: ${res.data.entry.entry_no}` : res.data?.message || 'Kur farkı oluşmadı.');
      await fetchStatements();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Kur değerlemesi yapılamadı.');
    } finally {
      setFxBusy(false);
    }
  };

  const createIntercompanyRule = async () => {
    if (!intercompanyForm.name.trim() || !intercompanyForm.tenant_a_id || !intercompanyForm.tenant_b_id || !intercompanyForm.account_a_code.trim() || !intercompanyForm.account_b_code.trim()) {
      toast.error('Eliminasyon adı, iki otel ve iki hesap kodu zorunludur.');
      return;
    }
    setIntercompanyBusy(true);
    try {
      await axios.post(GL_ENDPOINTS.intercompanyRules, {
        ...intercompanyForm,
        name: intercompanyForm.name.trim(),
        account_a_code: intercompanyForm.account_a_code.trim(),
        account_b_code: intercompanyForm.account_b_code.trim(),
        active: true,
      });
      toast.success('Grup içi eliminasyon kuralı oluşturuldu.');
      setIntercompanyForm({ name: '', kind: 'balance', tenant_a_id: '', account_a_code: '', tenant_b_id: '', account_b_code: '' });
      await fetchStatements();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Eliminasyon kuralı oluşturulamadı.');
    } finally {
      setIntercompanyBusy(false);
    }
  };

  const deleteIntercompanyRule = async (ruleId) => {
    if (!window.confirm('Bu eliminasyon kuralı kaldırılsın mı?')) return;
    setIntercompanyBusy(true);
    try {
      await axios.delete(`${GL_ENDPOINTS.intercompanyRules}/${ruleId}`);
      toast.success('Eliminasyon kuralı kaldırıldı.');
      await fetchStatements();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Eliminasyon kuralı kaldırılamadı.');
    } finally {
      setIntercompanyBusy(false);
    }
  };

  const refreshEledgerPreflight = async () => {
    setEledgerBusy('preflight');
    try {
      const response = await axios.get(GL_ENDPOINTS.eledgerPreflight, { params: { period: eledgerPeriod } });
      setEledgerPreflight(response.data);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'e-Defter ön kontrolü çalıştırılamadı.');
    } finally {
      setEledgerBusy('');
    }
  };

  const saveEledgerSettings = async () => {
    setEledgerBusy('settings');
    try {
      const response = await axios.put(GL_ENDPOINTS.eledgerSettings, {
        taxpayer_id: eledgerSettings.taxpayer_id,
        legal_name: eledgerSettings.legal_name,
        source_application: eledgerSettings.source_application,
        source_application_version: eledgerSettings.source_application_version,
        software_approval_reference: eledgerSettings.software_approval_reference?.trim() || null,
      });
      setEledgerSettings(response.data.settings);
      toast.success('e-Defter hazırlık bilgileri kaydedildi.');
      await refreshEledgerPreflight();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'e-Defter hazırlık bilgileri kaydedilemedi.');
    } finally {
      setEledgerBusy('');
    }
  };

  const downloadEledgerSourcePackage = async () => {
    setEledgerBusy('download');
    try {
      const response = await axios.get(GL_ENDPOINTS.eledgerSourcePackage, {
        params: { period: eledgerPeriod },
        responseType: 'blob',
      });
      const url = URL.createObjectURL(response.data);
      const link = document.createElement('a');
      link.href = url;
      link.download = `syroce-eledger-source-${eledgerPeriod}.zip`;
      link.click();
      URL.revokeObjectURL(url);
      toast.success('Kaynak paket indirildi; mali mühür veya GİB gönderimi yapılmadı.');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Kaynak paket indirilemedi.');
    } finally {
      setEledgerBusy('');
    }
  };

  const downloadReport = async (report, format) => {
    try {
      const today = businessDate;
      const response = await axios.get(GL_ENDPOINTS.exportReport, {
        params: { report, format, as_of: today, start: `${today.slice(0, 4)}-01-01`, end: today },
        responseType: 'blob',
      });
      const url = URL.createObjectURL(response.data);
      const link = document.createElement('a');
      link.href = url;
      link.download = `gl-${report}-${today}.${format}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error('Rapor indirilemedi.');
    }
  };

  const fetchWorkspace = async () => {
    const period = businessDate.slice(0, 7);
    try {
      const [agingRes, expenseRes, revenueRes, assetsRes, operationalRes] = await Promise.all([
        axios.get('/ap/aging'),
        axios.get('/budget/vs-actual', { params: { period, kind: 'expense' } }),
        axios.get('/budget/vs-actual', { params: { period, kind: 'revenue' } }),
        axios.get('/fixed-assets/assets'),
        axios.get(GL_ENDPOINTS.operationalStatus),
      ]);
      setWorkspace({
        aging: agingRes.data,
        expenseBudget: expenseRes.data,
        revenueBudget: revenueRes.data,
        assets: assetsRes.data?.assets || [],
      });
      setOperationalBridge(operationalRes.data || null);
    } catch {
      toast.error('Muhasebe alt defterleri yüklenemedi.');
    }
  };

  const enableOperationalBridge = async () => {
    setOperationalBusy(true);
    try {
      const current = operationalBridge?.mapping || {};
      await axios.put(GL_ENDPOINTS.operationalMapping, {
        enabled: true,
        auto_night_audit: current.auto_night_audit ?? true,
        auto_pos: current.auto_pos ?? true,
        receivable_account_code: current.receivable_account_code || '120',
        revenue_account_code: current.revenue_account_code || '600',
        tax_account_code: current.tax_account_code || '391',
        cash_account_code: current.cash_account_code || '100',
        card_account_code: current.card_account_code || '108',
        bank_account_code: current.bank_account_code || '102',
      });
      toast.success('PMS/POS otomatik muhasebe köprüsü etkinleştirildi.');
      await fetchWorkspace();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Operasyonel muhasebe köprüsü etkinleştirilemedi.');
    } finally {
      setOperationalBusy(false);
    }
  };

  const fetchAccountingIntegrations = async () => {
    try {
      const [nilveraSettingsRes, nilveraQueueRes, apRes, fixedAssetRes] = await Promise.all([
        axios.get(GL_ENDPOINTS.nilveraSettings),
        axios.get(GL_ENDPOINTS.nilveraQueue),
        axios.get(GL_ENDPOINTS.apGLMapping),
        axios.get(GL_ENDPOINTS.fixedAssetGLMapping),
      ]);
      const settings = { ...DEFAULT_NILVERA_GL_SETTINGS, ...(nilveraSettingsRes.data?.settings || {}) };
      setNilveraGL({
        settings,
        queue: nilveraQueueRes.data?.items || [],
        counts: nilveraQueueRes.data?.counts || {},
      });
      setNilveraMappingText({
        incoming_other_tax_accounts_by_code: formatAccountMapping(settings.incoming_other_tax_accounts_by_code),
        incoming_deduction_accounts_by_code: formatAccountMapping(settings.incoming_deduction_accounts_by_code),
        outgoing_vat_accounts_by_rate: formatAccountMapping(settings.outgoing_vat_accounts_by_rate),
        outgoing_accommodation_tax_accounts_by_rate: formatAccountMapping(settings.outgoing_accommodation_tax_accounts_by_rate),
      });
      setApGLMapping({ ...DEFAULT_AP_GL_MAPPING, ...(apRes.data?.mapping || {}) });
      setFixedAssetGLMapping({ ...DEFAULT_FIXED_ASSET_GL_MAPPING, ...(fixedAssetRes.data?.mapping || {}) });
    } catch {
      toast.error('Muhasebe entegrasyon ayarları yüklenemedi.');
    }
  };

  const saveNilveraGL = async () => {
    setIntegrationBusy('nilvera-settings');
    try {
      const settings = nilveraGL.settings;
      const response = await axios.put(GL_ENDPOINTS.nilveraSettings, {
        ...settings,
        incoming_other_tax_accounts_by_code: parseAccountMapping(nilveraMappingText.incoming_other_tax_accounts_by_code, 'Diğer vergi kodu eşlemesi'),
        incoming_deduction_accounts_by_code: parseAccountMapping(nilveraMappingText.incoming_deduction_accounts_by_code, 'Tevkifat/kesinti kodu eşlemesi'),
        outgoing_vat_accounts_by_rate: parseAccountMapping(nilveraMappingText.outgoing_vat_accounts_by_rate, 'KDV oranı eşlemesi'),
        outgoing_accommodation_tax_accounts_by_rate: parseAccountMapping(nilveraMappingText.outgoing_accommodation_tax_accounts_by_rate, 'Konaklama vergisi oranı eşlemesi'),
        incoming_other_tax_account_code: settings.incoming_other_tax_account_code?.trim() || null,
        incoming_deduction_account_code: settings.incoming_deduction_account_code?.trim() || null,
        outgoing_discount_account_code: settings.outgoing_discount_account_code?.trim() || null,
        outgoing_vat_account_code: settings.outgoing_vat_account_code?.trim() || null,
        outgoing_accommodation_tax_account_code: settings.outgoing_accommodation_tax_account_code?.trim() || null,
      });
      setNilveraGL((current) => ({ ...current, settings: response.data.settings }));
      toast.success('Nilvera muhasebe eşlemesi kaydedildi.');
      await fetchAccountingIntegrations();
    } catch (error) {
      toast.error(error.response?.data?.detail || error.message || 'Nilvera muhasebe eşlemesi kaydedilemedi.');
    } finally {
      setIntegrationBusy('');
    }
  };

  const processNilveraQueueItem = async (itemId) => {
    setIntegrationBusy(`nilvera:${itemId}`);
    try {
      const response = await axios.post(`${GL_ENDPOINTS.nilveraQueue}/${itemId}/post`);
      const status = response.data?.item?.status;
      if (status === 'posted') toast.success('Nilvera belgesi Genel Muhasebeye işlendi.');
      else toast.error(response.data?.item?.error_detail || 'Belge inceleme kuyruğunda kaldı.');
      await fetchAccountingIntegrations();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Nilvera belgesi muhasebeleştirilemedi.');
    } finally {
      setIntegrationBusy('');
    }
  };

  const saveAPGLMapping = async () => {
    setIntegrationBusy('ap');
    try {
      const response = await axios.put(GL_ENDPOINTS.apGLMapping, apGLMapping);
      setApGLMapping(response.data.mapping);
      toast.success('Tedarikçi alt defteri GL eşlemesi kaydedildi.');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'AP muhasebe eşlemesi kaydedilemedi.');
    } finally {
      setIntegrationBusy('');
    }
  };

  const saveFixedAssetGLMapping = async () => {
    setIntegrationBusy('fixed-assets');
    try {
      const response = await axios.put(GL_ENDPOINTS.fixedAssetGLMapping, fixedAssetGLMapping);
      setFixedAssetGLMapping(response.data.mapping);
      toast.success('Amortisman GL eşlemesi kaydedildi.');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Amortisman muhasebe eşlemesi kaydedilemedi.');
    } finally {
      setIntegrationBusy('');
    }
  };

  const initializePeriods = async () => {
    setPeriodBusy('initialize');
    try {
      await axios.post(GL_ENDPOINTS.initializePeriods, { fiscal_year: Number(periodYear) });
      toast.success(`${periodYear} mali dönemleri hazırlandı.`);
      await fetchPeriods();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Mali dönemler oluşturulamadı.');
    } finally {
      setPeriodBusy('');
    }
  };

  const changePeriodStatus = async (period, action, reason) => {
    setPeriodBusy(`${period.id}:${action}`);
    try {
      await axios.post(`${GL_ENDPOINTS.periods}/${period.id}/${action}`, { reason: reason.trim() });
      toast.success(action === 'close' ? 'Mali dönem kapatıldı.' : 'Mali dönem yeniden açıldı.');
      await fetchPeriods();
      return true;
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Mali dönem güncellenemedi.');
      return false;
    } finally {
      setPeriodBusy('');
    }
  };

  const closeFiscalYear = async (reason) => {
    setPeriodBusy('year-end');
    try {
      const res = await axios.post(GL_ENDPOINTS.closeYear, {
        fiscal_year: Number(periodYear),
        reason: reason.trim(),
      });
      const entryNo = res.data?.closure?.closing_entry_no;
      toast.success(`${periodYear} kapatıldı; ${periodYear + 1} açılış bakiyeleri devredildi${entryNo ? ` (${entryNo})` : ''}.`);
      await fetchPeriods();
      return true;
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Mali yıl kapatılamadı.');
      return false;
    } finally {
      setPeriodBusy('');
    }
  };

  const requestPeriodAction = (action, period = null) => {
    setPeriodActionReason('');
    setPeriodActionDialog({ action, period });
  };

  const confirmPeriodAction = async () => {
    const reason = periodActionReason.trim();
    if (reason.length < 3) {
      toast.error('Gerekçe en az 3 karakter olmalıdır.');
      return;
    }
    const completed = periodActionDialog.action === 'year-end'
      ? await closeFiscalYear(reason)
      : await changePeriodStatus(periodActionDialog.period, periodActionDialog.action, reason);
    if (completed) {
      setPeriodActionDialog(null);
      setPeriodActionReason('');
    }
  };

  useEffect(() => {
    if (activeTab === 'overview') {
      fetchAccounts();
      fetchJournals();
      fetchPeriods();
    }
    if (activeTab === 'setup') fetchAccounts();
    if (activeTab === 'accounts') fetchAccounts();
    if (activeTab === 'journals') fetchJournals();
    if (activeTab === 'account-ledger') {
      fetchAccounts();
      fetchJournals();
    }
    if (activeTab === 'trial-balance') fetchTrialBalance();
    if (activeTab === 'periods') fetchPeriods();
    if (activeTab === 'statements') fetchStatements();
    if (activeTab === 'workspace') fetchWorkspace();
    if (activeTab === 'integrations') fetchAccountingIntegrations();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, businessDate, periodYear]);

  const handleAddJournalLine = () => {
    setNewJournal(prev => ({
      ...prev,
      lines: [...prev.lines, { account_code: '', debit: 0, credit: 0, description: '', currency: '', foreign_amount: '', exchange_rate: '' }]
    }));
  };

  const handleLineChange = (index, field, value) => {
    const updated = [...newJournal.lines];
    if (field === 'debit' || field === 'credit') {
      value = parseFloat(value) || 0;
      // You can only have debit OR credit
      if (field === 'debit' && value > 0) updated[index].credit = 0;
      if (field === 'credit' && value > 0) updated[index].debit = 0;
    }
    updated[index][field] = value;
    setNewJournal({ ...newJournal, lines: updated });
  };

  const handleSubmitJournal = async () => {
    const validationError = getJournalValidationError(newJournal, ledgerCurrency);
    if (validationError) {
      toast.error(validationError);
      return;
    }

    setJournalSaving(true);
    try {
      if (editingVoucher) {
        await axios.put(`${GL_ENDPOINTS.vouchers}/${editingVoucher.id}`, {
          ...toVoucherPayload(newJournal, ledgerCurrency),
          version: editingVoucher.version,
        });
        toast.success('Taslak fiş güncellendi. Değişiklik geçmişi korundu.');
      } else {
        await axios.post(GL_ENDPOINTS.vouchers, toVoucherPayload(newJournal, ledgerCurrency));
        toast.success('Taslak fiş oluşturuldu. Yevmiyeye geçmesi için inceleme ve onay gerekir.');
      }
      setNewJournal(emptyJournal(businessDate));
      setEditingVoucher(null);
      await fetchJournals();
    } catch (e) {
      const detail = e.response?.data?.detail;
      const message = Array.isArray(detail)
        ? detail.map((item) => item.msg || String(item)).join(' ')
        : detail;
      toast.error(message || 'Taslak fiş oluşturulurken hata oluştu.');
    } finally {
      setJournalSaving(false);
    }
  };

  const editVoucher = (voucher) => {
    setEditingVoucher(voucher);
    setNewJournal(journalFromVoucher(voucher));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const runVoucherAction = async (voucher, action, reason = '') => {
    const labels = {
      submit: 'incelemeye gönderme',
      approve: 'onaylama',
      reject: 'reddetme',
      cancel: 'iptal',
      post: 'yevmiye kaydı',
    };
    const busyKey = `${voucher.id}:${action}`;
    setVoucherBusy(busyKey);
    try {
      await axios.post(
        `${GL_ENDPOINTS.vouchers}/${voucher.id}/${action}`,
        action === 'post' ? undefined : { reason: reason.trim() },
      );
      toast.success(action === 'post' ? 'Onaylı fiş yevmiyeye işlendi.' : `Fiş ${labels[action]} adımını tamamladı.`);
      await fetchJournals();
      return true;
    } catch (error) {
      toast.error(error.response?.data?.detail || `Fiş ${labels[action]} işlemi tamamlanamadı.`);
      return false;
    } finally {
      setVoucherBusy('');
    }
  };

  const requestVoucherAction = async (voucher, action) => {
    if (action === 'post') {
      await runVoucherAction(voucher, action);
      return;
    }
    setVoucherActionReason('');
    setVoucherActionDialog({ voucher, action });
  };

  const confirmVoucherAction = async () => {
    const reason = voucherActionReason.trim();
    if (reason.length < 3) {
      toast.error('Gerekçe en az 3 karakter olmalıdır.');
      return;
    }
    if (await runVoucherAction(voucherActionDialog.voucher, voucherActionDialog.action, reason)) {
      setVoucherActionDialog(null);
      setVoucherActionReason('');
    }
  };

  const requestJournalReversal = (journal) => {
    setReversalReason('');
    setReversalDate(businessDate);
    setReversalDialog({ journal });
  };

  const reverseJournal = async (journal, reason, date) => {
    const key = reversalKeys.current[journal.id] || newRequestKey();
    reversalKeys.current[journal.id] = key;
    setReversalBusy(journal.id);
    try {
      await axios.post(`${GL_ENDPOINTS.journal}/${journal.id}/reverse`, {
        date,
        reason: reason.trim(),
        idempotency_key: key,
      });
      delete reversalKeys.current[journal.id];
      toast.success('Bağlı ters kayıt fişi oluşturuldu.');
      await fetchJournals();
      return true;
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Ters kayıt oluşturulamadı.');
      return false;
    } finally {
      setReversalBusy('');
    }
  };

  const confirmJournalReversal = async () => {
    const reason = reversalReason.trim();
    if (reason.length < 3) {
      toast.error('Gerekçe en az 3 karakter olmalıdır.');
      return;
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(reversalDate)) {
      toast.error('Ters kayıt tarihi YYYY-MM-DD biçiminde olmalıdır.');
      return;
    }
    if (await reverseJournal(reversalDialog.journal, reason, reversalDate)) {
      setReversalDialog(null);
      setReversalReason('');
    }
  };

  const yearEndReady = periods.length === 12
    && periods.filter((period) => Number(period.period_no) < 12).every((period) => period.status === 'closed')
    && periods.find((period) => Number(period.period_no) === 12)?.status === 'open';
  const knownAccountCodes = new Set(accounts.filter((account) => account.active !== false).map((account) => account.code));
  const missingIntegrationAccountCodes = collectIntegrationAccountCodes(
    nilveraGL.settings,
    apGLMapping,
    fixedAssetGLMapping,
  ).filter((code) => !knownAccountCodes.has(code));
  const journalValidationError = getJournalValidationError(newJournal, ledgerCurrency);

  return (
    <div className="p-4 sm:p-6 max-w-7xl mx-auto overflow-x-hidden">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Genel Muhasebe</h1>
        <p className="text-gray-500 mt-1">Tek Düzen Hesap Planı, Yevmiye Kayıtları ve Mizan</p>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
        <div className="grid items-start gap-5 lg:grid-cols-[270px_minmax(0,1fr)]">
          <GeneralLedgerNavigation activeTab={activeTab} onSelect={handleTabChange} onNavigate={navigate} />
          <main className="min-w-0">
        <TabsContent value="overview" className="mt-0">
          <GeneralLedgerOverview
            accounts={accounts}
            vouchers={vouchers}
            trialBalance={trialBalance}
            periods={periods}
            onSelect={handleTabChange}
          />
        </TabsContent>

        <TabsContent value="setup">
          <AccountingSetupWizard onAccountsChanged={fetchAccounts} />
        </TabsContent>

        {/* TDHP Accounts */}
        <TabsContent value="accounts">
          <Card>
            <CardHeader className="flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
              <div>
                <CardTitle>Tek Düzen Hesap Planı</CardTitle>
                <p className="text-xs text-slate-500 mt-1">Standart plan mevcut özel hesapları değiştirmeden eksik TDHP ve parasal hesap işaretlerini tamamlar.</p>
              </div>
              <Button variant="outline" onClick={initializeAccounts} disabled={initializingAccounts} size="sm">
                {initializingAccounts ? 'Güncelleniyor...' : 'Standart Planı Tamamla'}
              </Button>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
              <table className="min-w-[680px] w-full text-sm text-left">
                <thead className="bg-gray-50 text-gray-600">
                  <tr>
                    <th className="p-3 font-semibold rounded-tl-lg">Hesap Kodu</th>
                    <th className="p-3 font-semibold">Hesap Adı</th>
                    <th className="p-3 font-semibold">Tip</th>
                    <th className="p-3 font-semibold">Nitelik</th>
                    <th className="p-3 font-semibold text-right rounded-tr-lg">Güncel Bakiye</th>
                  </tr>
                </thead>
                <tbody>
                  {accounts.map(acc => (
                    <tr key={acc.code} className="border-b last:border-0 hover:bg-gray-50">
                      <td className="p-3 font-medium text-blue-600">{acc.code}</td>
                      <td className="p-3 text-gray-800">{acc.name}</td>
                      <td className="p-3 text-gray-500">{acc.type}</td>
                      <td className="p-3 text-xs text-slate-600">{acc.monetary ? 'Parasal' : acc.normal_balance === 'credit' && acc.type === 'asset' ? 'Ters bakiye' : 'Standart'}</td>
                      <td className="p-3 text-right font-medium">
                        {acc.balance !== 0 ? fmtMoney(Math.abs(acc.balance)) : '-'}
                      </td>
                    </tr>
                  ))}
                  {accounts.length === 0 && (
                    <tr>
                      <td colSpan="5" className="text-center p-8 text-gray-500">
                        <p className="mb-3">Kayıtlı hesap bulunamadı.</p>
                        <Button onClick={initializeAccounts} disabled={initializingAccounts} size="sm">
                          {initializingAccounts ? 'Oluşturuluyor...' : 'Standart Hesap Planını Oluştur'}
                        </Button>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="account-ledger">
          <AccountLedgerView journals={journals} accounts={accounts} formatMoney={fmtMoney} />
        </TabsContent>

        {/* Journals */}
        <TabsContent value="journals">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            
            {/* New Journal Form */}
            <div className="lg:col-span-2">
              <Card>
                <CardHeader>
                  <CardTitle>{editingVoucher ? `${editingVoucher.voucher_no} Taslağını Düzenle` : 'Yeni Taslak Muhasebe Fişi'}</CardTitle>
                  <p className="text-sm text-gray-500">Taslak doğrudan yevmiyeye yazılmaz. Hazırlayan kişi incelemeye gönderir; farklı bir yetkili onaylar ve kayıt işlemini tamamlar.</p>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid gap-4 sm:grid-cols-3">
                    <div>
                      <label className="text-sm font-medium mb-1 block">Tarih</label>
                      <Input type="date" value={newJournal.date} onChange={e => setNewJournal({...newJournal, date: e.target.value})} />
                    </div>
                    <div>
                      <label className="text-sm font-medium mb-1 block">Fiş Tipi</label>
                      <select className="w-full h-10 px-3 py-2 border rounded-md text-sm bg-white" value={newJournal.type} onChange={e => setNewJournal({...newJournal, type: e.target.value})}>
                        <option value="Mahsup">Mahsup Fişi</option>
                        <option value="Tahsilat">Tahsilat Fişi</option>
                        <option value="Tediye">Tediye Fişi</option>
                      </select>
                    </div>
                    <div>
                      <label className="text-sm font-medium mb-1 block">Açıklama</label>
                      <Input type="text" placeholder="Fiş Geneli Açıklaması" value={newJournal.description} onChange={e => setNewJournal({...newJournal, description: e.target.value})} />
                    </div>
                  </div>

                  <div className="border rounded-md overflow-x-auto mt-4">
                    <table className="min-w-[780px] w-full text-sm">
                      <thead className="bg-gray-100">
                        <tr>
                          <th className="p-2 text-left w-32">Hesap Kodu</th>
                          <th className="p-2 text-left">Açıklama</th>
                          <th className="p-2 text-left w-20">Döviz</th>
                          <th className="p-2 text-right w-28">Yabancı Tutar</th>
                          <th className="p-2 text-right w-24">Kur</th>
                          <th className="p-2 text-right w-32">Borç (₺)</th>
                          <th className="p-2 text-right w-32">Alacak (₺)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {newJournal.lines.map((line, idx) => (
                          <tr key={idx} className="border-b">
                            <td className="p-1"><Input className="h-8" value={line.account_code} onChange={e => handleLineChange(idx, 'account_code', e.target.value)} placeholder="100, 120" /></td>
                            <td className="p-1"><Input className="h-8" value={line.description} onChange={e => handleLineChange(idx, 'description', e.target.value)} /></td>
                            <td className="p-1"><Input className="h-8 uppercase" maxLength={3} value={line.currency} onChange={e => handleLineChange(idx, 'currency', e.target.value)} placeholder="USD" /></td>
                            <td className="p-1"><Input type="number" className="h-8 text-right" value={line.foreign_amount} onChange={e => handleLineChange(idx, 'foreign_amount', e.target.value)} /></td>
                            <td className="p-1"><Input type="number" className="h-8 text-right" value={line.exchange_rate} onChange={e => handleLineChange(idx, 'exchange_rate', e.target.value)} /></td>
                            <td className="p-1"><Input type="number" className="h-8 text-right bg-red-50" value={line.debit || ''} onChange={e => handleLineChange(idx, 'debit', e.target.value)} /></td>
                            <td className="p-1"><Input type="number" className="h-8 text-right bg-green-50" value={line.credit || ''} onChange={e => handleLineChange(idx, 'credit', e.target.value)} /></td>
                          </tr>
                        ))}
                      </tbody>
                      <tfoot className="bg-gray-50 font-bold">
                        <tr>
                          <td colSpan="5" className="p-2 text-right">TOPLAM:</td>
                          <td className="p-2 text-right text-red-600">{newJournal.lines.reduce((a, b) => a + (parseFloat(b.debit)||0), 0).toFixed(2)}</td>
                          <td className="p-2 text-right text-green-600">{newJournal.lines.reduce((a, b) => a + (parseFloat(b.credit)||0), 0).toFixed(2)}</td>
                        </tr>
                      </tfoot>
                    </table>
                  </div>
                  <div className="flex flex-wrap justify-between gap-3 mt-4">
                    <Button variant="outline" onClick={handleAddJournalLine}><Plus className="w-4 h-4 mr-2" /> Satır Ekle</Button>
                    <div className="flex gap-2">
                      {editingVoucher && <Button variant="ghost" onClick={() => { setEditingVoucher(null); setNewJournal(emptyJournal(businessDate)); }}>Düzenlemeyi İptal Et</Button>}
                      <Button onClick={handleSubmitJournal} disabled={journalSaving || !!journalValidationError} title={journalValidationError || undefined} className="bg-blue-600 hover:bg-blue-700 text-white"><Save className="w-4 h-4 mr-2" /> {journalSaving ? 'Kaydediliyor...' : editingVoucher ? 'Taslağı Güncelle' : 'Taslak Oluştur'}</Button>
                    </div>
                  </div>
                  {journalValidationError && <p className="text-xs text-slate-500" role="status">{journalValidationError}</p>}
                </CardContent>
              </Card>
            </div>

            {/* Recent Journals */}
            <div>
              {integrityAudit && (
                <div className={`mb-4 rounded-lg border p-3 ${integrityAudit.fully_sealed ? 'border-emerald-200 bg-emerald-50' : 'border-amber-300 bg-amber-50'}`} data-testid="gl-integrity-audit">
                  <div className="flex items-center justify-between gap-2">
                    <p className="flex items-center gap-1.5 text-sm font-semibold text-gray-900"><ShieldCheck className="h-4 w-4" /> Yevmiye bütünlük zinciri</p>
                    <span className={`text-xs font-semibold ${integrityAudit.fully_sealed ? 'text-emerald-700' : 'text-amber-700'}`}>
                      {integrityAudit.fully_sealed ? 'Doğrulandı' : 'İnceleme gerekli'}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-gray-600">
                    {integrityAudit.counts?.sealed || 0} mühürlü kayıt · {integrityAudit.counts?.legacy_unsealed || 0} eski mühürsüz kayıt · {integrityAudit.counts?.issues || 0} bütünlük sorunu
                  </p>
                </div>
              )}
              {sequenceAudit && (
                <div className={`mb-4 rounded-lg border p-3 ${sequenceAudit.healthy ? 'border-emerald-200 bg-emerald-50' : 'border-amber-300 bg-amber-50'}`}>
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-gray-900">Yevmiye sıra denetimi</p>
                    <span className={`text-xs font-semibold ${sequenceAudit.healthy ? 'text-emerald-700' : 'text-amber-700'}`}>
                      {sequenceAudit.healthy ? 'Sağlıklı' : 'İnceleme gerekli'}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-gray-600">
                    {sequenceAudit.totals?.posted || 0} kayıt · {sequenceAudit.totals?.void || 0} iptal · {sequenceAudit.totals?.reserved || 0} bekleyen · {sequenceAudit.totals?.missing || 0} eksik sıra
                  </p>
                </div>
              )}
              <Card className="mb-4">
                <CardHeader>
                  <CardTitle className="text-base">Fiş İş Akışı</CardTitle>
                  <p className="text-xs text-gray-500">Taslak, inceleme ve onay kuyruğu</p>
                </CardHeader>
                <CardContent className="space-y-3 max-h-[420px] overflow-y-auto" data-testid="gl-voucher-queue">
                  {vouchers.map((voucher) => {
                    const status = VOUCHER_STATUS[voucher.status] || { label: voucher.status, className: 'bg-gray-100 text-gray-700' };
                    return (
                      <div key={voucher.id} className="rounded-lg border bg-white p-3">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold text-gray-900">{voucher.voucher_no}</p>
                            <p className="truncate text-xs text-gray-500">{voucher.date} · {voucher.memo}</p>
                          </div>
                          <span className={`shrink-0 rounded-full px-2 py-1 text-[11px] font-semibold ${status.className}`}>{status.label}</span>
                        </div>
                        {voucher.rejection_reason && <p className="mt-2 text-xs text-red-700">Ret: {voucher.rejection_reason}</p>}
                        {voucher.journal_entry_no && <p className="mt-2 text-xs text-emerald-700">Yevmiye: {voucher.journal_entry_no}</p>}
                        {voucherActionNames(voucher.status).length > 0 && (
                          <div className="mt-3 flex flex-wrap gap-2">
                            {voucherActionNames(voucher.status).includes('edit') && (
                              <Button size="sm" variant="outline" disabled={!!voucherBusy} onClick={() => editVoucher(voucher)}>Düzenle</Button>
                            )}
                            {voucherActionNames(voucher.status).includes('submit') && (
                              <Button size="sm" variant="outline" disabled={!!voucherBusy} onClick={() => requestVoucherAction(voucher, 'submit')}><Send className="mr-1.5 h-3.5 w-3.5" /> İncelemeye Gönder</Button>
                            )}
                            {voucherActionNames(voucher.status).includes('approve') && (
                              <Button size="sm" disabled={!!voucherBusy} onClick={() => requestVoucherAction(voucher, 'approve')}><CheckCircle2 className="mr-1.5 h-3.5 w-3.5" /> Onayla</Button>
                            )}
                            {voucherActionNames(voucher.status).includes('reject') && (
                              <Button size="sm" variant="outline" disabled={!!voucherBusy} onClick={() => requestVoucherAction(voucher, 'reject')}><XCircle className="mr-1.5 h-3.5 w-3.5" /> Reddet</Button>
                            )}
                            {voucherActionNames(voucher.status).includes('post') && (
                              <Button size="sm" disabled={!!voucherBusy} onClick={() => requestVoucherAction(voucher, 'post')}><Save className="mr-1.5 h-3.5 w-3.5" /> Yevmiyeye İşle</Button>
                            )}
                            {voucherActionNames(voucher.status).includes('cancel') && (
                              <Button size="sm" variant="ghost" disabled={!!voucherBusy} onClick={() => requestVoucherAction(voucher, 'cancel')}>İptal Et</Button>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                  {vouchers.length === 0 && <p className="py-4 text-center text-sm text-gray-500">Bekleyen muhasebe fişi yok.</p>}
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Son Fişler</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4 max-h-[600px] overflow-y-auto">
                  {journals.map(j => (
                    <div key={j.id} className="p-3 border rounded-lg hover:border-blue-300 transition-colors bg-white">
                      <div className="flex justify-between items-start mb-2">
                        <div>
                          <span className="text-xs font-bold px-2 py-1 bg-gray-100 text-gray-600 rounded-full">{j.entry_no || (j.source === 'reversal' ? 'Ters Kayıt' : j.source_ref || j.source || 'Fiş')}</span>
                          <span className="text-xs text-gray-400 ml-2">{j.date}</span>
                        </div>
                        <span className="font-bold text-gray-900">{fmtMoney(j.total_debit)}</span>
                      </div>
                      <p className="text-sm text-gray-600 truncate">{j.memo}</p>
                      {j.reversal_status === 'reversed' && <p className="text-xs text-amber-700 mt-2">Bu fiş için ters kayıt oluşturuldu.</p>}
                      {j.source !== 'reversal' && j.reversal_status !== 'reversed' && (
                        <Button size="sm" variant="outline" className="w-full mt-3" disabled={reversalBusy === j.id} onClick={() => requestJournalReversal(j)}>
                          <RotateCcw className="w-3.5 h-3.5 mr-1.5" /> {reversalBusy === j.id ? 'Oluşturuluyor...' : 'Ters Kayıt Oluştur'}
                        </Button>
                      )}
                    </div>
                  ))}
                  {journals.length === 0 && <p className="text-center text-sm text-gray-500 py-4">Henüz fiş girilmemiş.</p>}
                </CardContent>
              </Card>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="periods">
          <Card>
            <CardHeader className="flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
              <div>
                <CardTitle className="flex items-center gap-2"><CalendarRange className="w-5 h-5" /> Mali Dönem Yönetimi</CardTitle>
                <p className="text-sm text-gray-500 mt-1">Kapalı döneme yeni fiş veya entegrasyon kaydı gönderilemez.</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Input className="w-28" type="number" min="2000" max="2100" value={periodYear} onChange={(e) => setPeriodYear(Number(e.target.value))} />
                <Button variant="outline" onClick={initializePeriods} disabled={periodBusy === 'initialize'}>
                  {periodBusy === 'initialize' ? 'Hazırlanıyor...' : '12 Dönemi Hazırla'}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className={`mb-4 rounded-lg border p-4 ${yearEndStatus?.closed ? 'border-slate-300 bg-slate-50' : 'border-blue-200 bg-blue-50/50'}`}>
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                  <div>
                    <p className="font-semibold text-gray-900">{periodYear} yıl sonu kapanışı</p>
                    <p className="text-xs text-gray-600 mt-1">
                      {yearEndStatus?.closed
                        ? `${yearEndStatus.closure?.closing_entry_no || 'Kapanış fişi olmadan'} kapatıldı; ${yearEndStatus.closure?.opening_fiscal_year} açılış bakiyeleri hazır.`
                        : 'İlk 11 dönem kapandıktan sonra gelir/gider hesapları 690 üzerinden 590/591’e devredilir.'}
                    </p>
                  </div>
                  <Button onClick={() => requestPeriodAction('year-end')} disabled={yearEndStatus?.closed || periodBusy === 'year-end' || !yearEndReady}>
                    <Landmark className="w-4 h-4 mr-2" />
                    {yearEndStatus?.closed
                      ? 'Yıl Kapatıldı'
                      : periodBusy === 'year-end'
                        ? 'Kapatılıyor...'
                        : yearEndReady
                          ? 'Yıl Sonunu Kapat ve Devret'
                          : 'Önce Aylık Dönemleri Kapat'}
                  </Button>
                </div>
              </div>
              {periods.length === 0 ? (
                <div className="text-center py-10 text-gray-500">Bu mali yıl için dönem bulunamadı.</div>
              ) : (
                <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {periods.map((period) => {
                    const closed = period.status === 'closed';
                    const action = closed ? 'reopen' : 'close';
                    const busy = periodBusy === `${period.id}:${action}`;
                    return (
                      <div key={period.id} className={`rounded-lg border p-3 ${closed ? 'border-slate-300 bg-slate-50' : 'border-emerald-200 bg-emerald-50/40'}`}>
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <p className="font-semibold text-gray-900">{period.name}</p>
                            <p className="text-xs text-gray-500">{period.start_date} — {period.end_date}</p>
                          </div>
                          <span className={`text-xs px-2 py-1 rounded-full font-medium ${closed ? 'bg-slate-200 text-slate-700' : 'bg-emerald-100 text-emerald-700'}`}>
                            {closed ? 'Kapalı' : 'Açık'}
                          </span>
                        </div>
                        {closed && period.close_reason && <p className="mt-2 text-xs text-slate-600">Gerekçe: {period.close_reason}</p>}
                        <Button className="w-full mt-3" size="sm" variant={closed ? 'outline' : 'default'} disabled={busy} onClick={() => requestPeriodAction(action, period)}>
                          {closed ? <Unlock className="w-3.5 h-3.5 mr-1.5" /> : <LockKeyhole className="w-3.5 h-3.5 mr-1.5" />}
                          {busy ? 'İşleniyor...' : closed ? 'Yeniden Aç' : 'Dönemi Kapat'}
                        </Button>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Trial Balance */}
        <TabsContent value="trial-balance">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>Geçici Mizan</CardTitle>
              <Button variant="outline" size="sm" onClick={() => window.print()}><FileText className="w-4 h-4 mr-2" />Yazdır</Button>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
              <table className="min-w-[760px] w-full text-sm text-left">
                <thead className="bg-gray-800 text-white">
                  <tr>
                    <th className="p-3 font-semibold rounded-tl-lg">Hesap</th>
                    <th className="p-3 font-semibold">Hesap Adı</th>
                    <th className="p-3 font-semibold text-right">Borç Toplam</th>
                    <th className="p-3 font-semibold text-right">Alacak Toplam</th>
                    <th className="p-3 font-semibold text-center">Bakiye Yönü</th>
                    <th className="p-3 font-semibold text-right rounded-tr-lg">Bakiye</th>
                  </tr>
                </thead>
                <tbody>
                  {trialBalance.lines?.map((line) => (
                    <tr key={line.code} className="border-b hover:bg-gray-50">
                      <td className="p-3 font-medium text-blue-600">{line.code}</td>
                      <td className="p-3 text-gray-800">{line.name}</td>
                      <td className="p-3 text-right">{line.total_debit > 0 ? fmtMoney(line.total_debit) : '-'}</td>
                      <td className="p-3 text-right">{line.total_credit > 0 ? fmtMoney(line.total_credit) : '-'}</td>
                      <td className="p-3 text-center">
                        <span className={`text-xs px-2 py-1 rounded-full ${line.balance_type === 'Borç' ? 'bg-red-100 text-red-700' : line.balance_type === 'Alacak' ? 'bg-green-100 text-green-700' : 'bg-gray-100'}`}>
                          {line.balance_type}
                        </span>
                      </td>
                      <td className="p-3 text-right font-bold text-gray-900">{line.balance > 0 ? fmtMoney(line.balance) : '-'}</td>
                    </tr>
                  ))}
                  {(!trialBalance.lines || trialBalance.lines.length === 0) && (
                    <tr><td colSpan="6" className="text-center p-8 text-gray-500">Mizan alınacak hareket bulunamadı.</td></tr>
                  )}
                </tbody>
                {trialBalance.lines && trialBalance.lines.length > 0 && (
                  <tfoot className="bg-gray-100 font-bold border-t-2 border-gray-300">
                    <tr>
                      <td colSpan="2" className="p-3 text-right">GENEL TOPLAM:</td>
                      <td className="p-3 text-right text-red-600">{fmtMoney(trialBalance.totals?.total_debit || 0)}</td>
                      <td className="p-3 text-right text-green-600">{fmtMoney(trialBalance.totals?.total_credit || 0)}</td>
                      <td colSpan="2"></td>
                    </tr>
                  </tfoot>
                )}
              </table>
              </div>
              {trialBalance.totals && !trialBalance.totals.balanced && (
                <div className="mt-4 p-4 bg-red-50 border border-red-200 text-red-700 rounded-lg flex items-start gap-2">
                  <AlertCircle className="w-5 h-5 mt-0.5" />
                  <div>
                    <h4 className="font-bold">Mizan Denk Değil!</h4>
                    <p className="text-sm">Borç ve Alacak toplamları birbirine eşit değil. Bu durum geçmiş hatalı fişlerden veya yuvarlama farklarından kaynaklanabilir.</p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="statements">
          <div className="flex flex-wrap gap-2 mb-4">
            <Button variant="outline" onClick={() => downloadReport('trial_balance', 'xlsx')}>Mizan Excel</Button>
            <Button variant="outline" onClick={() => downloadReport('income_statement', 'xlsx')}>Gelir Tablosu Excel</Button>
            <Button variant="outline" onClick={() => downloadReport('balance_sheet', 'pdf')}>Bilanço PDF</Button>
            <Button variant="outline" onClick={() => downloadReport('journal', 'pdf')}>Yevmiye PDF</Button>
          </div>
          <div className="grid lg:grid-cols-2 gap-5">
            <Card>
              <CardHeader><CardTitle>Gelir Tablosu · Yılbaşından Bugüne</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {(statements.income?.revenue || []).map((row) => <div key={row.account_code} className="flex justify-between text-sm"><span>{row.account_code} · {row.account_name}</span><span className="font-medium">{fmtMoney(row.amount)}</span></div>)}
                <div className="border-t pt-2 flex justify-between font-semibold text-emerald-700"><span>Toplam Gelir</span><span>{fmtMoney(statements.income?.totals?.revenue || 0)} <small>({comparison.income?.variance?.revenue?.percent ?? '—'}%)</small></span></div>
                {(statements.income?.expenses || []).map((row) => <div key={row.account_code} className="flex justify-between text-sm"><span>{row.account_code} · {row.account_name}</span><span className="font-medium">{fmtMoney(row.amount)}</span></div>)}
                <div className="border-t pt-2 flex justify-between font-semibold text-red-700"><span>Toplam Gider</span><span>{fmtMoney(statements.income?.totals?.expenses || 0)} <small>({comparison.income?.variance?.expenses?.percent ?? '—'}%)</small></span></div>
                <div className="rounded-lg bg-slate-900 text-white p-3 flex justify-between font-bold"><span>Net Dönem Kârı / Zararı</span><span>{fmtMoney(statements.income?.totals?.net_income || 0)} <small>({comparison.income?.variance?.net_income?.percent ?? '—'}%)</small></span></div>
                <p className="text-xs text-slate-500">Parantez içindeki oranlar önceki yılın aynı dönemine göre değişimi gösterir.</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Bilanço · Bugün</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {['assets', 'liabilities', 'equity'].map((section) => (
                  <div key={section} className="space-y-1">
                    <p className="text-xs font-bold uppercase text-slate-500">{section === 'assets' ? 'Varlıklar' : section === 'liabilities' ? 'Yükümlülükler' : 'Özkaynaklar'}</p>
                    {(statements.balance?.[section] || []).map((row) => <div key={row.account_code} className="flex justify-between text-sm"><span>{row.account_code} · {row.account_name}</span><span>{fmtMoney(row.amount)}</span></div>)}
                  </div>
                ))}
                <div className="flex justify-between text-sm border-t pt-2"><span>Cari dönem kârı/zararı</span><span>{fmtMoney(statements.balance?.current_earnings?.amount || 0)}</span></div>
                <div className={`rounded-lg p-3 flex justify-between font-bold ${statements.balance?.totals?.balanced ? 'bg-emerald-50 text-emerald-800' : 'bg-red-50 text-red-800'}`}>
                  <span>Bilanço dengesi</span><span>{statements.balance?.totals?.balanced ? 'Dengeli' : `Fark: ${fmtMoney(statements.balance?.totals?.difference || 0)}`}</span>
                </div>
                <p className="text-xs text-slate-500">Varlık değişimi: {comparison.balance?.variance?.assets?.percent ?? '—'}% · Özkaynak değişimi: {comparison.balance?.variance?.equity?.percent ?? '—'}%</p>
              </CardContent>
            </Card>
          </div>
          <Card className="mt-5">
            <CardHeader><CardTitle>Dönem Sonu Kur Değerlemesi</CardTitle></CardHeader>
            <CardContent>
              <p className="text-sm text-slate-500 mb-3">Yabancı para hareketi bulunan “parasal” hesapları girilen kapanış kuruyla değerler; canlı kur servisi çağrılmaz.</p>
              <div className="grid sm:grid-cols-4 gap-3">
                <Input type="date" value={fxForm.date} onChange={(e) => setFxForm({ ...fxForm, date: e.target.value })} />
                <Input maxLength={3} className="uppercase" value={fxForm.currency} onChange={(e) => setFxForm({ ...fxForm, currency: e.target.value })} placeholder="USD" />
                <Input type="number" min="0" step="0.000001" value={fxForm.closing_rate} onChange={(e) => setFxForm({ ...fxForm, closing_rate: e.target.value })} placeholder="Kapanış kuru" />
                <Button onClick={revalueCurrency} disabled={fxBusy}>{fxBusy ? 'Değerleniyor...' : 'Kur Farkı Fişi Oluştur'}</Button>
              </div>
            </CardContent>
          </Card>
          {chainFinance?.property_count > 1 && (
            <Card className="mt-5">
              <CardHeader><CardTitle>Zincir Konsolide Finans · {chainFinance.property_count} Otel</CardTitle></CardHeader>
              <CardContent>
                <div className="grid sm:grid-cols-3 gap-3 mb-4">
                  <div className="rounded-lg bg-emerald-50 p-3"><p className="text-xs text-slate-500">Toplam Gelir</p><p className="text-xl font-bold text-emerald-700">{fmtMoney(chainFinance.totals?.revenue?.amount || 0)}</p></div>
                  <div className="rounded-lg bg-red-50 p-3"><p className="text-xs text-slate-500">Toplam Gider</p><p className="text-xl font-bold text-red-700">{fmtMoney(chainFinance.totals?.expenses?.amount || 0)}</p></div>
                  <div className="rounded-lg bg-slate-100 p-3"><p className="text-xs text-slate-500">Konsolide Net Sonuç</p><p className="text-xl font-bold">{fmtMoney(chainFinance.totals?.net_income?.amount || 0)}</p></div>
                </div>
                <div className="rounded-lg border bg-slate-50 p-3 mb-4 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold">Grup içi eliminasyon</span>
                    <span className={chainFinance.consolidation?.intercompany_eliminations_applied ? 'text-emerald-700' : 'text-amber-700'}>
                      {chainFinance.consolidation?.applied_rule_count || 0}/{chainFinance.consolidation?.rule_count || 0} kural uygulandı
                    </span>
                  </div>
                  {chainFinance.consolidation?.intercompany_eliminations_applied && (
                    <p className="text-xs text-slate-600 mt-1">
                      Brüt gelir {fmtMoney(chainFinance.raw_totals?.revenue?.amount || 0)} → net {fmtMoney(chainFinance.totals?.revenue?.amount || 0)} · Brüt varlık {fmtMoney(chainFinance.raw_totals?.assets?.amount || 0)} → net {fmtMoney(chainFinance.totals?.assets?.amount || 0)}
                    </p>
                  )}
                  {(chainFinance.consolidation?.eliminations || []).map((item) => (
                    <div key={item.rule_id} className="flex justify-between border-t mt-2 pt-2 text-xs">
                      <span>{item.name}</span><span>{item.status === 'applied' ? fmtMoney(item.matched_amount) : 'Eşleşen bakiye yok'}</span>
                    </div>
                  ))}
                </div>
                <div className="space-y-2">
                  {chainFinance.properties.map((property) => (
                    <div key={property.tenant_id} className="flex items-center justify-between rounded border p-2 text-sm">
                      <span>{property.property_name}</span>
                      <span className="font-medium">{fmtMoney(property.income?.net_income || 0)}</span>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-amber-700 mt-3">{chainFinance.consolidation?.warning}</p>
                <div className="mt-5 border-t pt-4 space-y-3">
                  <h4 className="font-semibold">Eliminasyon Kuralları</h4>
                  {(intercompany.rules || []).map((rule) => (
                    <div key={rule.id} className="flex items-center justify-between gap-3 rounded border p-2 text-xs">
                      <span><strong>{rule.name}</strong> · {rule.tenant_a_id}/{rule.account_a_code} ↔ {rule.tenant_b_id}/{rule.account_b_code}</span>
                      {intercompany.can_manage && <Button size="sm" variant="outline" disabled={intercompanyBusy} onClick={() => deleteIntercompanyRule(rule.id)}>Kaldır</Button>}
                    </div>
                  ))}
                  {intercompany.can_manage && (
                    <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-2 rounded-lg bg-slate-50 p-3">
                      <Input value={intercompanyForm.name} onChange={(e) => setIntercompanyForm({ ...intercompanyForm, name: e.target.value })} placeholder="Kural adı" />
                      <select className="rounded-md border px-3 py-2 text-sm" value={intercompanyForm.kind} onChange={(e) => setIntercompanyForm({ ...intercompanyForm, kind: e.target.value })}>
                        <option value="balance">Varlık / borç</option><option value="income">Gelir / gider</option>
                      </select>
                      <select className="rounded-md border px-3 py-2 text-sm" value={intercompanyForm.tenant_a_id} onChange={(e) => setIntercompanyForm({ ...intercompanyForm, tenant_a_id: e.target.value })}>
                        <option value="">Birinci otel</option>{(intercompany.properties || []).map((property) => <option key={property.tenant_id} value={property.tenant_id}>{property.property_name}</option>)}
                      </select>
                      <Input value={intercompanyForm.account_a_code} onChange={(e) => setIntercompanyForm({ ...intercompanyForm, account_a_code: e.target.value })} placeholder="Birinci hesap" />
                      <select className="rounded-md border px-3 py-2 text-sm" value={intercompanyForm.tenant_b_id} onChange={(e) => setIntercompanyForm({ ...intercompanyForm, tenant_b_id: e.target.value })}>
                        <option value="">İkinci otel</option>{(intercompany.properties || []).map((property) => <option key={property.tenant_id} value={property.tenant_id}>{property.property_name}</option>)}
                      </select>
                      <Input value={intercompanyForm.account_b_code} onChange={(e) => setIntercompanyForm({ ...intercompanyForm, account_b_code: e.target.value })} placeholder="İkinci hesap" />
                      <Button className="lg:col-span-2" disabled={intercompanyBusy} onClick={createIntercompanyRule}>{intercompanyBusy ? 'Kaydediliyor...' : 'Eliminasyon Kuralı Ekle'}</Button>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
          <Card className="mt-5">
            <CardHeader><CardTitle>e-Defter Hazırlık ve Kaynak Paketi</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                Bu alan XBRL-GL e-Defter veya berat üretmez; mali mühür/e-imza ve GİB gönderimi yapmaz. Kapalı dönemin doğrulanmış kaynak verisini, SHA-256 bütünlük manifestiyle uyumlu yazılıma aktarır.
              </div>
              <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
                <Input value={eledgerSettings.taxpayer_id || ''} onChange={(e) => setEledgerSettings({ ...eledgerSettings, taxpayer_id: e.target.value })} placeholder="VKN / TCKN" maxLength={11} />
                <Input value={eledgerSettings.legal_name || ''} onChange={(e) => setEledgerSettings({ ...eledgerSettings, legal_name: e.target.value })} placeholder="Yasal unvan" />
                <Input value={eledgerSettings.source_application || ''} onChange={(e) => setEledgerSettings({ ...eledgerSettings, source_application: e.target.value })} placeholder="Kaynak uygulama" />
                <Input value={eledgerSettings.source_application_version || ''} onChange={(e) => setEledgerSettings({ ...eledgerSettings, source_application_version: e.target.value })} placeholder="Uygulama sürümü" />
                <Input value={eledgerSettings.software_approval_reference || ''} onChange={(e) => setEledgerSettings({ ...eledgerSettings, software_approval_reference: e.target.value })} placeholder="GİB uyumluluk onayı referansı (varsa)" />
                <Button variant="outline" disabled={eledgerBusy === 'settings'} onClick={saveEledgerSettings}>{eledgerBusy === 'settings' ? 'Kaydediliyor...' : 'Hazırlık Bilgilerini Kaydet'}</Button>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <Input type="month" className="w-44" value={eledgerPeriod} onChange={(e) => setEledgerPeriod(e.target.value)} />
                <Button variant="outline" disabled={eledgerBusy === 'preflight'} onClick={refreshEledgerPreflight}>{eledgerBusy === 'preflight' ? 'Kontrol ediliyor...' : 'Ön Kontrolü Çalıştır'}</Button>
                <Button disabled={!eledgerPreflight?.ready_for_source_export || eledgerBusy === 'download'} onClick={downloadEledgerSourcePackage}>{eledgerBusy === 'download' ? 'Hazırlanıyor...' : 'Kaynak ZIP İndir'}</Button>
                <span className={`text-sm font-semibold ${eledgerPreflight?.ready_for_source_export ? 'text-emerald-700' : 'text-amber-700'}`}>
                  {eledgerPreflight?.ready_for_source_export ? 'Kaynak aktarımına hazır' : 'Hazır değil'}
                </span>
              </div>
              {eledgerPreflight && (
                <div className="grid md:grid-cols-2 gap-3 text-xs">
                  <div className="rounded border p-3">
                    <p className="font-semibold mb-2">Kontrol sonucu · {eledgerPreflight.entry_count || 0} fiş / {eledgerPreflight.line_count || 0} satır</p>
                    {(eledgerPreflight.blockers || []).length === 0 ? <p className="text-emerald-700">Muhasebe bütünlüğü engeli yok.</p> : (eledgerPreflight.blockers || []).map((item) => <p key={item.code} className="text-red-700">• {item.message}</p>)}
                    {(eledgerPreflight.warnings || []).map((item) => <p key={item.code} className="text-amber-700">• {item.message}</p>)}
                  </div>
                  <div className="rounded border p-3">
                    <p className="font-semibold mb-2">Resmi e-Defter için dış gereksinimler</p>
                    {(eledgerPreflight.external_requirements || []).map((item) => <p key={item}>• {item}</p>)}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="workspace">
          <div className="grid md:grid-cols-2 lg:grid-cols-5 gap-4">
            <Card><CardContent className="pt-6"><Landmark className="w-7 h-7 text-amber-600 mb-3" /><p className="text-sm text-slate-500">Tedarikçi Borçları</p><p className="text-2xl font-bold">{fmtMoney(workspace.aging?.total_outstanding || 0)}</p><p className="text-xs text-slate-500 mt-2">90+ gün: {fmtMoney(workspace.aging?.buckets?.d90_plus || 0)}</p></CardContent></Card>
            <Card><CardContent className="pt-6"><TrendingUp className="w-7 h-7 text-red-600 mb-3" /><p className="text-sm text-slate-500">Gider Bütçesi · Bu Ay</p><p className="text-2xl font-bold">{fmtMoney(workspace.expenseBudget?.totals?.actual || 0)}</p><p className="text-xs text-slate-500 mt-2">Bütçe: {fmtMoney(workspace.expenseBudget?.totals?.budget || 0)}</p></CardContent></Card>
            <Card><CardContent className="pt-6"><TrendingUp className="w-7 h-7 text-emerald-600 mb-3" /><p className="text-sm text-slate-500">Gelir Bütçesi · Bu Ay</p><p className="text-2xl font-bold">{fmtMoney(workspace.revenueBudget?.totals?.actual || 0)}</p><p className="text-xs text-slate-500 mt-2">Bütçe: {fmtMoney(workspace.revenueBudget?.totals?.budget || 0)}</p></CardContent></Card>
            <Card><CardContent className="pt-6"><PackageOpen className="w-7 h-7 text-indigo-600 mb-3" /><p className="text-sm text-slate-500">Sabit Kıymetler</p><p className="text-2xl font-bold">{workspace.assets.length}</p><p className="text-xs text-slate-500 mt-2">Net defter değeri: {fmtMoney(workspace.assets.reduce((sum, item) => sum + (Number(item.book_value) || 0), 0))}</p></CardContent></Card>
            <Card><CardContent className="pt-6"><Landmark className={`w-7 h-7 mb-3 ${operationalBridge?.healthy ? 'text-emerald-600' : 'text-amber-600'}`} /><p className="text-sm text-slate-500">PMS/POS Muhasebe Köprüsü</p><p className="text-lg font-bold">{operationalBridge?.healthy ? 'Sağlıklı' : operationalBridge?.configured ? 'İnceleme Gerekli' : 'Kapalı'}</p><p className="text-xs text-slate-500 mt-2">Gece: {operationalBridge?.failed?.night_audit || 0} · POS: {operationalBridge?.failed?.pos || 0} hata</p>{!operationalBridge?.configured && <Button size="sm" className="w-full mt-3" onClick={enableOperationalBridge} disabled={operationalBusy}>{operationalBusy ? 'Açılıyor...' : 'Standart Eşlemeyle Aç'}</Button>}</CardContent></Card>
          </div>
          <p className="text-xs text-slate-500 mt-4">Bu özetler AP, bütçe ve sabit kıymet alt defterlerindeki gerçek tenant verisinden okunur; örnek/sabit rakam kullanılmaz.</p>
        </TabsContent>

        <TabsContent value="integrations" className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><Cable className="w-5 h-5 text-blue-600" /> Nilvera → Genel Muhasebe</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              {missingIntegrationAccountCodes.length > 0 && (
                <div className="flex flex-col gap-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950 sm:flex-row sm:items-center sm:justify-between" role="alert">
                  <div className="flex items-start gap-2">
                    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                    <p>
                      Eşlemelerde kullanılan şu hesaplar aktif hesap planında yok: <strong>{missingIntegrationAccountCodes.join(', ')}</strong>.
                      Otomatik muhasebeleştirmeyi açmadan önce standart planı tamamlayın; özel alt hesapları ayrıca oluşturun.
                    </p>
                  </div>
                  <Button variant="outline" size="sm" className="shrink-0" onClick={initializeAccounts} disabled={initializingAccounts}>
                    {initializingAccounts ? 'Tamamlanıyor...' : 'Standart Planı Tamamla'}
                  </Button>
                </div>
              )}
              <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
                İnceleme modunda belgeler fiş oluşturulmadan kuyruğa alınır. Otomatik mod yalnızca yerel muhasebe fişi üretir; Nilvera’ya veya GİB’e yazma işlemi yapmaz.
              </div>
              <div className="grid lg:grid-cols-2 gap-5">
                <div className="rounded-lg border p-4 space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="font-semibold">Alış Faturaları</h3>
                    <select
                      aria-label="Nilvera alış muhasebe modu"
                      className="rounded-md border px-3 py-2 text-sm"
                      value={nilveraGL.settings.incoming_mode}
                      onChange={(event) => setNilveraGL((current) => ({ ...current, settings: { ...current.settings, incoming_mode: event.target.value } }))}
                    >
                      <option value="disabled">Kapalı</option>
                      <option value="review">İnceleme Kuyruğu</option>
                      <option value="automatic">Otomatik</option>
                    </select>
                  </div>
                  <div className="grid sm:grid-cols-3 gap-2">
                    <Input value={nilveraGL.settings.incoming_purchase_account_code} onChange={(event) => setNilveraGL((current) => ({ ...current, settings: { ...current.settings, incoming_purchase_account_code: event.target.value } }))} placeholder="Gider/Stok (153)" />
                    <Input value={nilveraGL.settings.incoming_vat_account_code} onChange={(event) => setNilveraGL((current) => ({ ...current, settings: { ...current.settings, incoming_vat_account_code: event.target.value } }))} placeholder="İndirilecek KDV (191)" />
                    <Input value={nilveraGL.settings.incoming_payable_account_code} onChange={(event) => setNilveraGL((current) => ({ ...current, settings: { ...current.settings, incoming_payable_account_code: event.target.value } }))} placeholder="Satıcılar (320)" />
                    <Input value={nilveraGL.settings.incoming_other_tax_account_code || ''} onChange={(event) => setNilveraGL((current) => ({ ...current, settings: { ...current.settings, incoming_other_tax_account_code: event.target.value } }))} placeholder="Diğer Vergi (opsiyonel)" />
                    <Input value={nilveraGL.settings.incoming_deduction_account_code || ''} onChange={(event) => setNilveraGL((current) => ({ ...current, settings: { ...current.settings, incoming_deduction_account_code: event.target.value } }))} placeholder="Tevkifat/Kesinti (360)" />
                  </div>
                  <div className="grid gap-3 border-t pt-3 sm:grid-cols-2">
                    <label className="space-y-1 text-xs text-slate-600">
                      <span>Vergi koduna göre hesap</span>
                      <Input
                        aria-label="Nilvera alış diğer vergi kodu hesap eşlemeleri"
                        value={nilveraMappingText.incoming_other_tax_accounts_by_code}
                        onChange={(event) => setNilveraMappingText((current) => ({ ...current, incoming_other_tax_accounts_by_code: event.target.value }))}
                        placeholder="0015=360.15, 0073=360.73"
                      />
                    </label>
                    <label className="space-y-1 text-xs text-slate-600">
                      <span>Tevkifat/kesinti koduna göre hesap</span>
                      <Input
                        aria-label="Nilvera alış tevkifat kodu hesap eşlemeleri"
                        value={nilveraMappingText.incoming_deduction_accounts_by_code}
                        onChange={(event) => setNilveraMappingText((current) => ({ ...current, incoming_deduction_accounts_by_code: event.target.value }))}
                        placeholder="601=360.601, 603=360.603"
                      />
                    </label>
                  </div>
                </div>
                <div className="rounded-lg border p-4 space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="font-semibold">Satış Faturaları</h3>
                    <select
                      aria-label="Nilvera satış muhasebe modu"
                      className="rounded-md border px-3 py-2 text-sm"
                      value={nilveraGL.settings.outgoing_mode}
                      onChange={(event) => setNilveraGL((current) => ({ ...current, settings: { ...current.settings, outgoing_mode: event.target.value } }))}
                    >
                      <option value="disabled">Kapalı</option>
                      <option value="review">İnceleme Kuyruğu</option>
                      <option value="automatic">Otomatik</option>
                    </select>
                  </div>
                  <div className="grid sm:grid-cols-3 gap-2">
                    <Input value={nilveraGL.settings.outgoing_revenue_account_code || ''} onChange={(event) => setNilveraGL((current) => ({ ...current, settings: { ...current.settings, outgoing_revenue_account_code: event.target.value } }))} placeholder="Gelir (600)" />
                    <Input value={nilveraGL.settings.outgoing_receivable_account_code || ''} onChange={(event) => setNilveraGL((current) => ({ ...current, settings: { ...current.settings, outgoing_receivable_account_code: event.target.value } }))} placeholder="Alıcılar (120)" />
                    <Input value={nilveraGL.settings.outgoing_discount_account_code || ''} onChange={(event) => setNilveraGL((current) => ({ ...current, settings: { ...current.settings, outgoing_discount_account_code: event.target.value } }))} placeholder="İskonto (611)" />
                    <Input value={nilveraGL.settings.outgoing_vat_account_code || ''} onChange={(event) => setNilveraGL((current) => ({ ...current, settings: { ...current.settings, outgoing_vat_account_code: event.target.value } }))} placeholder="Hesaplanan KDV (391)" />
                    <Input value={nilveraGL.settings.outgoing_accommodation_tax_account_code || ''} onChange={(event) => setNilveraGL((current) => ({ ...current, settings: { ...current.settings, outgoing_accommodation_tax_account_code: event.target.value } }))} placeholder="Konaklama Vergisi (360)" />
                  </div>
                  <div className="grid gap-3 border-t pt-3 sm:grid-cols-2">
                    <label className="space-y-1 text-xs text-slate-600">
                      <span>KDV oranına göre hesap</span>
                      <Input
                        aria-label="Nilvera satış KDV oranı hesap eşlemeleri"
                        value={nilveraMappingText.outgoing_vat_accounts_by_rate}
                        onChange={(event) => setNilveraMappingText((current) => ({ ...current, outgoing_vat_accounts_by_rate: event.target.value }))}
                        placeholder="10=391.10, 20=391.20"
                      />
                    </label>
                    <label className="space-y-1 text-xs text-slate-600">
                      <span>Konaklama vergisi oranına göre hesap</span>
                      <Input
                        aria-label="Nilvera konaklama vergisi oranı hesap eşlemeleri"
                        value={nilveraMappingText.outgoing_accommodation_tax_accounts_by_rate}
                        onChange={(event) => setNilveraMappingText((current) => ({ ...current, outgoing_accommodation_tax_accounts_by_rate: event.target.value }))}
                        placeholder="2=360.02"
                      />
                    </label>
                  </div>
                </div>
              </div>
              <Button onClick={saveNilveraGL} disabled={integrationBusy === 'nilvera-settings'}>
                <Save className="w-4 h-4 mr-2" /> {integrationBusy === 'nilvera-settings' ? 'Kaydediliyor...' : 'Nilvera Muhasebe Eşlemesini Kaydet'}
              </Button>

              <div className="border-t pt-4">
                <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                  <h3 className="font-semibold">Muhasebe İnceleme Kuyruğu</h3>
                  <p className="text-xs text-slate-500">Bekleyen: {nilveraGL.counts.pending || 0} · Engelli: {nilveraGL.counts.blocked || 0} · İşlenen: {nilveraGL.counts.posted || 0}</p>
                </div>
                <div className="space-y-2">
                  {nilveraGL.queue.slice(0, 20).map((item) => (
                    <div key={item.id} className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-lg border p-3 text-sm">
                      <div>
                        <p className="font-medium">{item.direction === 'incoming' ? 'Alış' : 'Satış'} · {item.invoice_id}</p>
                        <p className={`text-xs ${item.status === 'blocked' ? 'text-red-700' : item.status === 'posted' || item.status === 'reversed' ? 'text-emerald-700' : 'text-amber-700'}`}>
                          {item.status}{item.error_detail ? ` · ${item.error_detail}` : ''}
                        </p>
                      </div>
                      {item.operation === 'post' && ['pending', 'blocked'].includes(item.status) && (
                        <Button size="sm" variant="outline" disabled={integrationBusy === `nilvera:${item.id}`} onClick={() => processNilveraQueueItem(item.id)}>
                          {integrationBusy === `nilvera:${item.id}` ? 'İşleniyor...' : 'Kontrol Et ve Muhasebeleştir'}
                        </Button>
                      )}
                    </div>
                  ))}
                  {nilveraGL.queue.length === 0 && <p className="rounded-lg bg-slate-50 p-4 text-sm text-slate-500">İncelenecek Nilvera belgesi bulunmuyor.</p>}
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="grid lg:grid-cols-2 gap-5">
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2"><ReceiptText className="w-5 h-5 text-amber-600" /> Tedarikçi Alt Defteri → GL</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <select aria-label="AP GL durumu" className="w-full rounded-md border px-3 py-2 text-sm" value={apGLMapping.enabled ? 'enabled' : 'disabled'} onChange={(event) => setApGLMapping({ ...apGLMapping, enabled: event.target.value === 'enabled' })}>
                  <option value="disabled">Otomatik Muhasebe Kapalı</option><option value="enabled">Otomatik Muhasebe Açık</option>
                </select>
                <div className="grid sm:grid-cols-2 gap-2">
                  <Input value={apGLMapping.expense_account_code} onChange={(event) => setApGLMapping({ ...apGLMapping, expense_account_code: event.target.value })} placeholder="Gider (770)" />
                  <Input value={apGLMapping.input_vat_account_code} onChange={(event) => setApGLMapping({ ...apGLMapping, input_vat_account_code: event.target.value })} placeholder="İndirilecek KDV (191)" />
                  <Input value={apGLMapping.payable_account_code} onChange={(event) => setApGLMapping({ ...apGLMapping, payable_account_code: event.target.value })} placeholder="Satıcılar (320)" />
                  <Input value={apGLMapping.bank_account_code} onChange={(event) => setApGLMapping({ ...apGLMapping, bank_account_code: event.target.value })} placeholder="Banka (102)" />
                  <Input value={apGLMapping.cash_account_code} onChange={(event) => setApGLMapping({ ...apGLMapping, cash_account_code: event.target.value })} placeholder="Kasa (100)" />
                </div>
                <Button variant="outline" onClick={saveAPGLMapping} disabled={integrationBusy === 'ap'}>{integrationBusy === 'ap' ? 'Kaydediliyor...' : 'AP Eşlemesini Kaydet'}</Button>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2"><PackageOpen className="w-5 h-5 text-indigo-600" /> Amortisman → GL</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <select aria-label="Amortisman GL durumu" className="w-full rounded-md border px-3 py-2 text-sm" value={fixedAssetGLMapping.enabled ? 'enabled' : 'disabled'} onChange={(event) => setFixedAssetGLMapping({ ...fixedAssetGLMapping, enabled: event.target.value === 'enabled' })}>
                  <option value="disabled">Otomatik Muhasebe Kapalı</option><option value="enabled">Otomatik Muhasebe Açık</option>
                </select>
                <div className="grid sm:grid-cols-2 gap-2">
                  <Input value={fixedAssetGLMapping.depreciation_expense_account_code} onChange={(event) => setFixedAssetGLMapping({ ...fixedAssetGLMapping, depreciation_expense_account_code: event.target.value })} placeholder="Amortisman Gideri (770)" />
                  <Input value={fixedAssetGLMapping.accumulated_depreciation_account_code} onChange={(event) => setFixedAssetGLMapping({ ...fixedAssetGLMapping, accumulated_depreciation_account_code: event.target.value })} placeholder="Birikmiş Amortisman (257)" />
                </div>
                <Button variant="outline" onClick={saveFixedAssetGLMapping} disabled={integrationBusy === 'fixed-assets'}>{integrationBusy === 'fixed-assets' ? 'Kaydediliyor...' : 'Amortisman Eşlemesini Kaydet'}</Button>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
          </main>
        </div>
      </Tabs>

      <Dialog
        open={Boolean(periodActionDialog)}
        onOpenChange={(open) => {
          if (!open && !periodBusy) {
            setPeriodActionDialog(null);
            setPeriodActionReason('');
          }
        }}
      >
        <DialogContent className="sm:max-w-md" data-testid="gl-period-action-dialog">
          <DialogHeader>
            <DialogTitle>
              {periodActionDialog?.action === 'year-end'
                ? `${periodYear} Mali Yılını Kapat`
                : periodActionDialog?.action === 'reopen'
                  ? `${periodActionDialog?.period?.name || 'Dönem'} Dönemini Yeniden Aç`
                  : `${periodActionDialog?.period?.name || 'Dönem'} Dönemini Kapat`}
            </DialogTitle>
            <DialogDescription>
              {periodActionDialog?.action === 'year-end'
                ? `Gelir ve gider hesapları kapatılacak, ${periodYear + 1} açılış bakiyeleri oluşturulacak.`
                : periodActionDialog?.action === 'reopen'
                  ? 'Bu dönem yeniden fiş ve entegrasyon kaydı kabul edecektir.'
                  : 'Kapalı döneme yeni fiş veya entegrasyon kaydı gönderilemez.'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="gl-period-action-reason">Gerekçe</label>
            <Input
              id="gl-period-action-reason"
              autoFocus
              value={periodActionReason}
              onChange={(event) => setPeriodActionReason(event.target.value)}
              placeholder="En az 3 karakter"
              disabled={Boolean(periodBusy)}
            />
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setPeriodActionDialog(null)} disabled={Boolean(periodBusy)}>Vazgeç</Button>
            <Button onClick={confirmPeriodAction} disabled={Boolean(periodBusy) || periodActionReason.trim().length < 3}>
              {periodBusy ? 'İşleniyor...' : periodActionDialog?.action === 'reopen' ? 'Yeniden Aç' : 'Kapat ve Onayla'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={Boolean(voucherActionDialog)}
        onOpenChange={(open) => {
          if (!open && !voucherBusy) {
            setVoucherActionDialog(null);
            setVoucherActionReason('');
          }
        }}
      >
        <DialogContent className="sm:max-w-md" data-testid="gl-voucher-action-dialog">
          <DialogHeader>
            <DialogTitle>Fiş İşlemini Onayla</DialogTitle>
            <DialogDescription>
              {voucherActionDialog?.voucher?.voucher_no} için {voucherActionDialog?.action === 'submit' ? 'incelemeye gönderme' : voucherActionDialog?.action === 'approve' ? 'onaylama' : voucherActionDialog?.action === 'reject' ? 'reddetme' : 'iptal'} gerekçesini yazın.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="gl-voucher-action-reason">Gerekçe</label>
            <Input id="gl-voucher-action-reason" autoFocus value={voucherActionReason} onChange={(event) => setVoucherActionReason(event.target.value)} placeholder="En az 3 karakter" disabled={Boolean(voucherBusy)} />
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setVoucherActionDialog(null)} disabled={Boolean(voucherBusy)}>Vazgeç</Button>
            <Button onClick={confirmVoucherAction} disabled={Boolean(voucherBusy) || voucherActionReason.trim().length < 3}>{voucherBusy ? 'İşleniyor...' : 'Onayla'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={Boolean(reversalDialog)}
        onOpenChange={(open) => {
          if (!open && !reversalBusy) {
            setReversalDialog(null);
            setReversalReason('');
          }
        }}
      >
        <DialogContent className="sm:max-w-md" data-testid="gl-reversal-dialog">
          <DialogHeader>
            <DialogTitle>Ters Kayıt Oluştur</DialogTitle>
            <DialogDescription>{reversalDialog?.journal?.entry_no || 'Yevmiye kaydı'} için bağlı ters kayıt oluşturulur.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="gl-reversal-reason">Gerekçe</label>
              <Input id="gl-reversal-reason" autoFocus value={reversalReason} onChange={(event) => setReversalReason(event.target.value)} placeholder="En az 3 karakter" disabled={Boolean(reversalBusy)} />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="gl-reversal-date">Ters kayıt tarihi</label>
              <Input id="gl-reversal-date" type="date" value={reversalDate} onChange={(event) => setReversalDate(event.target.value)} disabled={Boolean(reversalBusy)} />
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setReversalDialog(null)} disabled={Boolean(reversalBusy)}>Vazgeç</Button>
            <Button onClick={confirmJournalReversal} disabled={Boolean(reversalBusy) || reversalReason.trim().length < 3}>{reversalBusy ? 'Oluşturuluyor...' : 'Ters Kayıt Oluştur'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default GeneralLedgerModule;
