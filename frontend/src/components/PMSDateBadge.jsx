import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Calendar, AlertTriangle } from "lucide-react";
import api from "@/api/axios";
import { prefetchNightAudit } from "@/lib/prefetch";

const MONTHS_TR = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"];

const fmtDate = (iso) => {
  if (!iso) return "—";
  const [y, m, d] = String(iso).split("-").map((s) => parseInt(s, 10));
  if (!y || !m || !d) return iso;
  return `${String(d).padStart(2, "0")} ${MONTHS_TR[m - 1] || ""} ${y}`;
};

const todayISO = () => {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
};

// SessionStorage cache: Layout her sayfa geçişinde remount oluyor; bu cache sayesinde
// PMS tarihi anında görünür, sadece stale (>2dk) ise fetch tetiklenir.
// Cache tenant_id ile scope edilir — hesap değişiminde başka tenant'ın
// business-date'i sızmaz. Auth değişince App.clearAuthStorage cache key'i temizler.
const BD_CACHE_KEY = "pms_bd_cache_v1";
const currentTenantId = () => {
  try {
    const u = JSON.parse(localStorage.getItem("user") || "null");
    const t = JSON.parse(localStorage.getItem("tenant") || "null");
    return u?.tenant_id || t?.id || t?._id || null;
  } catch { return null; }
};
const readBdCache = () => {
  try {
    const raw = sessionStorage.getItem(BD_CACHE_KEY);
    if (!raw) return null;
    const c = JSON.parse(raw);
    if (Date.now() - (c.t || 0) > 2 * 60 * 1000) return null; // 2dk stale
    if (c.tid && c.tid !== currentTenantId()) return null; // tenant mismatch
    return c;
  } catch { return null; }
};

export default function PMSDateBadge() {
  const navigate = useNavigate();
  const cached = readBdCache();
  const [bd, setBd] = useState(cached?.bd || null);
  const [hidden, setHidden] = useState(false);

  const fetchBD = useCallback(async () => {
    try {
      const r = await api.get("/night-audit/business-date");
      const v = r?.data?.business_date || null;
      setBd(v);
      try { sessionStorage.setItem(BD_CACHE_KEY, JSON.stringify({ bd: v, tid: currentTenantId(), t: Date.now() })); } catch {}
    } catch (e) {
      const code = e?.response?.status;
      if (code === 401 || code === 403 || code === 404) {
        setHidden(true);
      }
    }
  }, []);

  useEffect(() => {
    // Cache taze ise mount fetch'i atla — interval 5dk'da bir zaten yenileyecek
    if (!cached) fetchBD();
    const id = setInterval(fetchBD, 5 * 60 * 1000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchBD]);

  const today = todayISO();
  const isStale = bd && bd < today;

  // Stale durumu görünür hale gelir gelmez ağır chunk'ı sessizce indir;
  // kullanıcı butonu okuyup tıklayana kadar bundle hazır olur.
  // Hooks kuralı gereği erken return'den ÖNCE.
  useEffect(() => {
    if (isStale && !hidden) prefetchNightAudit();
  }, [isStale, hidden]);

  const [navigating, setNavigating] = useState(false);
  const handleNavigate = useCallback(() => {
    setNavigating(true);
    navigate("/night-audit");
  }, [navigate]);

  if (hidden) return null;

  const containerClass = isStale
    ? "flex items-center gap-2 pl-3 pr-1 py-1 rounded-full bg-amber-50 text-amber-900 text-xs shadow-sm border border-amber-300"
    : "flex items-center gap-2 px-3 py-1 rounded-full bg-white/90 text-slate-700 text-xs shadow-sm border border-slate-200 backdrop-blur-sm";

  return (
    <div className="fixed bottom-3 left-3 z-40 select-none">
      <div className={containerClass} data-testid="pms-date-badge">
        {isStale ? (
          <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
        ) : (
          <Calendar className="w-3.5 h-3.5 text-slate-500 shrink-0" />
        )}
        <span className="font-medium">PMS:</span>
        <span className="font-semibold tabular-nums">{fmtDate(bd)}</span>
        {isStale && (
          <button
            type="button"
            onClick={handleNavigate}
            onMouseEnter={prefetchNightAudit}
            onFocus={prefetchNightAudit}
            disabled={navigating}
            className="ml-1 px-2.5 py-0.5 rounded-full bg-amber-600 hover:bg-amber-700 disabled:bg-amber-700 disabled:cursor-wait text-white text-[11px] font-medium transition-colors"
            data-testid="pms-date-stale-warning"
            title="Gün sonu işlemini başlat"
          >
            {navigating ? "Açılıyor…" : "Gün Sonu Yap"}
          </button>
        )}
      </div>
    </div>
  );
}
