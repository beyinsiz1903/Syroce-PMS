import React, { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { alertDialog } from '@/lib/dialogs';
import {
  Sparkles, Wrench, Wifi, Tv, Thermometer, Utensils, Wine, Beer, Shirt,
  Car, Bell, Heart, Package, MessageSquare, CheckCircle2, Loader2, Hotel,
  AlertTriangle,
} from "lucide-react";

const ICONS = {
  sparkles: Sparkles, wrench: Wrench, wifi: Wifi, tv: Tv, thermometer: Thermometer,
  utensils: Utensils, wine: Wine, beer: Beer, shirt: Shirt, car: Car, bell: Bell,
  heart: Heart, package: Package, message: MessageSquare, alert: AlertTriangle,
};

const LANGS = [
  { code: "tr", label: "Türkçe" },
  { code: "en", label: "English" },
  { code: "de", label: "Deutsch" },
  { code: "ru", label: "Русский" },
  { code: "ar", label: "العربية" },
];

const UI = {
  tr: { title: "Oda Talebi", room: "Oda", welcome: "Hoş geldiniz", pick: "Ne için talep oluşturuyorsunuz?",
        describe: "Detay / Açıklama", placeholder: "Kısaca talebinizi yazın...", priority: "Öncelik",
        low: "Düşük", normal: "Normal", high: "Yüksek", urgent: "Acil", submit: "Talebi Gönder",
        sent: "Talebiniz alındı!", sentDesc: "İlgili departmana iletildi, kısa sürede geri dönülecek.",
        newReq: "Yeni talep oluştur", name: "Adınız (opsiyonel)", phone: "Telefon (opsiyonel)",
        sending: "Gönderiliyor...", language: "Dil", back: "Geri", home: "Ana menü",
        errorTitle: "Talep açılamadı",
        loadError: "Yükleme hatası", sendError: "Gönderim hatası",
        conversation: "Mesajlar", you: "Siz", team: "Otel Ekibi",
        replyPlaceholder: "Bir mesaj yazın...", send: "Gönder", noMessages: "Henüz mesaj yok." },
  en: { title: "Room Request", room: "Room", welcome: "Welcome", pick: "What is your request about?",
        describe: "Details", placeholder: "Briefly describe your request...", priority: "Priority",
        low: "Low", normal: "Normal", high: "High", urgent: "Urgent", submit: "Submit Request",
        sent: "Request received!", sentDesc: "It has been forwarded to the right team. We'll get back to you shortly.",
        newReq: "Make another request", name: "Your name (optional)", phone: "Phone (optional)",
        sending: "Sending...", language: "Language", back: "Back", home: "Main menu",
        errorTitle: "Unable to open request",
        loadError: "Loading error", sendError: "Sending error",
        conversation: "Messages", you: "You", team: "Hotel Team",
        replyPlaceholder: "Write a message...", send: "Send", noMessages: "No messages yet." },
  de: { title: "Zimmeranfrage", room: "Zimmer", welcome: "Willkommen", pick: "Worum geht es?",
        describe: "Beschreibung", placeholder: "Beschreiben Sie Ihre Anfrage...", priority: "Priorität",
        low: "Niedrig", normal: "Normal", high: "Hoch", urgent: "Dringend", submit: "Anfrage senden",
        sent: "Anfrage erhalten!", sentDesc: "Wir haben sie an das Team weitergeleitet.",
        newReq: "Neue Anfrage", name: "Name (optional)", phone: "Telefon (optional)",
        sending: "Senden...", language: "Sprache", back: "Zurück", home: "Hauptmenü",
        errorTitle: "Anfrage konnte nicht geöffnet werden",
        loadError: "Ladefehler", sendError: "Sendefehler",
        conversation: "Nachrichten", you: "Sie", team: "Hotel-Team",
        replyPlaceholder: "Nachricht schreiben...", send: "Senden", noMessages: "Noch keine Nachrichten." },
  ru: { title: "Запрос из номера", room: "Номер", welcome: "Добро пожаловать", pick: "Что вас интересует?",
        describe: "Описание", placeholder: "Опишите ваш запрос...", priority: "Приоритет",
        low: "Низкий", normal: "Обычный", high: "Высокий", urgent: "Срочно", submit: "Отправить",
        sent: "Запрос принят!", sentDesc: "Мы передали его в нужный отдел.",
        newReq: "Новый запрос", name: "Имя (необяз.)", phone: "Телефон (необяз.)",
        sending: "Отправка...", language: "Язык", back: "Назад", home: "Главное меню",
        errorTitle: "Не удалось открыть запрос",
        loadError: "Ошибка загрузки", sendError: "Ошибка отправки",
        conversation: "Сообщения", you: "Вы", team: "Команда отеля",
        replyPlaceholder: "Напишите сообщение...", send: "Отправить", noMessages: "Сообщений пока нет." },
  ar: { title: "طلب من الغرفة", room: "غرفة", welcome: "أهلاً بك", pick: "ما هو طلبك؟",
        describe: "التفاصيل", placeholder: "صف طلبك...", priority: "الأولوية",
        low: "منخفض", normal: "عادي", high: "مرتفع", urgent: "عاجل", submit: "إرسال الطلب",
        sent: "تم استلام طلبك!", sentDesc: "تم تحويله إلى القسم المختص.",
        newReq: "طلب جديد", name: "الاسم (اختياري)", phone: "الهاتف (اختياري)",
        sending: "جارٍ الإرسال...", language: "اللغة", back: "رجوع", home: "القائمة الرئيسية",
        errorTitle: "تعذّر فتح الطلب",
        loadError: "خطأ في التحميل", sendError: "خطأ في الإرسال",
        conversation: "الرسائل", you: "أنت", team: "فريق الفندق",
        replyPlaceholder: "اكتب رسالة...", send: "إرسال", noMessages: "لا توجد رسائل بعد." },
};

const LOCALE = { tr: "tr-TR", en: "en-US", de: "de-DE", ru: "ru-RU", ar: "ar" };

function fmtGuestTime(iso, lang) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString(LOCALE[lang] || "tr-TR", {
      day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return "";
  }
}

/**
 * Misafir tarafı iki yönlü thread — BOOKING-SCOPED (backend belirler).
 * Mesajlar 15s'de bir (sekme görünürken) tazelenir. Personel adı backend'de
 * "Otel Ekibi" olarak maskelenir; burada da sender_type'a göre etiketlenir.
 *
 * `alwaysShow` true ise (talep gönderildikten sonra) thread + yanıt kutusu
 * her zaman görünür; aksi halde yalnızca mevcut mesaj varsa render edilir
 * (ziyarette devam eden konuşma).
 */
function GuestThread({ tenantId, roomId, token, t, lang, rtl, accent, alwaysShow }) {
  const [messages, setMessages] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [reply, setReply] = useState("");
  const [sending, setSending] = useState(false);
  const mountedRef = useRef(true);
  const scrollRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(
        `/public/room-qr/${tenantId}/${roomId}/thread`,
        { params: { t: token } },
      );
      if (!mountedRef.current) return;
      setMessages(r.data?.messages || []);
    } catch {
      /* thread opsiyonel — sessiz geç */
    } finally {
      if (mountedRef.current) setLoaded(true);
    }
  }, [tenantId, roomId]);

  useEffect(() => {
    mountedRef.current = true;
    load();
    let timer = null;
    const start = () => {
      if (timer === null && !document.hidden) timer = setInterval(load, 15000);
    };
    const stop = () => {
      if (timer !== null) { clearInterval(timer); timer = null; }
    };
    const onVis = () => {
      if (document.hidden) { stop(); } else { load(); start(); }
    };
    start();
    document.addEventListener("visibilitychange", onVis);
    return () => {
      mountedRef.current = false;
      stop();
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [load]);

  useEffect(() => {
    if (!scrollRef.current) return;
    const n = scrollRef.current;
    requestAnimationFrame(() => { n.scrollTop = n.scrollHeight; });
  }, [messages]);

  const send = async () => {
    const text = reply.trim();
    if (!text || sending) return;
    setSending(true);
    try {
      await axios.post(
        `/public/room-qr/${tenantId}/${roomId}/thread/message`,
        { body: text },
        { params: { t: token } },
      );
      if (!mountedRef.current) return;
      setReply("");
      load();
    } catch (e) {
      alertDialog({ message: e.response?.data?.detail || t.sendError });
    } finally {
      if (mountedRef.current) setSending(false);
    }
  };

  if (!alwaysShow && (!loaded || messages.length === 0)) return null;

  return (
    <Card className="shadow-xl mt-4" data-testid="guest-thread-card">
      <CardHeader>
        <CardTitle className="text-lg">{t.conversation}</CardTitle>
      </CardHeader>
      <CardContent>
        <div ref={scrollRef} className="max-h-72 overflow-y-auto space-y-2 mb-3" data-testid="guest-thread-messages">
          {messages.length === 0 ? (
            <div className="text-center text-sm text-gray-500 py-6">{t.noMessages}</div>
          ) : (
            messages.map((m) => {
              const isGuest = m.sender_type === "guest";
              const alignEnd = rtl ? !isGuest : isGuest;
              return (
                <div key={m.id} className={`flex ${alignEnd ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${isGuest ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-900"}`}>
                    <div className="text-[11px] font-medium opacity-80 mb-0.5">
                      {isGuest ? t.you : t.team}
                    </div>
                    <div className="whitespace-pre-wrap break-words">{m.body}</div>
                    <div className="text-[10px] opacity-60 mt-0.5">{fmtGuestTime(m.created_at, lang)}</div>
                  </div>
                </div>
              );
            })
          )}
        </div>
        <div className="flex items-end gap-2">
          <Textarea
            value={reply}
            onChange={(e) => setReply(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
            placeholder={t.replyPlaceholder}
            rows={2}
            className="resize-none"
            data-testid="input-guest-reply"
          />
          <Button
            onClick={send}
            disabled={!reply.trim() || sending}
            className="text-white shrink-0"
            style={{ background: accent }}
            data-testid="button-guest-send"
          >
            {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : t.send}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function RoomRequestPage() {
  const { tenantId, roomId } = useParams();
  const [params] = useSearchParams();
  const token = params.get("t");

  const [lang, setLang] = useState(() => {
    const nav = (navigator.language || "tr").slice(0, 2);
    return UI[nav] ? nav : "tr";
  });
  const t = UI[lang] || UI.tr;
  const rtl = lang === "ar";

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [meta, setMeta] = useState(null);
  const [category, setCategory] = useState(null);
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("normal");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const r = await axios.get(`/public/room-qr/${tenantId}/${roomId}`, { params: { t: token } });
        setMeta(r.data);
        if (r.data.guest_name) setName(r.data.guest_name);
      } catch (e) {
        setError(e.response?.data?.detail || t.loadError);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [tenantId, roomId]);

  const submit = async () => {
    if (!category || !description.trim()) return;
    setSubmitting(true);
    try {
      await axios.post(`/public/room-qr/${tenantId}/${roomId}/submit`, {
        category, description, priority, language: lang,
        guest_name: name.trim() || undefined,
        guest_phone: phone.trim() || undefined,
      }, { params: { t: token } });
      setDone(true);
    } catch (e) {
      alertDialog({ message: e.response?.data?.detail || t.sendError });
    } finally {
      setSubmitting(false);
    }
  };

  const resetForNew = () => {
    setDone(false); setCategory(null); setDescription(""); setPriority("normal");
  };

  const goHome = () => {
    setDone(false); setCategory(null); setDescription(""); setPriority("normal");
    if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "smooth" });
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-slate-200 dark:bg-none dark:bg-background">
        <Loader2 className="w-10 h-10 animate-spin text-slate-400" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-slate-50">
        <Card className="max-w-md w-full">
          <CardContent className="p-8 text-center">
            <div className="flex justify-center mb-4"><AlertTriangle className="w-14 h-14 text-red-600" /></div>
            <h2 className="text-xl font-semibold mb-2">{t.errorTitle}</h2>
            <p className="text-gray-600 text-sm">{error}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const accent = meta?.primary_color || "#0ea5e9";

  return (
    <div dir={rtl ? "rtl" : "ltr"} className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-200 dark:bg-none dark:bg-background pb-24">
      {/* Header */}
      <div className="text-white p-6 pb-10 rounded-b-3xl shadow-lg"
           style={{ background: `linear-gradient(135deg, ${accent} 0%, ${accent}dd 100%)` }}>
        <div className="max-w-2xl mx-auto">
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center gap-3">
              {meta.hotel_logo ? (
                <img src={meta.hotel_logo} alt="" className="w-12 h-12 rounded-xl bg-white/20 p-2" />
              ) : (
                <Hotel className="w-12 h-12 bg-white/20 p-2 rounded-xl" />
              )}
              <div>
                <div className="text-xs opacity-80">{t.welcome}</div>
                <div className="font-bold text-lg">{meta.hotel_name}</div>
              </div>
            </div>
            <Select value={lang} onValueChange={setLang}>
              <SelectTrigger className="w-28 bg-white/20 border-white/30 text-white">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LANGS.map((l) => <SelectItem key={l.code} value={l.code}>{l.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="bg-white/15 backdrop-blur p-4 rounded-2xl">
            <div className="text-xs opacity-80 uppercase tracking-wide">{t.room}</div>
            <div className="text-4xl font-bold">{meta.room_number}</div>
            {meta.room_type && <div className="text-sm opacity-80 mt-1">{meta.room_type}</div>}
          </div>
        </div>
      </div>

      <div className="max-w-2xl mx-auto px-4 -mt-4">
        {done ? (
          <Card className="shadow-xl">
            <CardContent className="p-10 text-center">
              <div className="w-20 h-20 mx-auto rounded-full bg-emerald-100 flex items-center justify-center mb-4">
                <CheckCircle2 className="w-12 h-12 text-emerald-600" />
              </div>
              <h2 className="text-2xl font-bold mb-2">{t.sent}</h2>
              <p className="text-gray-600 mb-6">{t.sentDesc}</p>
              <div className="space-y-3">
                <Button onClick={resetForNew} className="w-full text-white" style={{ background: accent }}>{t.newReq}</Button>
                <Button onClick={goHome} variant="outline" className="w-full">{t.home}</Button>
              </div>
            </CardContent>
          </Card>
        ) : !category ? (
          <Card className="shadow-xl">
            <CardHeader>
              <CardTitle>{t.pick}</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-3">
              {meta.categories.map((c) => {
                const Icon = ICONS[c.icon] || MessageSquare;
                const label = c.labels[lang] || c.labels.en || c.id;
                return (
                  <button
                    key={c.id}
                    onClick={() => { setCategory(c.id); setPriority(c.default_priority || "normal"); }}
                    className="flex flex-col items-center gap-2 p-4 rounded-xl border-2 border-slate-200 hover:border-slate-400 hover:bg-slate-50 transition-all active:scale-95"
                  >
                    <div className="w-12 h-12 rounded-full flex items-center justify-center"
                         style={{ background: `${accent}15`, color: accent }}>
                      <Icon className="w-6 h-6" />
                    </div>
                    <span className="text-sm font-medium text-center">{label}</span>
                  </button>
                );
              })}
            </CardContent>
          </Card>
        ) : (
          <Card className="shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-lg">
                {meta.categories.find((c) => c.id === category)?.labels[lang] || category}
              </CardTitle>
              <Button variant="ghost" size="sm" onClick={() => setCategory(null)}>{t.back}</Button>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label>{t.describe}</Label>
                <Textarea
                  value={description} onChange={(e) => setDescription(e.target.value)}
                  placeholder={t.placeholder} rows={4} className="mt-1"
                />
              </div>
              <div>
                <Label>{t.priority}</Label>
                <Select value={priority} onValueChange={setPriority}>
                  <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="low">{t.low}</SelectItem>
                    <SelectItem value="normal">{t.normal}</SelectItem>
                    <SelectItem value="high">{t.high}</SelectItem>
                    <SelectItem value="urgent">{t.urgent}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>{t.name}</Label>
                  <Input value={name} onChange={(e) => setName(e.target.value)} className="mt-1" />
                </div>
                <div>
                  <Label>{t.phone}</Label>
                  <Input value={phone} onChange={(e) => setPhone(e.target.value)} className="mt-1" />
                </div>
              </div>
              <Button
                onClick={submit}
                disabled={!description.trim() || submitting}
                className="w-full text-white"
                style={{ background: accent }}
              >
                {submitting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                {submitting ? t.sending : t.submit}
              </Button>
            </CardContent>
          </Card>
        )}

        <GuestThread
          tenantId={tenantId}
          roomId={roomId}
          token={token}
          t={t}
          lang={lang}
          rtl={rtl}
          accent={accent}
          alwaysShow={done}
        />
      </div>
    </div>
  );
}
