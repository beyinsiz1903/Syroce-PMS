import React, { useState } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { toast } from "sonner";
import { useTranslation } from 'react-i18next';

const PmsLiteLanding = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    full_name: "",
    phone: "",
    email: "",
    property_name: "",
    location: "",
    rooms_count: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [lastLead, setLastLead] = useState(null);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.phone.trim()) {
      toast.error("Telefon numarası gerekli");
      return;
    }
    if (!form.full_name.trim()) {
      toast.error("Ad Soyad gerekli");
      return;
    }
    if (!form.property_name.trim()) {
      toast.error("Otel adı gerekli");
      return;
    }

    const rooms = parseInt(form.rooms_count || "0", 10);
    if (Number.isNaN(rooms) || rooms < 1 || rooms > 200) {
      toast.error("Oda sayısı 1 ile 200 arasında olmalı");
      return;
    }

    setSubmitting(true);
    try {
      const payload = {
        contact: {
          full_name: form.full_name.trim(),
          phone: form.phone.trim(),
          email: form.email.trim() || undefined,
        },
        hotel: {
          property_name: form.property_name.trim(),
          location: form.location.trim() || undefined,
          rooms_count: rooms,
        },
        metadata: {},
      };

      const res = await axios.post("/leads", payload);
      if (res.data?.ok) {
        const lead_id = res.data.lead_id;
        const leadMessage = `Merhaba, Syroce {t('common.hotel')} için demo talebi oluşturdum.\n\nAd Soyad: ${payload.contact.full_name}\nTelefon: ${payload.contact.phone}\nOtel: ${payload.hotel.property_name}\nBölge: ${payload.hotel.location || "-"}\nOda Sayısı: ${payload.hotel.rooms_count}\n\nUygun olduğunuzda bilgi alabilir miyim?\n(Lead ID: ${lead_id})`;

        setLastLead({
          full_name: payload.contact.full_name,
          phone: payload.contact.phone,
          property_name: payload.hotel.property_name,
          location: payload.hotel.location,
          rooms_count: payload.hotel.rooms_count,
          lead_id,
          deduped: !!res.data.deduped,
          message: leadMessage,
        });

        toast.success("Talebiniz alındı, en kısa sürede sizi arayacağız.");
        setForm({
          full_name: "",
          phone: "",
          email: "",
          property_name: "",
          location: "",
          rooms_count: "",
        });
      } else {
        toast.error("Talep kaydedilemedi, lütfen daha sonra tekrar deneyin.");
      }
    } catch (e) {
      console.error(e);
      toast.error("Talep gönderilirken bir hata oluştu. Lütfen tekrar deneyin.");
    } finally {
      setSubmitting(false);
    }
  };

  const openWhatsApp = () => {
    const phone = "+905555555555"; // TODO: Gerçek WhatsApp numarası ile değiştir
    const text = encodeURIComponent(
      "Merhaba, PMS Lite hakkında demo talep etmek istiyorum."
    );
    window.open(`https://wa.me/${phone}?text=${text}`, "_blank");
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-900 via-slate-950 to-black text-white">
      <div className="max-w-5xl mx-auto px-4 py-10 space-y-10">
        {/* Hero */}
        <section className="space-y-6">
          <button
            className="text-sm text-slate-300 hover:text-white underline"
            onClick={() => navigate("/")}
          >
            ← Ana sayfaya dön
          </button>

          <div className="space-y-3">
            <h1 className="text-3xl md:text-4xl font-bold">
              Bungalov & Küçük Oteller için <span className="text-emerald-400">PMS Lite</span>
            </h1>
            <p className="text-slate-300 max-w-2xl text-sm md:text-base">
              Excel / WhatsApp karmaşasına son verin. 2 dakikada kurun, tüm rezervasyonlarınızı
              tek ekrandan yönetin.
            </p>
            <div className="flex items-baseline gap-3 text-emerald-300">
              <span className="text-3xl font-extrabold">1500 TL</span>
              <span className="text-sm">/ ay (5–20 oda bungalov & küçük oteller)</span>
            </div>
          </div>

          <div className="flex flex-col md:flex-row gap-4">
            <Button
              size="lg"
              className="bg-emerald-500 hover:bg-emerald-600 text-black font-semibold"
              onClick={openWhatsApp}
            >
              WhatsApp’tan Demo İste
            </Button>
            <p className="text-xs text-slate-400 max-w-sm">
              WhatsApp üzerinden hızlıca bilgi alın, 15 dakikalık online demo planlayalım.
            </p>
          </div>
        </section>

        {/* Neden PMS Lite */}
        <section className="grid md:grid-cols-3 gap-4">
          <Card className="bg-slate-900/60 border-slate-700">
            <CardHeader>
              <CardTitle className="text-sm font-semibold">Takvim & Rezervasyon Yönetimi</CardTitle>
              <CardDescription className="text-xs text-slate-400">
                Tüm giriş-çıkışları tek bir takvimde görün, çakışmaları ve overbook’u engelleyin.
              </CardDescription>
            </CardHeader>
          </Card>
          <Card className="bg-slate-900/60 border-slate-700">
            <CardHeader>
              <CardTitle className="text-sm font-semibold">Oda Listesi & Hızlı Oda Ekleme</CardTitle>
              <CardDescription className="text-xs text-slate-400">
                Odalarınızı birkaç saniyede ekleyin, bungalov isimlerinizi ve tiplerinizi düzenleyin.
              </CardDescription>
            </CardHeader>
          </Card>
          <Card className="bg-slate-900/60 border-slate-700">
            <CardHeader>
              <CardTitle className="text-sm font-semibold">Basit Raporlar</CardTitle>
              <CardDescription className="text-xs text-slate-400">
                Son 7 / 30 gün doluluk ve ciroyu görün, sezona hazır olun.
              </CardDescription>
            </CardHeader>
          </Card>
        </section>

        {/* 3 Adım Kurulum */}
        <section className="space-y-3">
          <h2 className="text-xl font-semibold">Kurulum 3 Adım</h2>
          <div className="grid md:grid-cols-3 gap-4 text-sm">
            <Card className="bg-slate-900/60 border-slate-700">
              <CardHeader>
                <CardTitle className="text-sm font-semibold">1. Oda ekleyin</CardTitle>
                <CardDescription className="text-xs text-slate-400">
                  Bungalov veya oda isimlerinizi sisteme tek seferde girin.
                </CardDescription>
              </CardHeader>
            </Card>
            <Card className="bg-slate-900/60 border-slate-700">
              <CardHeader>
                <CardTitle className="text-sm font-semibold">2. İlk rezervasyonu oluşturun</CardTitle>
                <CardDescription className="text-xs text-slate-400">
                  Bugün giriş / yarın çıkış ile test rezervasyonu oluşturun.
                </CardDescription>
              </CardHeader>
            </Card>
            <Card className="bg-slate-900/60 border-slate-700">
              <CardHeader>
                <CardTitle className="text-sm font-semibold">3. Takvimden yönetin</CardTitle>
                <CardDescription className="text-xs text-slate-400">
                  Tüm rezervasyonları takvim üzerinden yönetin, doluluğu takip edin.
                </CardDescription>
              </CardHeader>
            </Card>
          </div>
        </section>

        {/* Lead Form */}
        <section className="grid md:grid-cols-2 gap-6 items-start">
          <div className="space-y-3">
            <h2 className="text-xl font-semibold">Demo Talep Formu</h2>
            <p className="text-sm text-slate-300">
              Aşağıdaki formu doldurun, bölgenize göre (Kartepe, Sapanca vb.) sizi arayıp uygun paketi
              birlikte planlayalım.
            </p>
          </div>

          <Card className="bg-slate-900/80 border-slate-700">
            <CardContent className="pt-6 space-y-3">
              <form onSubmit={handleSubmit} className="space-y-3 text-sm">
                <div>
                  <Label htmlFor="full_name">Ad Soyad</Label>
                  <Input
                    id="full_name"
                    name="full_name"
                    value={form.full_name}
                    onChange={handleChange}
                    disabled={submitting}
                    className="bg-slate-950 border-slate-700 text-white"
                  />
                </div>
                <div>
                  <Label htmlFor="phone">Telefon</Label>
                  <Input
                    id="phone"
                    name="phone"
                    value={form.phone}
                    onChange={handleChange}
                    disabled={submitting}
                    className="bg-slate-950 border-slate-700 text-white"
                  />
                </div>
                <div>
                  <Label htmlFor="email">E-posta (opsiyonel)</Label>
                  <Input
                    id="email"
                    name="email"
                    type="email"
                    value={form.email}
                    onChange={handleChange}
                    disabled={submitting}
                    className="bg-slate-950 border-slate-700 text-white"
                  />
                </div>
                <div>
                  <Label htmlFor="property_name">Otel / Tesis Adı</Label>
                  <Input
                    id="property_name"
                    name="property_name"
                    value={form.property_name}
                    onChange={handleChange}
                    disabled={submitting}
                    className="bg-slate-950 border-slate-700 text-white"
                  />
                </div>
                <div>
                  <Label htmlFor="location">Bölge (Kartepe / Sapanca / Diğer)</Label>
                  <Input
                    id="location"
                    name="location"
                    value={form.location}
                    onChange={handleChange}
                    disabled={submitting}
                    className="bg-slate-950 border-slate-700 text-white"
                  />
                </div>
                <div>
                  <Label htmlFor="rooms_count">Oda Sayısı</Label>
                  <Input
                    id="rooms_count"
                    name="rooms_count"
                    type="number"
                    min={1}
                    max={200}
                    value={form.rooms_count}
                    onChange={handleChange}
                    disabled={submitting}
                    className="bg-slate-950 border-slate-700 text-white"
                  />
                </div>

                <Button
                  type="submit"
                  disabled={submitting}
                  className="w-full bg-emerald-500 hover:bg-emerald-600 text-black font-semibold mt-2"
                >
                  {submitting ? "Gönderiliyor..." : "Demo Talebi Gönder"}
                </Button>
              </form>
            </CardContent>
          </Card>
        </section>

        {/* Success Message */}
        {lastLead && (
          <section className="space-y-4">
            <Card className="bg-slate-900/80 border-slate-700">
              <CardHeader>
                <div className="flex items-center justify-between gap-2">
                  <CardTitle className="text-sm">Talebiniz alındı</CardTitle>
                  {lastLead.deduped && (
                    <span className="inline-flex items-center rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-300 border border-amber-500/30">
                      Daha önce alındı
                    </span>
                  )}
                </div>
                <CardDescription className="text-xs text-slate-400">
                  Aşağıdaki mesajı WhatsApp üzerinden de gönderebilirsiniz.
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="bg-slate-950/50 p-3 rounded-md border border-slate-700">
                  <pre className="text-xs text-slate-300 whitespace-pre-wrap font-mono">
                    {lastLead.message}
                  </pre>
                </div>
                <div className="flex gap-2 mt-3">
                  <Button
                    size="sm"
                    className="bg-green-600 hover:bg-green-700 text-white"
                    onClick={() => {
                      const phone = "+905555555555";
                      const text = encodeURIComponent(lastLead.message);
                      window.open(`https://wa.me/${phone}?text=${text}`, "_blank");
                    }}
                  >
                    WhatsApp'a Gönder
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="border-slate-600 text-slate-300 hover:bg-slate-800"
                    onClick={() => setLastLead(null)}
                  >
                    Kapat
                  </Button>
                </div>
              </CardContent>
            </Card>
          </section>
        )}
      </div>
    </div>
  );
};

export default PmsLiteLanding;
