import {
  InvoiceModule, GeneralLedgerModule, BankReconciliationModule, NightAuditDashboard, NightAuditLogs, PendingAR,
  CityLedgerAccounts, EFaturaModule, Settings, BasicReports, ReportBuilder,
  OfficialGuestList, CorporateContractsDashboard, CorporateContractApprovals,
} from "./lazyPages";

export function financeReportsRoutes({ p }) {
  return [
    // ── Finance ────────────────────────────────────────
    { path: "/invoices", ...p(InvoiceModule), wrapLayout: true, layoutModule: "invoices" },
    { path: "/app/invoices", ...p(InvoiceModule), wrapLayout: true, layoutModule: "invoices" },
    { path: "/app/general-ledger", ...p(GeneralLedgerModule), wrapLayout: true, layoutModule: "invoices" },
    { path: "/app/bank-reconciliation", ...p(BankReconciliationModule), wrapLayout: true, layoutModule: "invoices" },
    { path: "/night-audit", ...p(NightAuditDashboard), wrapLayout: true, layoutModule: "night_audit" },
    { path: "/night-audit/logs", ...p(NightAuditLogs), wrapLayout: true, layoutModule: "reports" },
    { path: "/pending-ar", ...p(PendingAR), wrapLayout: true, layoutModule: "pending-ar" },
    { path: "/city-ledger", ...p(CityLedgerAccounts), wrapLayout: true, layoutModule: "city-ledger" },
    { path: "/efatura", ...p(EFaturaModule) },

    // ── Settings ───────────────────────────────────────
    { path: "/settings", ...p(Settings), wrapLayout: true, layoutModule: "settings" },
    { path: "/app/settings", ...p(Settings), wrapLayout: true, layoutModule: "settings" },

    // ── Reports ────────────────────────────────────────
    { path: "/app/raporlar", ...p(BasicReports), wrapLayout: true, layoutModule: "reports_basic" },
    { path: "/app/gelismis-raporlar", ...p(BasicReports), wrapLayout: true, layoutModule: "reports_basic" },
    { path: "/reports", ...p(BasicReports), wrapLayout: true, layoutModule: "reports_basic" },
    { path: "/app/reports", ...p(BasicReports), wrapLayout: true, layoutModule: "reports_basic" },
    { path: "/reports/builder", ...p(ReportBuilder), wrapLayout: true, layoutModule: "reports" },
    { path: "/app/rapor-olusturucu", ...p(ReportBuilder), wrapLayout: true, layoutModule: "reports" },
    { path: "/reports/official-guest-list", ...p(OfficialGuestList), wrapLayout: true, layoutModule: "reports" },
    { path: "/reports/corporate-contracts", ...p(CorporateContractsDashboard), wrapLayout: true, layoutModule: "reports" },
    { path: "/reports/corporate-contract-approvals", ...p(CorporateContractApprovals), wrapLayout: true, layoutModule: "reports" },
  ];
}
