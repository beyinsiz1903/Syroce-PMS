import React from 'react';
import { Badge } from '@/components/ui/badge';
import {
  CheckCircle2, AlertTriangle, Loader2, XCircle, Clock,
} from 'lucide-react';

export const statusConfig = {
  completed: { label: "Tamamlandı", color: "bg-emerald-100 text-emerald-700 border-emerald-200", icon: CheckCircle2 },
  completed_with_exceptions: { label: "İstisnalı Tamamlandı", color: "bg-amber-100 text-amber-700 border-amber-200", icon: AlertTriangle },
  running: { label: "Çalışıyor", color: "bg-blue-100 text-blue-700 border-blue-200", icon: Loader2 },
  failed: { label: "Başarısız", color: "bg-red-100 text-red-700 border-red-200", icon: XCircle },
  pending: { label: "Bekliyor", color: "bg-gray-100 text-gray-600 border-gray-200", icon: Clock },
};

export const severityConfig = {
  info: { label: "Bilgi", color: "bg-blue-50 text-blue-700 border-blue-200" },
  warning: { label: "Uyarı", color: "bg-amber-50 text-amber-700 border-amber-200" },
  error: { label: "Hata", color: "bg-red-50 text-red-700 border-red-200" },
  critical: { label: "Kritik", color: "bg-red-100 text-red-800 border-red-300" },
};

export const StatusBadge = ({ status }) => {
  const cfg = statusConfig[status] || statusConfig.pending;
  const Icon = cfg.icon;
  return (
    <Badge data-testid={`status-badge-${status}`} className={`${cfg.color} border gap-1 font-medium`}>
      <Icon className={`w-3 h-3 ${status === "running" ? "animate-spin" : ""}`} />
      {cfg.label}
    </Badge>
  );
};

export const SeverityBadge = ({ severity }) => {
  const cfg = severityConfig[severity] || severityConfig.info;
  return (
    <Badge className={`${cfg.color} border text-[11px]`}>{cfg.label}</Badge>
  );
};

export const StatCard = ({ icon: Icon, label, value, subValue, color = "text-gray-600" }) => (
  <div className="bg-white border rounded-xl p-4 flex items-start gap-3">
    <div className={`rounded-lg p-2 ${color.replace("text-", "bg-").replace("-600", "-100")}`}>
      <Icon className={`w-5 h-5 ${color}`} />
    </div>
    <div className="min-w-0">
      <p className="text-2xl font-bold text-gray-900 leading-tight">{value}</p>
      <p className="text-xs text-gray-500 mt-0.5">{label}</p>
      {subValue && <p className="text-[11px] text-gray-400 mt-0.5">{subValue}</p>}
    </div>
  </div>
);

export const IntegrityBadge = ({ status }) => {
  const cfg = {
    pass: { label: "Geçti", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
    warning: { label: "Uyarı", cls: "bg-amber-50 text-amber-700 border-amber-200" },
    error: { label: "Hata", cls: "bg-red-50 text-red-700 border-red-200" },
    fail: { label: "Başarısız", cls: "bg-red-50 text-red-700 border-red-200" },
  }[status] || { label: status, cls: "bg-gray-50 text-gray-600 border-gray-200" };
  return <Badge className={`${cfg.cls} border text-[11px]`}>{cfg.label}</Badge>;
};

export const categoryLabels = {
  room: "Oda",
  no_show_fee: "No-Show",
  room_service: "Oda Servisi",
  minibar: "Minibar",
  restaurant: "Restoran",
  spa: "Spa",
  laundry: "Çamaşır",
  parking: "Park",
  other: "Diğer",
};

export const paymentMethodLabels = {
  cash: "Nakit",
  credit_card: "Kredi Kartı",
  debit_card: "Banka Kartı",
  bank_transfer: "Havale/EFT",
  city_ledger: "Cari Hesap",
  agency: "Acente",
  other: "Diğer",
};
