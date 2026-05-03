import { useEffect, useState } from "react";
import api from "@/api/axios";

export default function LoyaltyAdminPage() {
  const [tab, setTab] = useState("tiers");
  const [tiers, setTiers] = useState([]);
  const [members, setMembers] = useState([]);
  const [rewards, setRewards] = useState([]);
  const [err, setErr] = useState("");

  const reload = async () => {
    try {
      const [t, m, r] = await Promise.all([
        api.get("/api/loyalty/tiers"),
        api.get("/api/loyalty/members"),
        api.get("/api/loyalty/rewards", { params: { active_only: false } }),
      ]);
      setTiers(t.data || []);
      setMembers(m.data || []);
      setRewards(r.data || []);
      setErr("");
    } catch (e) {
      setErr(e?.response?.data?.detail || "Yüklenemedi");
    }
  };
  useEffect(() => { reload(); }, []);

  // ── Tiers form
  const [tierForm, setTierForm] = useState({ name: "", min_points: 0, earn_multiplier: 1, color: "#888", benefits: "" });
  const addTier = async (e) => {
    e.preventDefault();
    await api.post("/api/loyalty/tiers", {
      ...tierForm,
      min_points: Number(tierForm.min_points),
      earn_multiplier: Number(tierForm.earn_multiplier),
      benefits: tierForm.benefits.split(",").map(s => s.trim()).filter(Boolean),
    });
    setTierForm({ name: "", min_points: 0, earn_multiplier: 1, color: "#888", benefits: "" });
    reload();
  };

  // ── Member enroll + earn
  const [enrollForm, setEnrollForm] = useState({ guest_id: "" });
  const [earnForm, setEarnForm] = useState({ guest_id: "", points: 100, source: "stay" });
  const enroll = async (e) => {
    e.preventDefault();
    await api.post("/api/loyalty/members/enroll", { guest_id: enrollForm.guest_id });
    setEnrollForm({ guest_id: "" });
    reload();
  };
  const earn = async (e) => {
    e.preventDefault();
    const { data } = await api.post("/api/loyalty/earn", {
      guest_id: earnForm.guest_id,
      points: Number(earnForm.points),
      source: earnForm.source,
    });
    alert(`+${data.awarded} puan, yeni bakiye: ${data.balance}, tier: ${data.tier || "-"}`);
    reload();
  };

  // ── Rewards
  const [rewardForm, setRewardForm] = useState({ name: "", points_cost: 1000, type: "discount", value: 0, stock: "" });
  const addReward = async (e) => {
    e.preventDefault();
    await api.post("/api/loyalty/rewards", {
      ...rewardForm,
      points_cost: Number(rewardForm.points_cost),
      value: Number(rewardForm.value),
      stock: rewardForm.stock === "" ? null : Number(rewardForm.stock),
    });
    setRewardForm({ name: "", points_cost: 1000, type: "discount", value: 0, stock: "" });
    reload();
  };
  const redeem = async (reward_id) => {
    const guest_id = prompt("Misafir ID?");
    if (!guest_id) return;
    try {
      const { data } = await api.post("/api/loyalty/redeem", { guest_id, reward_id });
      alert(`Ödül kullanıldı. Kalan bakiye: ${data.balance_after}`);
      reload();
    } catch (e) {
      alert(e?.response?.data?.detail || "Ödül kullanılamadı");
    }
  };

  return (
    <div style={{ padding: 24, maxWidth: 1200, margin: "0 auto" }}>
      <h2>Loyalty Yönetimi</h2>
      {err && <div style={{ color: "crimson" }}>{err}</div>}
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {["tiers", "members", "rewards"].map(t => (
          <button key={t} onClick={() => setTab(t)}
            style={{ fontWeight: tab === t ? 700 : 400 }}>
            {t === "tiers" ? "Seviyeler" : t === "members" ? "Üyeler" : "Ödüller"}
          </button>
        ))}
      </div>

      {tab === "tiers" && (
        <div>
          <form onSubmit={addTier} style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(5, 1fr)", marginBottom: 16 }}>
            <input placeholder="Ad (Bronze)" value={tierForm.name} onChange={e => setTierForm({ ...tierForm, name: e.target.value })} required />
            <input type="number" placeholder="Min puan" value={tierForm.min_points} onChange={e => setTierForm({ ...tierForm, min_points: e.target.value })} />
            <input type="number" step="0.1" placeholder="Çarpan" value={tierForm.earn_multiplier} onChange={e => setTierForm({ ...tierForm, earn_multiplier: e.target.value })} />
            <input placeholder="Avantajlar (virgülle)" value={tierForm.benefits} onChange={e => setTierForm({ ...tierForm, benefits: e.target.value })} />
            <button type="submit">Ekle</button>
          </form>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr style={{ background: "#eee" }}>
              <th style={{ padding: 8, textAlign: "left" }}>Ad</th>
              <th style={{ padding: 8 }}>Min Puan</th>
              <th style={{ padding: 8 }}>Çarpan</th>
              <th style={{ padding: 8, textAlign: "left" }}>Avantajlar</th>
            </tr></thead>
            <tbody>{tiers.map(t => (
              <tr key={t.id} style={{ borderBottom: "1px solid #eee" }}>
                <td style={{ padding: 8 }}><span style={{ background: t.color, color: "white", padding: "2px 8px", borderRadius: 4 }}>{t.name}</span></td>
                <td style={{ padding: 8, textAlign: "center" }}>{t.min_points}</td>
                <td style={{ padding: 8, textAlign: "center" }}>{t.earn_multiplier}x</td>
                <td style={{ padding: 8 }}>{(t.benefits || []).join(", ")}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}

      {tab === "members" && (
        <div>
          <div style={{ display: "flex", gap: 16, marginBottom: 16 }}>
            <form onSubmit={enroll} style={{ display: "flex", gap: 8 }}>
              <input placeholder="Misafir ID" value={enrollForm.guest_id} onChange={e => setEnrollForm({ guest_id: e.target.value })} required />
              <button type="submit">Üye Yap</button>
            </form>
            <form onSubmit={earn} style={{ display: "flex", gap: 8 }}>
              <input placeholder="Misafir ID" value={earnForm.guest_id} onChange={e => setEarnForm({ ...earnForm, guest_id: e.target.value })} required />
              <input type="number" placeholder="Puan" value={earnForm.points} onChange={e => setEarnForm({ ...earnForm, points: e.target.value })} />
              <input placeholder="Kaynak" value={earnForm.source} onChange={e => setEarnForm({ ...earnForm, source: e.target.value })} />
              <button type="submit">Puan Ver</button>
            </form>
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr style={{ background: "#eee" }}>
              <th style={{ padding: 8, textAlign: "left" }}>Misafir</th>
              <th style={{ padding: 8 }}>Tier</th>
              <th style={{ padding: 8 }}>Bakiye</th>
              <th style={{ padding: 8 }}>Lifetime</th>
            </tr></thead>
            <tbody>{members.map(m => (
              <tr key={m.id} style={{ borderBottom: "1px solid #eee" }}>
                <td style={{ padding: 8, fontFamily: "monospace" }}>{m.guest_id}</td>
                <td style={{ padding: 8, textAlign: "center" }}>{m.tier_name || "-"}</td>
                <td style={{ padding: 8, textAlign: "right" }}>{m.points_balance}</td>
                <td style={{ padding: 8, textAlign: "right" }}>{m.points_lifetime}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}

      {tab === "rewards" && (
        <div>
          <form onSubmit={addReward} style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(6, 1fr)", marginBottom: 16 }}>
            <input placeholder="Ad" value={rewardForm.name} onChange={e => setRewardForm({ ...rewardForm, name: e.target.value })} required />
            <input type="number" placeholder="Puan" value={rewardForm.points_cost} onChange={e => setRewardForm({ ...rewardForm, points_cost: e.target.value })} />
            <select value={rewardForm.type} onChange={e => setRewardForm({ ...rewardForm, type: e.target.value })}>
              {["discount","free_night","upgrade","amenity","fnb","spa"].map(o => <option key={o}>{o}</option>)}
            </select>
            <input type="number" placeholder="Değer" value={rewardForm.value} onChange={e => setRewardForm({ ...rewardForm, value: e.target.value })} />
            <input type="number" placeholder="Stok (boş=∞)" value={rewardForm.stock} onChange={e => setRewardForm({ ...rewardForm, stock: e.target.value })} />
            <button type="submit">Ekle</button>
          </form>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr style={{ background: "#eee" }}>
              <th style={{ padding: 8, textAlign: "left" }}>Ad</th>
              <th style={{ padding: 8 }}>Tip</th>
              <th style={{ padding: 8 }}>Puan</th>
              <th style={{ padding: 8 }}>Değer</th>
              <th style={{ padding: 8 }}>Stok</th>
              <th style={{ padding: 8 }}>Aksiyon</th>
            </tr></thead>
            <tbody>{rewards.map(r => (
              <tr key={r.id} style={{ borderBottom: "1px solid #eee", opacity: r.active ? 1 : 0.5 }}>
                <td style={{ padding: 8 }}>{r.name}</td>
                <td style={{ padding: 8, textAlign: "center" }}>{r.type}</td>
                <td style={{ padding: 8, textAlign: "right" }}>{r.points_cost}</td>
                <td style={{ padding: 8, textAlign: "right" }}>{r.value || "-"}</td>
                <td style={{ padding: 8, textAlign: "right" }}>{r.stock ?? "∞"}</td>
                <td style={{ padding: 8 }}>{r.active && <button onClick={() => redeem(r.id)}>Kullandır</button>}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
