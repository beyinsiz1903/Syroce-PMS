/**
 * Syroce Contact Center — Çağrı geçmişi listesi.
 *
 * Tasarım kararları (doktrin):
 *  - GERÇEK VERİ: `/contact-center/calls` ucundan okur (axios baseURL `/api`).
 *    Kayıt yoksa boş-durum gösterilir; sahte/placeholder satır YOK.
 *  - PII: Telefon yalnızca sunucunun döndüğü maskeli haliyle gösterilir; tam numara
 *    talep edilmez (reveal_phone gönderilmez).
 *  - YÖN: Her satır `direction` (inbound/outbound) alanına göre rozet + ikonla
 *    gelen/giden ayrılır. İsteğe bağlı yön filtresi istemci tarafında uygulanır
 *    (uç en çok 200 kayıt döndüğünden ek sorgu maliyeti yok).
 */
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { PhoneIncoming, PhoneOutgoing, RefreshCw } from "lucide-react";

const STATUS_LABEL = {
  ringing: "Çalıyor",
  answered: "Yanıtlandı",
  completed: "Tamamlandı",
  missed: "Cevapsız",
  failed: "Başarısız",
};

const DIRECTION_FILTERS = [
  { key: "all", label: "Tümü" },
  { key: "inbound", label: "Gelen" },
  { key: "outbound", label: "Giden" },
];

function formatDateTime(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("tr-TR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDuration(seconds) {
  const total = Number(seconds) || 0;
  if (total <= 0) return "—";
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function DirectionBadge({ direction }) {
  const isInbound = direction === "inbound";
  const Icon = isInbound ? PhoneIncoming : PhoneOutgoing;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
        isInbound
          ? "bg-emerald-50 text-emerald-700"
          : "bg-indigo-50 text-indigo-700"
      }`}
      title={isInbound ? "Gelen çağrı" : "Giden çağrı"}
    >
      <Icon className="h-3 w-3" aria-hidden="true" />
      {isInbound ? "Gelen" : "Giden"}
    </span>
  );
}

export default function CallHistory() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await axios.get("/contact-center/calls", {
        params: { limit: 50 },
      });
      setItems(Array.isArray(res.data?.items) ? res.data.items : []);
    } catch (err) {
      if (err?.response?.status === 503) {
        setError(
          "Sesli arama altyapısı henüz yapılandırılmadı. Çağrı geçmişi yok.",
        );
      } else if (err?.response?.status === 403) {
        setError("Çağrı geçmişini görüntüleme yetkiniz yok.");
      } else {
        setError("Çağrı geçmişi yüklenemedi. Daha sonra tekrar deneyin.");
      }
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const visible =
    filter === "all" ? items : items.filter((c) => c.direction === filter);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="inline-flex rounded-md border border-gray-200 p-0.5">
          {DIRECTION_FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              className={`rounded px-2 py-1 text-xs font-medium ${
                filter === f.key
                  ? "bg-gray-900 text-white"
                  : "text-gray-600 hover:bg-gray-50"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-1 rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
          aria-label="Yenile"
        >
          <RefreshCw
            className={`h-3 w-3 ${loading ? "animate-spin" : ""}`}
            aria-hidden="true"
          />
          Yenile
        </button>
      </div>

      {error ? (
        <p className="text-xs leading-relaxed text-red-600">{error}</p>
      ) : null}

      {!error && !loading && visible.length === 0 ? (
        <p className="py-6 text-center text-xs text-gray-500">
          {items.length === 0
            ? "Henüz çağrı kaydı yok."
            : "Bu filtreye uyan çağrı yok."}
        </p>
      ) : null}

      {visible.length > 0 ? (
        <ul className="max-h-72 divide-y divide-gray-100 overflow-y-auto">
          {visible.map((call) => (
            <li key={call.id} className="flex items-start gap-2 py-2">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <DirectionBadge direction={call.direction} />
                  <span className="truncate text-sm text-gray-900">
                    {call.caller_phone_masked || "Bilinmeyen numara"}
                  </span>
                </div>
                <div className="mt-0.5 flex items-center gap-2 text-[11px] text-gray-500">
                  <span>{STATUS_LABEL[call.status] || call.status || "—"}</span>
                  <span aria-hidden="true">·</span>
                  <span>{formatDateTime(call.started_at)}</span>
                </div>
              </div>
              <span className="shrink-0 pt-0.5 text-[11px] tabular-nums text-gray-500">
                {formatDuration(call.duration_seconds)}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
