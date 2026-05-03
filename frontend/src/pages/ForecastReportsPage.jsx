import { useEffect, useState } from "react";
import api from "@/api/axios";

export default function ForecastReportsPage() {
  const [tab, setTab] = useState("forecast");
  const [days, setDays] = useState(30);
  const [segment, setSegment] = useState("");
  const [forecast, setForecast] = useState(null);
  const [pickup, setPickup] = useState(null);
  const [pickupDays, setPickupDays] = useState(7);
  const [pace, setPace] = useState(null);
  const [paceDate, setPaceDate] = useState(new Date().toISOString().slice(0, 10));
  const [paceCompare, setPaceCompare] = useState(new Date().getFullYear() - 1);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  const loadForecast = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/api/analytics/forecast", {
        params: { days, segment: segment || undefined },
      });
      setForecast(data);
      setErr("");
    } catch (e) {
      setErr(e?.response?.data?.detail || "Forecast yüklenemedi");
    } finally { setLoading(false); }
  };

  const loadPickup = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/api/analytics/pickup-report", {
        params: { period_days: pickupDays },
      });
      setPickup(data);
      setErr("");
    } catch (e) {
      setErr(e?.response?.data?.detail || "Pickup yüklenemedi");
    } finally { setLoading(false); }
  };

  const loadPace = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/api/analytics/pace", {
        params: { target_date: paceDate, compare_year: paceCompare || undefined },
      });
      setPace(data);
      setErr("");
    } catch (e) {
      setErr(e?.response?.data?.detail || "Pace yüklenemedi");
    } finally { setLoading(false); }
  };

  useEffect(() => {
    if (tab === "forecast") loadForecast();
    if (tab === "pickup") loadPickup();
    if (tab === "pace") loadPace();
  }, [tab]);

  return (
    <div style={{ padding: 24, maxWidth: 1300, margin: "0 auto" }}>
      <h2>Forecast / Pace / Pickup Raporları</h2>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {["forecast","pace","pickup"].map(t => (
          <button key={t} onClick={() => setTab(t)} style={{ fontWeight: tab === t ? 700 : 400 }}>
            {t === "forecast" ? "Forecast" : t === "pace" ? "Pace" : "Pickup"}
          </button>
        ))}
      </div>
      {err && <div style={{ color: "crimson" }}>{err}</div>}

      {tab === "forecast" && (
        <div>
          <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
            <select value={days} onChange={e => setDays(Number(e.target.value))}>
              <option value={10}>10 gün</option>
              <option value={30}>30 gün</option>
              <option value={90}>90 gün</option>
              <option value={180}>180 gün</option>
            </select>
            <input placeholder="Segment (opsiyonel: corporate, leisure…)" value={segment} onChange={e => setSegment(e.target.value)} />
            <button onClick={loadForecast} disabled={loading}>Yenile</button>
          </div>
          {forecast && (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead><tr style={{ background: "#eee" }}>
                <th style={{ padding: 6 }}>Tarih</th>
                <th style={{ padding: 6 }}>OTB Oda</th>
                <th style={{ padding: 6 }}>Forecast Oda</th>
                <th style={{ padding: 6 }}>Doluluk %</th>
                <th style={{ padding: 6 }}>ADR</th>
                <th style={{ padding: 6 }}>RevPAR</th>
                <th style={{ padding: 6 }}>OTB Gelir</th>
                <th style={{ padding: 6 }}>Forecast Gelir</th>
              </tr></thead>
              <tbody>{(forecast.daily || []).map(d => (
                <tr key={d.date} style={{ borderBottom: "1px solid #eee" }}>
                  <td style={{ padding: 6 }}>{d.date}</td>
                  <td style={{ padding: 6, textAlign: "right" }}>{d.rooms_otb}</td>
                  <td style={{ padding: 6, textAlign: "right" }}>{d.rooms_forecast}</td>
                  <td style={{ padding: 6, textAlign: "right" }}>{d.occupancy_pct}%</td>
                  <td style={{ padding: 6, textAlign: "right" }}>{d.adr}</td>
                  <td style={{ padding: 6, textAlign: "right" }}>{d.revpar}</td>
                  <td style={{ padding: 6, textAlign: "right" }}>{d.revenue_otb}</td>
                  <td style={{ padding: 6, textAlign: "right" }}>{d.revenue_forecast}</td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </div>
      )}

      {tab === "pace" && (
        <div>
          <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
            <input type="date" value={paceDate} onChange={e => setPaceDate(e.target.value)} />
            <input type="number" placeholder="Karşılaştırma yılı" value={paceCompare} onChange={e => setPaceCompare(e.target.value)} />
            <button onClick={loadPace} disabled={loading}>Yenile</button>
          </div>
          {pace && (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead><tr style={{ background: "#eee" }}>
                <th style={{ padding: 8 }}>Gün Önce</th>
                <th style={{ padding: 8 }}>Bu Yıl Oda</th>
                <th style={{ padding: 8 }}>Karşılaştırma</th>
              </tr></thead>
              <tbody>{(pace.current || []).map(p => {
                const cmp = (pace.compare || []).find(c => c.days_out === p.days_out);
                return (
                  <tr key={p.days_out} style={{ borderBottom: "1px solid #eee" }}>
                    <td style={{ padding: 8, textAlign: "center" }}>-{p.days_out}</td>
                    <td style={{ padding: 8, textAlign: "right" }}>{p.rooms_on_books}</td>
                    <td style={{ padding: 8, textAlign: "right", color: "#666" }}>{cmp?.rooms_on_books ?? "-"}</td>
                  </tr>
                );
              })}</tbody>
            </table>
          )}
        </div>
      )}

      {tab === "pickup" && (
        <div>
          <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
            <select value={pickupDays} onChange={e => setPickupDays(Number(e.target.value))}>
              <option value={1}>Son 1 gün</option>
              <option value={7}>Son 7 gün</option>
              <option value={14}>Son 14 gün</option>
              <option value={30}>Son 30 gün</option>
            </select>
            <button onClick={loadPickup} disabled={loading}>Yenile</button>
          </div>
          {pickup && (
            <>
              <div style={{ marginBottom: 12 }}>
                Toplam: <b>{pickup.total_rooms_picked}</b> oda · <b>{pickup.total_revenue_picked}</b> ₺
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead><tr style={{ background: "#eee" }}>
                  <th style={{ padding: 8 }}>Check-in Tarihi</th>
                  <th style={{ padding: 8 }}>Oda</th>
                  <th style={{ padding: 8 }}>Gelir</th>
                </tr></thead>
                <tbody>{(pickup.daily || []).map(d => (
                  <tr key={d.check_in} style={{ borderBottom: "1px solid #eee" }}>
                    <td style={{ padding: 8 }}>{d.check_in}</td>
                    <td style={{ padding: 8, textAlign: "right" }}>{d.rooms}</td>
                    <td style={{ padding: 8, textAlign: "right" }}>{d.revenue}</td>
                  </tr>
                ))}</tbody>
              </table>
            </>
          )}
        </div>
      )}
    </div>
  );
}
