import { useEffect, useState } from "react";
import api from "@/api/axios";

const TYPES = ["golf", "tennis", "yoga", "fitness", "bike", "diving", "kids", "other"];

export default function ActivitySchedulerPage() {
  const [tab, setTab] = useState("schedule");
  const [activities, setActivities] = useState([]);
  const [resources, setResources] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [err, setErr] = useState("");

  const load = async () => {
    try {
      const [a, r, b] = await Promise.all([
        api.get("/api/activities"),
        api.get("/api/activities/resources"),
        api.get("/api/activities/bookings", { params: { date } }),
      ]);
      setActivities(a.data || []);
      setResources(r.data || []);
      setBookings(b.data || []);
      setErr("");
    } catch (e) {
      setErr(e?.response?.data?.detail || "Yüklenemedi");
    }
  };
  useEffect(() => { load(); }, [date]);

  const [actForm, setActForm] = useState({ name: "", type: "golf", duration_min: 60, price: 0, capacity: 1 });
  const addActivity = async (e) => {
    e.preventDefault();
    await api.post("/api/activities", { ...actForm, duration_min: Number(actForm.duration_min), price: Number(actForm.price), capacity: Number(actForm.capacity) });
    setActForm({ name: "", type: "golf", duration_min: 60, price: 0, capacity: 1 });
    load();
  };

  const [resForm, setResForm] = useState({ name: "", kind: "instructor", activity_types: "", capacity: 1 });
  const addResource = async (e) => {
    e.preventDefault();
    await api.post("/api/activities/resources", {
      ...resForm,
      capacity: Number(resForm.capacity),
      activity_types: resForm.activity_types.split(",").map(s => s.trim()).filter(Boolean),
    });
    setResForm({ name: "", kind: "instructor", activity_types: "", capacity: 1 });
    load();
  };

  const [bkForm, setBkForm] = useState({ activity_id: "", resource_id: "", guest_id: "", starts_at: "", note: "" });
  const book = async (e) => {
    e.preventDefault();
    try {
      await api.post("/api/activities/bookings", bkForm);
      setBkForm({ activity_id: "", resource_id: "", guest_id: "", starts_at: "", note: "" });
      load();
    } catch (e) {
      alert(e?.response?.data?.detail || "Kayıt başarısız");
    }
  };

  const cancel = async (id) => {
    if (!confirm("İptal edilsin mi?")) return;
    await api.post(`/api/activities/bookings/${id}/cancel`);
    load();
  };

  return (
    <div style={{ padding: 24, maxWidth: 1300, margin: "0 auto" }}>
      <h2>Aktivite Takvimi</h2>
      <p style={{ color: "#666" }}>Golf, tenis, yoga, dalış, çocuk kulübü… Eğitmen / mekan / ekipman atayarak çakışmasız rezervasyon.</p>
      {err && <div style={{ color: "crimson" }}>{err}</div>}

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {["schedule","activities","resources"].map(t => (
          <button key={t} onClick={() => setTab(t)} style={{ fontWeight: tab === t ? 700 : 400 }}>
            {t === "schedule" ? "Günlük Takvim" : t === "activities" ? "Aktivite Tanımları" : "Kaynaklar"}
          </button>
        ))}
      </div>

      {tab === "schedule" && (
        <div>
          <div style={{ display: "flex", gap: 16, marginBottom: 16, alignItems: "center" }}>
            <label>Tarih: <input type="date" value={date} onChange={e => setDate(e.target.value)} /></label>
          </div>
          <form onSubmit={book} style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 8, marginBottom: 16, padding: 12, background: "#f7f7f7", borderRadius: 8 }}>
            <select value={bkForm.activity_id} onChange={e => setBkForm({ ...bkForm, activity_id: e.target.value })} required>
              <option value="">Aktivite seç</option>
              {activities.map(a => <option key={a.id} value={a.id}>{a.name} ({a.type})</option>)}
            </select>
            <select value={bkForm.resource_id} onChange={e => setBkForm({ ...bkForm, resource_id: e.target.value })} required>
              <option value="">Kaynak seç</option>
              {resources.map(r => <option key={r.id} value={r.id}>{r.name} [{r.kind}]</option>)}
            </select>
            <input placeholder="Misafir ID" value={bkForm.guest_id} onChange={e => setBkForm({ ...bkForm, guest_id: e.target.value })} required />
            <input type="datetime-local" value={bkForm.starts_at} onChange={e => setBkForm({ ...bkForm, starts_at: e.target.value })} required />
            <input placeholder="Not" value={bkForm.note} onChange={e => setBkForm({ ...bkForm, note: e.target.value })} />
            <button type="submit">Rezerve Et</button>
          </form>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr style={{ background: "#eee" }}>
              <th style={{ padding: 8 }}>Saat</th>
              <th style={{ padding: 8 }}>Aktivite</th>
              <th style={{ padding: 8 }}>Kaynak</th>
              <th style={{ padding: 8 }}>Misafir</th>
              <th style={{ padding: 8 }}>Durum</th>
              <th style={{ padding: 8 }}></th>
            </tr></thead>
            <tbody>{bookings.map(b => {
              const act = activities.find(a => a.id === b.activity_id);
              const res = resources.find(r => r.id === b.resource_id);
              return (
                <tr key={b.id} style={{ borderBottom: "1px solid #eee", opacity: b.status === "cancelled" ? 0.4 : 1 }}>
                  <td style={{ padding: 8 }}>{b.starts_at?.slice(11, 16)} - {b.ends_at?.slice(11, 16)}</td>
                  <td style={{ padding: 8 }}>{act?.name || b.activity_id}</td>
                  <td style={{ padding: 8 }}>{res?.name || b.resource_id}</td>
                  <td style={{ padding: 8 }}>{b.guest_id}</td>
                  <td style={{ padding: 8 }}>{b.status}</td>
                  <td style={{ padding: 8 }}>{b.status !== "cancelled" && <button onClick={() => cancel(b.id)}>İptal</button>}</td>
                </tr>
              );
            })}</tbody>
          </table>
        </div>
      )}

      {tab === "activities" && (
        <div>
          <form onSubmit={addActivity} style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 8, marginBottom: 16 }}>
            <input placeholder="Ad" value={actForm.name} onChange={e => setActForm({ ...actForm, name: e.target.value })} required />
            <select value={actForm.type} onChange={e => setActForm({ ...actForm, type: e.target.value })}>
              {TYPES.map(t => <option key={t}>{t}</option>)}
            </select>
            <input type="number" placeholder="Süre (dk)" value={actForm.duration_min} onChange={e => setActForm({ ...actForm, duration_min: e.target.value })} />
            <input type="number" placeholder="Fiyat" value={actForm.price} onChange={e => setActForm({ ...actForm, price: e.target.value })} />
            <input type="number" placeholder="Kapasite" value={actForm.capacity} onChange={e => setActForm({ ...actForm, capacity: e.target.value })} />
            <button type="submit">Ekle</button>
          </form>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr style={{ background: "#eee" }}>
              <th style={{ padding: 8 }}>Ad</th><th style={{ padding: 8 }}>Tip</th>
              <th style={{ padding: 8 }}>Süre</th><th style={{ padding: 8 }}>Fiyat</th>
            </tr></thead>
            <tbody>{activities.map(a => (
              <tr key={a.id} style={{ borderBottom: "1px solid #eee" }}>
                <td style={{ padding: 8 }}>{a.name}</td>
                <td style={{ padding: 8, textAlign: "center" }}>{a.type}</td>
                <td style={{ padding: 8, textAlign: "center" }}>{a.duration_min} dk</td>
                <td style={{ padding: 8, textAlign: "right" }}>{a.price}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}

      {tab === "resources" && (
        <div>
          <form onSubmit={addResource} style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 8, marginBottom: 16 }}>
            <input placeholder="Ad (Hakan, Court 1)" value={resForm.name} onChange={e => setResForm({ ...resForm, name: e.target.value })} required />
            <select value={resForm.kind} onChange={e => setResForm({ ...resForm, kind: e.target.value })}>
              <option value="instructor">Eğitmen</option>
              <option value="venue">Mekan</option>
              <option value="equipment">Ekipman</option>
            </select>
            <input placeholder="Aktivite tipleri (golf,tennis)" value={resForm.activity_types} onChange={e => setResForm({ ...resForm, activity_types: e.target.value })} />
            <input type="number" placeholder="Kapasite" value={resForm.capacity} onChange={e => setResForm({ ...resForm, capacity: e.target.value })} />
            <button type="submit">Ekle</button>
          </form>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr style={{ background: "#eee" }}>
              <th style={{ padding: 8 }}>Ad</th><th style={{ padding: 8 }}>Tür</th>
              <th style={{ padding: 8 }}>Aktiviteler</th><th style={{ padding: 8 }}>Kapasite</th>
            </tr></thead>
            <tbody>{resources.map(r => (
              <tr key={r.id} style={{ borderBottom: "1px solid #eee" }}>
                <td style={{ padding: 8 }}>{r.name}</td>
                <td style={{ padding: 8, textAlign: "center" }}>{r.kind}</td>
                <td style={{ padding: 8 }}>{(r.activity_types || []).join(", ") || "tümü"}</td>
                <td style={{ padding: 8, textAlign: "right" }}>{r.capacity}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
