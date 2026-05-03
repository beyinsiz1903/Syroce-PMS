import { useEffect, useState } from "react";
import api from "@/api/axios";

export default function BlockManagementPage() {
  const [blocks, setBlocks] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [pickup, setPickup] = useState(null);
  const [selected, setSelected] = useState(null);
  const [err, setErr] = useState("");

  const load = async () => {
    try {
      const [s, a] = await Promise.all([
        api.get("/api/block-mgmt/summary"),
        api.get("/api/block-mgmt/cutoff-alerts", { params: { days_ahead: 14 } }),
      ]);
      setBlocks(s.data?.blocks || []);
      setAlerts(a.data?.alerts || []);
      setErr("");
    } catch (e) {
      setErr(e?.response?.data?.detail || "Yüklenemedi");
    }
  };
  useEffect(() => { load(); }, []);

  const showPickup = async (id) => {
    setSelected(id);
    const { data } = await api.get(`/api/block-mgmt/${id}/pickup`);
    setPickup(data);
  };

  const wash = async (id) => {
    const n = prompt("Kaç oda bırakılsın (wash)?");
    if (!n || isNaN(n)) return;
    try {
      const { data } = await api.post(`/api/block-mgmt/${id}/wash`, {
        wash_count: Number(n),
      });
      alert(`${data.washed} oda bırakıldı. Yeni toplam: ${data.new_total_rooms}`);
      load();
    } catch (e) {
      alert(e?.response?.data?.detail || "Wash başarısız");
    }
  };

  return (
    <div style={{ padding: 24, maxWidth: 1300, margin: "0 auto" }}>
      <h2>Grup Blok Yönetimi</h2>
      <p style={{ color: "#666" }}>Cutoff uyarıları, oda bırakma (wash), pickup eğrisi.</p>
      {err && <div style={{ color: "crimson" }}>{err}</div>}

      {alerts.length > 0 && (
        <div style={{ marginBottom: 16, padding: 12, background: "#fff8e1", border: "1px solid #f0c040", borderRadius: 8 }}>
          <h3 style={{ margin: "0 0 8px 0" }}>Cutoff Uyarıları (14 gün)</h3>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {alerts.map(a => (
              <li key={a.id}>
                <b>{a.group_name}</b> — {a.days_left} gün kaldı,
                {" "}{a.remaining}/{a.total_rooms} oda hâlâ alınmadı
              </li>
            ))}
          </ul>
        </div>
      )}

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead><tr style={{ background: "#eee" }}>
          <th style={{ padding: 8, textAlign: "left" }}>Grup</th>
          <th style={{ padding: 8 }}>Giriş</th>
          <th style={{ padding: 8 }}>Cutoff</th>
          <th style={{ padding: 8 }}>Toplam</th>
          <th style={{ padding: 8 }}>Pickup</th>
          <th style={{ padding: 8 }}>Wash</th>
          <th style={{ padding: 8 }}>%</th>
          <th style={{ padding: 8 }}></th>
        </tr></thead>
        <tbody>{blocks.map(b => (
          <tr key={b.id} style={{ borderBottom: "1px solid #eee" }}>
            <td style={{ padding: 8 }}>{b.group_name}</td>
            <td style={{ padding: 8, textAlign: "center" }}>{b.check_in?.slice(0, 10)}</td>
            <td style={{ padding: 8, textAlign: "center" }}>{b.cutoff_date?.slice(0, 10)}</td>
            <td style={{ padding: 8, textAlign: "right" }}>{b.total_rooms}</td>
            <td style={{ padding: 8, textAlign: "right" }}>{b.rooms_picked_up}</td>
            <td style={{ padding: 8, textAlign: "right" }}>{b.washed_count}</td>
            <td style={{ padding: 8, textAlign: "right" }}>{b.pickup_pct}%</td>
            <td style={{ padding: 8 }}>
              <button onClick={() => showPickup(b.id)}>Pickup</button>{" "}
              <button onClick={() => wash(b.id)}>Wash</button>
            </td>
          </tr>
        ))}</tbody>
      </table>

      {pickup && selected && (
        <div style={{ marginTop: 24, padding: 16, background: "#f7f7f7", borderRadius: 8 }}>
          <h3>Pickup Eğrisi: {pickup.group_name}</h3>
          <div>Toplam: {pickup.total_rooms} · Alınan: {pickup.picked_up} · Kalan: {pickup.remaining}</div>
          <table style={{ width: "100%", marginTop: 8 }}>
            <thead><tr><th>Tarih</th><th>Günlük</th><th>Kümülatif</th></tr></thead>
            <tbody>{(pickup.pickup_curve || []).map(p => (
              <tr key={p.date}><td>{p.date}</td><td style={{ textAlign: "right" }}>{p.rooms}</td><td style={{ textAlign: "right" }}>{p.cumulative}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
