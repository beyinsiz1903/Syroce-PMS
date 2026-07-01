import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Globe, Save, RefreshCw, Plus, Trash2, FileText, Phone, HelpCircle, LayoutGrid,
} from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { PageHeader } from '@/components/ui/page-header';

import { mergeLandingContent } from '@/config/landingContentDefaults';

// Karakter sinirlari backend SiteContent modeliyle birebir ayni (site_content.py).
const LIMITS = {
  brandName: 80,
  hero: { badge: 120, titlePre: 80, titleAccent: 80, titlePost: 80, description: 600, descriptionAccent: 160 },
  contact: { phone: 60, email: 160, address: 200 },
  solution: { title: 120, desc: 400 },
  faq: { q: 200, a: 1000 },
  maxSolutions: 12,
  maxFaqs: 20,
};

const hasMarkup = (v) => typeof v === 'string' && (v.includes('<') || v.includes('>'));

function collectStrings(obj, acc = []) {
  if (typeof obj === 'string') { acc.push(obj); return acc; }
  if (Array.isArray(obj)) { obj.forEach((x) => collectStrings(x, acc)); return acc; }
  if (obj && typeof obj === 'object') { Object.values(obj).forEach((x) => collectStrings(x, acc)); return acc; }
  return acc;
}

const SiteContentEditor = () => {
  const [form, setForm] = useState(() => mergeLandingContent(null));
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get('/site-content');
      setForm(mergeLandingContent(res.data));
    } catch (err) {
      setForm(mergeLandingContent(null));
      toast.error('Icerik yuklenemedi, varsayilanlar gosteriliyor.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const setTop = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));
  const setNested = (group, key, value) =>
    setForm((prev) => ({ ...prev, [group]: { ...prev[group], [key]: value } }));

  const setSolution = (i, key, value) =>
    setForm((prev) => ({
      ...prev,
      solutions: prev.solutions.map((s, idx) => (idx === i ? { ...s, [key]: value } : s)),
    }));
  const addSolution = () =>
    setForm((prev) =>
      prev.solutions.length >= LIMITS.maxSolutions
        ? prev
        : { ...prev, solutions: [...prev.solutions, { title: '', desc: '' }] },
    );
  const removeSolution = (i) =>
    setForm((prev) => ({ ...prev, solutions: prev.solutions.filter((_, idx) => idx !== i) }));

  const setFaq = (i, key, value) =>
    setForm((prev) => ({
      ...prev,
      faqs: prev.faqs.map((f, idx) => (idx === i ? { ...f, [key]: value } : f)),
    }));
  const addFaq = () =>
    setForm((prev) =>
      prev.faqs.length >= LIMITS.maxFaqs ? prev : { ...prev, faqs: [...prev.faqs, { q: '', a: '' }] },
    );
  const removeFaq = (i) =>
    setForm((prev) => ({ ...prev, faqs: prev.faqs.filter((_, idx) => idx !== i) }));

  const handleSave = async () => {
    // Backend duz-metin korumasinin istemci tarafi aynasi (anlik geri bildirim).
    if (collectStrings(form).some(hasMarkup)) {
      toast.error('Metin alanlarinda < veya > karakteri kullanilamaz.');
      return;
    }
    const payload = {
      brandName: form.brandName,
      hero: form.hero,
      contact: form.contact,
      solutions: form.solutions.filter((s) => (s.title || '').trim() || (s.desc || '').trim()),
      faqs: form.faqs.filter((f) => (f.q || '').trim() || (f.a || '').trim()),
    };
    setSaving(true);
    try {
      await axios.put('/admin/site-content', payload);
      toast.success('Landing icerigi kaydedildi.');
      setForm(mergeLandingContent(payload));
    } catch (err) {
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Kaydedilemedi. Lutfen alanlari kontrol edin.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-4 sm:p-6">
      <PageHeader
        icon={Globe}
        title="Landing Icerigi"
        subtitle="Herkese acik tanitim sayfasinin metinlerini buradan duzenleyin. Bos birakilan alanlar varsayilana doner."
        actions={
          <>
            <Button variant="outline" onClick={load} disabled={loading || saving}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Yenile
            </Button>
            <Button onClick={handleSave} disabled={loading || saving}>
              <Save className="mr-2 h-4 w-4" />
              {saving ? 'Kaydediliyor...' : 'Kaydet'}
            </Button>
          </>
        }
      />

      {/* Marka */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Globe className="h-4 w-4 text-slate-500" /> Marka
          </CardTitle>
          <CardDescription>Sayfa basligi, ust menu ve alt bilgide gosterilen marka adi.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-1.5">
            <Label htmlFor="brandName">Marka Adi</Label>
            <Input
              id="brandName"
              value={form.brandName}
              maxLength={LIMITS.brandName}
              onChange={(e) => setTop('brandName', e.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      {/* Hero */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileText className="h-4 w-4 text-slate-500" /> Hero (Ust Bolum)
          </CardTitle>
          <CardDescription>Sayfanin en ustundeki rozet, ana baslik ve aciklama.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="hero-badge">Rozet</Label>
            <Input
              id="hero-badge"
              value={form.hero.badge}
              maxLength={LIMITS.hero.badge}
              onChange={(e) => setNested('hero', 'badge', e.target.value)}
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="hero-pre">Baslik (1. kisim)</Label>
              <Input
                id="hero-pre"
                value={form.hero.titlePre}
                maxLength={LIMITS.hero.titlePre}
                onChange={(e) => setNested('hero', 'titlePre', e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="hero-accent">Baslik (vurgulu)</Label>
              <Input
                id="hero-accent"
                value={form.hero.titleAccent}
                maxLength={LIMITS.hero.titleAccent}
                onChange={(e) => setNested('hero', 'titleAccent', e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="hero-post">Baslik (son kisim)</Label>
              <Input
                id="hero-post"
                value={form.hero.titlePost}
                maxLength={LIMITS.hero.titlePost}
                onChange={(e) => setNested('hero', 'titlePost', e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="hero-desc">Aciklama</Label>
            <Textarea
              id="hero-desc"
              rows={3}
              value={form.hero.description}
              maxLength={LIMITS.hero.description}
              onChange={(e) => setNested('hero', 'description', e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="hero-desc-accent">Aciklama (vurgulu son)</Label>
            <Input
              id="hero-desc-accent"
              value={form.hero.descriptionAccent}
              maxLength={LIMITS.hero.descriptionAccent}
              onChange={(e) => setNested('hero', 'descriptionAccent', e.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      {/* Iletisim */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Phone className="h-4 w-4 text-slate-500" /> Iletisim
          </CardTitle>
          <CardDescription>Iletisim bolumunde gosterilen telefon, e-posta ve adres.</CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor="c-phone">Telefon</Label>
            <Input
              id="c-phone"
              value={form.contact.phone}
              maxLength={LIMITS.contact.phone}
              onChange={(e) => setNested('contact', 'phone', e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="c-email">E-posta</Label>
            <Input
              id="c-email"
              value={form.contact.email}
              maxLength={LIMITS.contact.email}
              onChange={(e) => setNested('contact', 'email', e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="c-address">Adres</Label>
            <Input
              id="c-address"
              value={form.contact.address}
              maxLength={LIMITS.contact.address}
              onChange={(e) => setNested('contact', 'address', e.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      {/* Cozum Kartlari */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <LayoutGrid className="h-4 w-4 text-slate-500" /> Cozum Kartlari
          </CardTitle>
          <CardDescription>
            "Cozumler" bolumundeki kartlar (en fazla {LIMITS.maxSolutions}). Ikonlar sabittir.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {form.solutions.map((s, i) => (
            <div key={i} className="rounded-lg border border-slate-200 p-4">
              <div className="mb-3 flex items-center justify-between">
                <span className="text-sm font-medium text-slate-700">Kart {i + 1}</span>
                <Button variant="ghost" size="sm" onClick={() => removeSolution(i)}>
                  <Trash2 className="h-4 w-4 text-rose-600" />
                </Button>
              </div>
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label htmlFor={`sol-title-${i}`}>Baslik</Label>
                  <Input
                    id={`sol-title-${i}`}
                    value={s.title}
                    maxLength={LIMITS.solution.title}
                    onChange={(e) => setSolution(i, 'title', e.target.value)}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor={`sol-desc-${i}`}>Aciklama</Label>
                  <Textarea
                    id={`sol-desc-${i}`}
                    rows={2}
                    value={s.desc}
                    maxLength={LIMITS.solution.desc}
                    onChange={(e) => setSolution(i, 'desc', e.target.value)}
                  />
                </div>
              </div>
            </div>
          ))}
          <Button
            variant="outline"
            onClick={addSolution}
            disabled={form.solutions.length >= LIMITS.maxSolutions}
          >
            <Plus className="mr-2 h-4 w-4" />
            Kart Ekle
          </Button>
        </CardContent>
      </Card>

      {/* SSS */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <HelpCircle className="h-4 w-4 text-slate-500" /> Sik Sorulan Sorular
          </CardTitle>
          <CardDescription>SSS bolumundeki soru-cevaplar (en fazla {LIMITS.maxFaqs}).</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {form.faqs.map((f, i) => (
            <div key={i} className="rounded-lg border border-slate-200 p-4">
              <div className="mb-3 flex items-center justify-between">
                <span className="text-sm font-medium text-slate-700">Soru {i + 1}</span>
                <Button variant="ghost" size="sm" onClick={() => removeFaq(i)}>
                  <Trash2 className="h-4 w-4 text-rose-600" />
                </Button>
              </div>
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label htmlFor={`faq-q-${i}`}>Soru</Label>
                  <Input
                    id={`faq-q-${i}`}
                    value={f.q}
                    maxLength={LIMITS.faq.q}
                    onChange={(e) => setFaq(i, 'q', e.target.value)}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor={`faq-a-${i}`}>Cevap</Label>
                  <Textarea
                    id={`faq-a-${i}`}
                    rows={3}
                    value={f.a}
                    maxLength={LIMITS.faq.a}
                    onChange={(e) => setFaq(i, 'a', e.target.value)}
                  />
                </div>
              </div>
            </div>
          ))}
          <Button variant="outline" onClick={addFaq} disabled={form.faqs.length >= LIMITS.maxFaqs}>
            <Plus className="mr-2 h-4 w-4" />
            Soru Ekle
          </Button>
        </CardContent>
      </Card>
    </div>
  );
};

export default SiteContentEditor;
