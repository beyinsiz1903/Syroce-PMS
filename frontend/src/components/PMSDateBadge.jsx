import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Calendar, AlertTriangle } from "lucide-react";
import api from "@/api/axios";

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

export default function PMSDateBadge() {
  const navigate = useNavigate();
  const [bd, setBd] = useState(null);
  const [hidden, setHidden] = useState(false);

  const fetchBD = useCallback(async () => {
    try {
      const r = await api.get("/night-audit/business-date");
      setBd(r?.data?.business_date || null);
    } catch (e) {
      const code = e?.response?.status;
      if (code === 401 || code === 403 || code === 404) {
        setHidden(true);
      }
    }
  }, []);

  useEffect(() => {
    fetchBD();
    const id = setInterval(fetchBD, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, [fetchBD]);

  if (hidden) return null;

  const today = todayISO();
  const isStale = bd && bd < today;

  return (
    <div className="fixed bottom-3 left-3 z-40 flex flex-col gap-1.5 select-none">
      <div
        className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-gray-900/90 text-white text-xs shadow-lg backdrop-blur-sm border border-gray-700"
        data-testid="pms-date-badge"
      >
        <Calendar className="w-3.5 h-3.5 text-gray-300 shrink-0" />
        <span className="font-medium">PMS Tarihi:</span>
        <span className="font-semibold tabular-nums">{fmtDate(bd)}</span>
      </div>
      {isStale && (
        <button
          type="button"
          onClick={() => navigate("/night-audit")}
          className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-amber-500 hover:bg-amber-600 text-white text-xs font-medium shadow-lg transition-colors animate-pulse"
          data-testid="pms-date-stale-warning"
          title="Night Audit sayfasına git"
        >
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          <span>Tarih güncel değil — Gün sonu işlemini yapın</span>
        </button>
      )}
    </div>
  );
}
