import { useEffect, useState } from "react";
import api from "@/api/axios";

export default function FolioRoutingPage() {
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [form, setForm] = useState({
    source_folio_id: "",
    dest_folio_id: "",
    charge_codes: "",
    note: "",
  });

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/api/folio-routing");
      setRules(data || []);
      setErr("");
    } catch (e) {
      setErr(e?.response?.data?.detail || "Yüklenemedi");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post("/api/folio-routing", {
        source_folio_id: form.source_folio_id.trim(),
        dest_folio_id: form.dest_folio_id.trim(),
        charge_codes: form.charge_codes
          .split(",").map(s => s.trim()).filter(Boolean),
        note: form.note || null,
      });
      setForm({ source_folio_id: "", dest_folio_id: "", charge_codes: "", note: "" });
      load();
    } catch (e) {
      setErr(e?.response?.data?.detail || "Kayıt başarısız");
    }
  };

  const remove = async (id) => {
    if (!confirm("Bu yönlendirme kuralı silinsin mi?")) return;
    await api.delete(`/api/folio-routing/${id}`);
    load();
  };

  const apply = async (folio_id) => {
    try {
      const { data } = await api.post(`/api/folio-routing/apply/${folio_id}`);
      alert(`Uygulandı: ${data.moved} ücret taşındı (${data.rules} kural)`);
    } catch (e) {
      alert(e?.response?.data?.detail || "Uygulanamadı");
    }
  };

  return (
    <div style={{ padding: 24, maxWidth: 1100, margin: "0 auto" }}>
      <h2>Folio Yönlendirme Kuralları</h2>
      <p style={{ color: "#666" }}>
        Bir oda folio'sundaki belirli ücretleri (oda, kahvaltı, vergi…) otomatik
        olarak şirket / master folioya yönlendirin.
      </p>

      <form onSubmit={submit} style={{ display: "grid", gap: 8, marginTop: 16, padding: 16, background: "#f7f7f7", borderRadius: 8 }}>
        <h3 style={{ margin: 0 }}>Yeni Kural</h3>
        <input placeholder="Kaynak folio ID (oda misafiri)"
          value={form.source_folio_id}
          onChange={e => setForm({ ...form, source_folio_id: e.target.value })} required />
        <input placeholder="Hedef folio ID (şirket / master)"
          value={form.dest_folio_id}
          onChange={e => setForm({ ...form, dest_folio_id: e.target.value })} required />
        <input placeholder="Ücret kodları (virgülle, boş = TÜM): ROOM,TAX,BREAKFAST"
          value={form.charge_codes}
          onChange={e => setForm({ ...form, charge_codes: e.target.value })} />
        <input placeholder="Not (opsiyonel)"
          value={form.note}
          onChange={e => setForm({ ...form, note: e.target.value })} />
        <button type="submit">Kural Ekle</button>
      </form>

      <h3 style={{ marginTop: 24 }}>Mevcut Kurallar</h3>
      {err && <div style={{ color: "crimson" }}>{err}</div>}
      {loading ? <div>Yükleniyor…</div> : rules.length === 0 ? (
        <div style={{ color: "#888" }}>Henüz kural yok.</div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "#eee" }}>
              <th style={{ textAlign: "left", padding: 8 }}>Kaynak</th>
              <th style={{ textAlign: "left", padding: 8 }}>Hedef</th>
              <th style={{ textAlign: "left", padding: 8 }}>Ücret Kodları</th>
              <th style={{ textAlign: "left", padding: 8 }}>Not</th>
              <th style={{ padding: 8 }}>Aksiyon</th>
            </tr>
          </thead>
          <tbody>
            {rules.map(r => (
              <tr key={r.id} style={{ borderBottom: "1px solid #eee" }}>
                <td style={{ padding: 8, fontFamily: "monospace" }}>{r.source_folio_id}</td>
                <td style={{ padding: 8, fontFamily: "monospace" }}>{r.dest_folio_id}</td>
                <td style={{ padding: 8 }}>{(r.charge_codes || []).join(", ") || "TÜM"}</td>
                <td style={{ padding: 8 }}>{r.note || "-"}</td>
                <td style={{ padding: 8, textAlign: "right" }}>
                  <button onClick={() => apply(r.source_folio_id)}>Uygula</button>{" "}
                  <button onClick={() => remove(r.id)} style={{ color: "crimson" }}>Sil</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
