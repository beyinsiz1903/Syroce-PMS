import { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { useTranslation } from 'react-i18next';
import { useNavigate } from "react-router-dom";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import {
  Sparkles, ExternalLink, Loader2, ShieldCheck, AlertCircle,
  ShoppingBag, Wrench, Crown, Search, Check
} from "lucide-react";
import api from "@/api/axios";

// A simple autocomplete component for Guest Search
function GuestSearchAutocomplete({ onSelect, selectedGuest, placeholder }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (query.length < 3) {
      setResults([]);
      setOpen(false);
      return;
    }
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await api.get(`/pms/guests/search?q=${query}&limit=5`);
        setResults(res.data?.items || res.data || []);
        setOpen(true);
      } catch (e) {
        console.error(e);
      }
      setLoading(false);
    }, 400);
    return () => clearTimeout(timer);
  }, [query]);

  return (
    <div className="relative w-full">
      {!selectedGuest ? (
        <>
          <div className="relative">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder={placeholder || "İsim, e-posta, tel (en az 3 hrf)..."}
              className="pl-8"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onFocus={() => { if(results.length > 0) setOpen(true); }}
              onBlur={() => setTimeout(() => setOpen(false), 200)}
            />
            {loading && <Loader2 className="absolute right-2 top-2.5 h-4 w-4 animate-spin text-muted-foreground" />}
          </div>
          {open && results.length > 0 && (
            <div className="absolute z-10 w-full mt-1 bg-white border rounded-md shadow-lg max-h-60 overflow-auto">
              {results.map((g) => (
                <div
                  key={g.id || g.guest_id}
                  className="px-3 py-2 hover:bg-slate-100 cursor-pointer text-sm flex justify-between items-center"
                  onMouseDown={() => {
                    onSelect(g);
                    setQuery("");
                    setOpen(false);
                  }}
                >
                  <div className="flex flex-col">
                    <span className="font-medium">{g.name || `${g.first_name || ''} ${g.last_name || ''}`}</span>
                    <span className="text-xs text-slate-500">{g.email} | {g.phone}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      ) : (
        <div className="flex items-center justify-between border px-3 py-2 rounded-md bg-slate-50">
          <div className="flex flex-col">
            <span className="font-medium text-sm">{selectedGuest.name || `${selectedGuest.first_name || ''} ${selectedGuest.last_name || ''}`}</span>
            <span className="text-xs text-slate-500">ID: {selectedGuest.id || selectedGuest.guest_id}</span>
          </div>
          <Button variant="ghost" size="sm" onClick={() => onSelect(null)} className="h-6 px-2 text-xs">Değiştir</Button>
        </div>
      )}
    </div>
  );
}

export default function AfsadakatLauncher({ user, tenant, onLogout }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  
  // Launcher state
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [opening, setOpening] = useState(false);

  // Loyalty Admin state
  const [tiers, setTiers] = useState([]);
  const [members, setMembers] = useState([]);
  const [rewards, setRewards] = useState([]);
  
  // Forms
  const [tierForm, setTierForm] = useState({ name: "", min_points: 0, earn_multiplier: 1, color: "#888", benefits: "" });
  const [selectedEnrollGuest, setSelectedEnrollGuest] = useState(null);
  const [selectedEarnGuest, setSelectedEarnGuest] = useState(null);
  const [earnForm, setEarnForm] = useState({ points: 100, source: "stay" });
  const [rewardForm, setRewardForm] = useState({ name: "", points_cost: 1000, type: "discount", value: 0, stock: "" });

  const refreshLoyalty = async () => {
    try {
      const [t_res, m, r] = await Promise.all([
        api.get("/loyalty/tiers"),
        api.get("/loyalty/members"),
        api.get("/loyalty/rewards", { params: { active_only: false } }),
      ]);
      setTiers(t_res.data || []);
      setMembers(m.data || []);
      setRewards(r.data || []);
    } catch (e) {
      console.error(e);
    }
  };

  const refreshAll = async () => {
    setLoading(true);
    try {
      const r = await axios.get("/integrations/afsadakat/status");
      setStatus(r.data);
      await refreshLoyalty();
    } catch (e) {
      toast.error("Durum alınamadı");
    }
    setLoading(false);
  };

  useEffect(() => { refreshAll(); }, []);

  const handleLaunch = async () => {
    setOpening(true);
    try {
      const r = await axios.post("/integrations/afsadakat/launch");
      const url = r.data?.url || "";
      if (!url) throw new Error("URL boş");
      if (!r.data?.external_ready || url.startsWith("/integrations/afsadakat/not-deployed")) {
        toast.warning(
          "Af-sadakat sunucusu henüz konfigüre edilmemiş. " +
          "Yöneticiniz AFSADAKAT_BASE_URL ayarladığında bu buton hedef sayfayı açacak.",
          { duration: 7000 }
        );
        return;
      }
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Açılamadı");
    }
    setOpening(false);
  };

  // Loyalty actions
  const addTier = async (e) => {
    e.preventDefault();
    try {
      await api.post("/loyalty/tiers", {
        ...tierForm,
        min_points: Number(tierForm.min_points),
        earn_multiplier: Number(tierForm.earn_multiplier),
        benefits: tierForm.benefits.split(",").map(s => s.trim()).filter(Boolean),
      });
      setTierForm({ name: "", min_points: 0, earn_multiplier: 1, color: "#888", benefits: "" });
      toast.success("Seviye eklendi");
      refreshLoyalty();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Eklenemedi");
    }
  };

  const enroll = async (e) => {
    e.preventDefault();
    if (!selectedEnrollGuest) return toast.error("Lütfen misafir seçin");
    try {
      const gId = selectedEnrollGuest.id || selectedEnrollGuest.guest_id;
      await api.post("/loyalty/members/enroll", { guest_id: gId });
      setSelectedEnrollGuest(null);
      toast.success("Misafir üye yapıldı");
      refreshLoyalty();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Üye yapılamadı");
    }
  };

  const earn = async (e) => {
    e.preventDefault();
    if (!selectedEarnGuest) return toast.error("Lütfen misafir seçin");
    try {
      const gId = selectedEarnGuest.id || selectedEarnGuest.guest_id;
      await api.post("/loyalty/members/earn", {
        guest_id: gId,
        points: Number(earnForm.points),
        source: earnForm.source
      }, { headers: { 'Idempotency-Key': crypto.randomUUID() } });
      setSelectedEarnGuest(null);
      setEarnForm({ points: 100, source: "stay" });
      toast.success("Puan eklendi");
      refreshLoyalty();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Puan verilemedi");
    }
  };

  const addReward = async (e) => {
    e.preventDefault();
    try {
      await api.post("/loyalty/rewards", {
        ...rewardForm,
        points_cost: Number(rewardForm.points_cost),
        value: Number(rewardForm.value),
        stock: rewardForm.stock === "" ? null : Number(rewardForm.stock),
      });
      setRewardForm({ name: "", points_cost: 1000, type: "discount", value: 0, stock: "" });
      toast.success("Ödül eklendi");
      refreshLoyalty();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Eklenemedi");
    }
  };

  const redeem = async (reward_id) => {
    const guest_id = window.prompt("Kullandırılacak Misafir ID'sini girin:");
    if (!guest_id) return;
    try {
      const { data } = await api.post("/loyalty/redeem", { guest_id, reward_id }, {
        headers: { 'Idempotency-Key': crypto.randomUUID() }
      });
      toast.success(`Ödül kullanıldı. Kalan bakiye: ${data.balance_after}`);
      refreshLoyalty();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Ödül kullanılamadı");
    }
  };

  if (loading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
      </div>
    );
  }

  const entitled = !!status?.entitled;
  const provisioned = !!status?.provisioned;
  const externalReady = !!status?.external_configured;
  const isSuperAdmin = user?.role === "super_admin"
    || user?.role === "platform_admin"
    || (Array.isArray(user?.roles)
        && user.roles.some((r) => r === "super_admin" || r === "platform_admin"));
  const viaSuper = status?.entitlement_source === "super_admin" || (isSuperAdmin && !status?.entitled);
  const effectiveEntitled = entitled || isSuperAdmin;

  return (
    <div className="max-w-6xl mx-auto p-4 sm:p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
          <Sparkles className="w-6 h-6 text-indigo-600" />
          Sadakat & Omni Inbox
        </h1>
        <p className="text-sm text-slate-600 mt-1">
          {t('cm.pages_AfsadakatLauncher.sadakat_programi_ai_yorum_yonetimi_whats')}
        </p>
      </div>

      <Tabs defaultValue="launcher" className="space-y-4">
        <TabsList>
          <TabsTrigger value="launcher">Harici Bağlantı (Inbox)</TabsTrigger>
          <TabsTrigger value="members">Üyeler & Puan</TabsTrigger>
          <TabsTrigger value="tiers">Seviyeler</TabsTrigger>
          <TabsTrigger value="rewards">Ödüller</TabsTrigger>
        </TabsList>

        <TabsContent value="launcher">
          <div className="max-w-3xl">
          {!effectiveEntitled && (
            <Card className="border-amber-200 bg-amber-50">
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2 text-amber-900">
                  <AlertCircle className="w-5 h-5" /> {t('cm.pages_AfsadakatLauncher.aktif_aboneliginiz_yok')}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-amber-900">
                  {t('cm.pages_AfsadakatLauncher.bu_modulu_kullanmak_icin_modul_pazari_nd')}
                </p>
                <Button onClick={() => navigate("/app/module-store")}>
                  <ShoppingBag className="w-4 h-4 mr-1" /> {t('cm.pages_AfsadakatLauncher.modul_pazari_na_git')}
                </Button>
              </CardContent>
            </Card>
          )}

          {effectiveEntitled && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <ShieldCheck className="w-5 h-5 text-emerald-600" />
                  {t('cm.pages_AfsadakatLauncher.baglanti_durumu')}
                  {viaSuper && (
                    <Badge className="bg-indigo-100 text-indigo-800 border-indigo-200 ml-1">
                      <Crown className="w-3 h-3 mr-1" /> {t('cm.pages_AfsadakatLauncher.super_admin_erisimi')}
                    </Badge>
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {viaSuper && (
                  <div className="border-l-4 border-indigo-400 bg-indigo-50 px-3 py-2 text-sm text-indigo-900">
                    {t('cm.pages_AfsadakatLauncher.bu_tenant_in_aktif_af_sadakat_aboneligi_')}
                  </div>
                )}
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="flex items-center justify-between border rounded-md px-3 py-2">
                    <span className="text-slate-600">Abonelik</span>
                    <Badge className={entitled
                      ? "bg-emerald-100 text-emerald-800 border-emerald-200"
                      : "bg-slate-100 text-slate-700 border-slate-200"}>
                      {entitled ? "Aktif" : "Yok (süper-admin)"}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between border rounded-md px-3 py-2">
                    <span className="text-slate-600">{t('cm.pages_AfsadakatLauncher.hazirlik')}</span>
                    <Badge className={provisioned
                      ? "bg-emerald-100 text-emerald-800 border-emerald-200"
                      : "bg-amber-100 text-amber-800 border-amber-200"}>
                      {provisioned ? "Tamamlandı" : "Bekliyor"}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between border rounded-md px-3 py-2 col-span-2">
                    <span className="text-slate-600">Mod</span>
                    <Badge variant="outline">
                      {status?.mode === "external" ? "Harici sunucu bağlı" :
                       externalReady ? "Bağlanılıyor" : "Yerel (Af-sadakat henüz yayında değil)"}
                    </Badge>
                  </div>
                </div>

                {!externalReady && (
                  <div className="border-l-4 border-amber-400 bg-amber-50 px-3 py-2 text-sm text-amber-900 flex gap-2">
                    <Wrench className="w-4 h-4 mt-0.5 shrink-0" />
                    <div>
                      {t('cm.pages_AfsadakatLauncher.af_sadakat_sunucusu_henuz_konfigure_edil')}
                    </div>
                  </div>
                )}

                <Button
                  onClick={handleLaunch}
                  disabled={opening}
                  size="lg"
                  className="w-full"
                >
                  {opening ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <>
                      <ExternalLink className="w-5 h-5 mr-2" />
                      {t('cm.pages_AfsadakatLauncher.sadakat_inbox_i_yeni_sekmede_ac')}
                    </>
                  )}
                </Button>
                <p className="text-xs text-slate-500 text-center">
                  {t('cm.pages_AfsadakatLauncher.tek_kullanimlik_guvenli_giris_baglantisi')}
                </p>
              </CardContent>
            </Card>
          )}
          </div>
        </TabsContent>

        <TabsContent value="members">
          <Card>
            <CardHeader>
              <CardTitle>Üye Yönetimi ve Puan Verme</CardTitle>
              <CardDescription>Misafirleri sadakat programına dahil edin veya puan yükleyin.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Enroll Form */}
                <form onSubmit={enroll} className="space-y-3 p-4 border rounded-lg bg-slate-50">
                  <h3 className="font-medium text-sm">Misafiri Üye Yap</h3>
                  <GuestSearchAutocomplete 
                    selectedGuest={selectedEnrollGuest} 
                    onSelect={setSelectedEnrollGuest} 
                  />
                  <Button type="submit" disabled={!selectedEnrollGuest} className="w-full">Üye Yap</Button>
                </form>

                {/* Earn Form */}
                <form onSubmit={earn} className="space-y-3 p-4 border rounded-lg bg-slate-50">
                  <h3 className="font-medium text-sm">Puan Ver</h3>
                  <GuestSearchAutocomplete 
                    selectedGuest={selectedEarnGuest} 
                    onSelect={setSelectedEarnGuest} 
                  />
                  <div className="flex gap-2">
                    <Input type="number" placeholder="Puan" value={earnForm.points} onChange={e => setEarnForm({ ...earnForm, points: e.target.value })} />
                    <Input placeholder="Kaynak" value={earnForm.source} onChange={e => setEarnForm({ ...earnForm, source: e.target.value })} />
                  </div>
                  <Button type="submit" disabled={!selectedEarnGuest} className="w-full">Puan Ver</Button>
                </form>
              </div>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Misafir ID</TableHead>
                    <TableHead>Tier</TableHead>
                    <TableHead className="text-right">Bakiye</TableHead>
                    <TableHead className="text-right">Lifetime</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {members.map(m => (
                    <TableRow key={m.id}>
                      <TableCell className="font-mono text-xs">{m.guest_id}</TableCell>
                      <TableCell><Badge variant="outline">{m.tier_name || "-"}</Badge></TableCell>
                      <TableCell className="text-right font-medium">{m.points_balance}</TableCell>
                      <TableCell className="text-right text-muted-foreground">{m.points_lifetime}</TableCell>
                    </TableRow>
                  ))}
                  {members.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={4} className="text-center py-4 text-muted-foreground">Kayıtlı üye bulunamadı.</TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="tiers">
          <Card>
            <CardHeader>
              <CardTitle>Sadakat Seviyeleri (Tiers)</CardTitle>
              <CardDescription>Üyelik katmanlarını ve avantajları tanımlayın.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <form onSubmit={addTier} className="grid grid-cols-1 md:grid-cols-5 gap-3 items-end p-4 border rounded-lg bg-slate-50">
                <div>
                  <label className="text-xs font-medium">Ad (Örn. Bronze)</label>
                  <Input value={tierForm.name} onChange={e => setTierForm({ ...tierForm, name: e.target.value })} required />
                </div>
                <div>
                  <label className="text-xs font-medium">Min Puan</label>
                  <Input type="number" value={tierForm.min_points} onChange={e => setTierForm({ ...tierForm, min_points: e.target.value })} />
                </div>
                <div>
                  <label className="text-xs font-medium">Çarpan (örn. 1.5)</label>
                  <Input type="number" step="0.1" value={tierForm.earn_multiplier} onChange={e => setTierForm({ ...tierForm, earn_multiplier: e.target.value })} />
                </div>
                <div className="md:col-span-1">
                  <label className="text-xs font-medium">Avantajlar (Virgülle)</label>
                  <Input placeholder="Erken Check-in, İndirim" value={tierForm.benefits} onChange={e => setTierForm({ ...tierForm, benefits: e.target.value })} />
                </div>
                <Button type="submit">Ekle</Button>
              </form>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Ad</TableHead>
                    <TableHead className="text-center">Min Puan</TableHead>
                    <TableHead className="text-center">Çarpan</TableHead>
                    <TableHead>Avantajlar</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tiers.map(t => (
                    <TableRow key={t.id}>
                      <TableCell>
                        <span style={{ backgroundColor: t.color || '#888' }} className="px-2 py-1 rounded text-white text-xs font-medium">{t.name}</span>
                      </TableCell>
                      <TableCell className="text-center">{t.min_points}</TableCell>
                      <TableCell className="text-center">{t.earn_multiplier}x</TableCell>
                      <TableCell>{(t.benefits || []).join(", ")}</TableCell>
                    </TableRow>
                  ))}
                  {tiers.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={4} className="text-center py-4 text-muted-foreground">Seviye tanımlanmamış.</TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="rewards">
          <Card>
            <CardHeader>
              <CardTitle>Ödüller</CardTitle>
              <CardDescription>Misafirlerin puanlarıyla alabileceği ödülleri yapılandırın.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <form onSubmit={addReward} className="grid grid-cols-1 md:grid-cols-6 gap-3 items-end p-4 border rounded-lg bg-slate-50">
                <div className="md:col-span-2">
                  <label className="text-xs font-medium">Ad</label>
                  <Input value={rewardForm.name} onChange={e => setRewardForm({ ...rewardForm, name: e.target.value })} required />
                </div>
                <div>
                  <label className="text-xs font-medium">Puan Bedeli</label>
                  <Input type="number" value={rewardForm.points_cost} onChange={e => setRewardForm({ ...rewardForm, points_cost: e.target.value })} />
                </div>
                <div>
                  <label className="text-xs font-medium">Tip</label>
                  <select className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm" value={rewardForm.type} onChange={e => setRewardForm({ ...rewardForm, type: e.target.value })}>
                    {["discount","free_night","upgrade","amenity","fnb","spa"].map(o => <option key={o}>{o}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium">Değer</label>
                  <Input type="number" value={rewardForm.value} onChange={e => setRewardForm({ ...rewardForm, value: e.target.value })} />
                </div>
                <Button type="submit">Ekle</Button>
              </form>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Ad</TableHead>
                    <TableHead className="text-center">Tip</TableHead>
                    <TableHead className="text-right">Puan</TableHead>
                    <TableHead className="text-right">Değer</TableHead>
                    <TableHead className="text-right">Stok</TableHead>
                    <TableHead className="text-center">Aksiyon</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rewards.map(r => (
                    <TableRow key={r.id} className={r.active ? "" : "opacity-50"}>
                      <TableCell className="font-medium">{r.name}</TableCell>
                      <TableCell className="text-center"><Badge variant="outline">{r.type}</Badge></TableCell>
                      <TableCell className="text-right font-bold text-indigo-600">{r.points_cost}</TableCell>
                      <TableCell className="text-right">{r.value || "-"}</TableCell>
                      <TableCell className="text-right">{r.stock ?? "∞"}</TableCell>
                      <TableCell className="text-center">
                        {r.active && <Button size="sm" variant="outline" onClick={() => redeem(r.id)}>Kullandır</Button>}
                      </TableCell>
                    </TableRow>
                  ))}
                  {rewards.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={6} className="text-center py-4 text-muted-foreground">Ödül bulunamadı.</TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
