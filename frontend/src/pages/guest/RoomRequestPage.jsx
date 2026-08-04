import React, { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { alertDialog } from '@/lib/dialogs';
import { Loader2, Hotel, AlertTriangle, CheckCircle2, Minus, Plus, MessageSquare } from "lucide-react";
import { ICONS, LANGS, UI, LOCALE, DEPT_LABELS, DEPT_ICONS } from "./constants";
import { useGuestCart } from "./hooks/useGuestCart";

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
        { headers: { "X-Guest-Session": token } },
      );
      if (!mountedRef.current) return;
      setMessages(r.data?.messages || []);
    } catch {
      // thread optional
    } finally {
      if (mountedRef.current) setLoaded(true);
    }
  }, [tenantId, roomId, token]);

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
        { headers: { "X-Guest-Session": token } },
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

// ----------------------------------------------------------------------
// SERVICE INPUT COMPONENT
// ----------------------------------------------------------------------
function ServiceInput({ service, cartItem, onChange, t, accent }) {
  const type = service.input_type;
  
  if (type === "one_tap") {
    const isSelected = !!cartItem;
    return (
      <Button 
        variant={isSelected ? "destructive" : "outline"}
        onClick={() => isSelected ? onChange(null) : onChange({})}
        className="w-full mt-2"
        style={isSelected ? {} : { color: accent, borderColor: accent }}
      >
        {isSelected ? t.remove : t.addMore}
      </Button>
    );
  }

  if (type === "quantity") {
    const qty = cartItem?.value?.quantity || 0;
    return (
      <div className="flex items-center justify-between mt-2 bg-slate-50 rounded-lg p-1">
        <Button 
          variant="ghost" 
          size="icon" 
          onClick={() => onChange({ value: { quantity: qty - 1 } })}
          disabled={qty === 0}
          className="h-8 w-8 min-w-[44px] min-h-[44px]"
        >
          <Minus className="w-4 h-4" />
        </Button>
        <span className="font-semibold text-base min-w-[32px] text-center" data-testid={`qty-${service.service_code}`}>{qty}</span>
        <Button 
          variant="ghost" 
          size="icon" 
          onClick={() => onChange({ value: { quantity: qty + 1 } })}
          className="h-8 w-8 min-w-[44px] min-h-[44px]"
          style={{ color: accent }}
        >
          <Plus className="w-4 h-4" />
        </Button>
      </div>
    );
  }

  if (type === "single_choice") {
    const opts = service.input_config?.options || [];
    const selected = cartItem?.value?.selected_options?.[0] || "";
    return (
      <div className="mt-2 flex flex-col gap-2">
        <Select value={selected} onValueChange={(val) => onChange({ value: { selected_options: [val] } })}>
          <SelectTrigger className="w-full min-h-[44px]"><SelectValue placeholder={t.selectOption} /></SelectTrigger>
          <SelectContent>
            {opts.map(o => (
              <SelectItem key={o.code} value={o.code}>{o.label || o.code}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        {cartItem && (
          <Button variant="ghost" size="sm" onClick={() => onChange(null)} className="text-red-500 self-start p-0 h-auto min-h-[44px]">
            {t.remove}
          </Button>
        )}
      </div>
    );
  }

  if (type === "multi_choice") {
    const opts = service.input_config?.options || [];
    const selected = cartItem?.value?.selected_options || [];
    return (
      <div className="mt-2 flex flex-col gap-2">
        {opts.map(o => {
          const checked = selected.includes(o.code);
          return (
            <label key={o.code} className="flex items-center gap-2 min-h-[44px] cursor-pointer">
              <input 
                type="checkbox" 
                checked={checked} 
                onChange={(e) => {
                  const newSel = e.target.checked ? [...selected, o.code] : selected.filter(x => x !== o.code);
                  if (newSel.length === 0) onChange(null);
                  else onChange({ value: { selected_options: newSel } });
                }}
                className="w-5 h-5 rounded border-slate-300"
                style={{ accentColor: accent }}
              />
              <span className="text-sm">{o.label || o.code}</span>
            </label>
          );
        })}
      </div>
    );
  }

  if (type === "date" || type === "time" || type === "datetime") {
    const key = `${type}_value`;
    const val = cartItem?.value?.[key] || "";
    let inputType = "date";
    if (type === "time") inputType = "time";
    if (type === "datetime") inputType = "datetime-local";

    return (
      <div className="mt-2 flex flex-col gap-2">
        <Input 
          type={inputType}
          value={val}
          onChange={(e) => {
            if (!e.target.value) onChange(null);
            else onChange({ value: { [key]: e.target.value } });
          }}
          className="min-h-[44px]"
        />
        {cartItem && (
          <Button variant="ghost" size="sm" onClick={() => onChange(null)} className="text-red-500 self-start p-0 h-auto min-h-[44px]">
            {t.remove}
          </Button>
        )}
      </div>
    );
  }

  return <div className="mt-2 text-xs text-red-500">{t.unsupportedInput}</div>;
}


// ----------------------------------------------------------------------
// MAIN EXPORT
// ----------------------------------------------------------------------
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

  // Core mode & views
  const [mode, setMode] = useState("loading"); // loading, catalogue, legacy, unavailable, error
  const [view, setView] = useState("departments"); // departments, services, review, success
  
  // Data
  const [meta, setMeta] = useState(null);
  const [guestSession, setGuestSession] = useState(null);
  const [catalogueData, setCatalogueData] = useState({ departments: [], services: [] });
  const [selectedDeptCode, setSelectedDeptCode] = useState(null);

  // Cart
  const cartState = useGuestCart();

  // Legacy fallback states
  const [legacyCategory, setLegacyCategory] = useState(null);
  const [legacyDescription, setLegacyDescription] = useState("");
  const [legacyPriority, setLegacyPriority] = useState("normal");

  // Shared form
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");

  const loadData = useCallback(async () => {
    setMode("loading");
    try {
      const metaRes = await axios.get(`/public/room-qr/${tenantId}/${roomId}`, { params: { t: token } });
      setMeta(metaRes.data);

      let sessionStr = null;
      try {
        const sessionRes = await axios.post(`/public/room-qr/${tenantId}/${roomId}/session`, null, { params: { t: token } });
        sessionStr = sessionRes.data.session_token;
        setGuestSession(sessionStr);
      } catch (sessionErr) {
        const status = sessionErr.response?.status;
        if (status === 401 || status === 403 || status === 410) {
          setMode("unavailable");
          return;
        } else if (status === 429) {
          setSubmitError(t.rateLimit);
          setMode("error");
          return;
        }
        throw sessionErr; 
      }

      // Fetch catalogue
      try {
        const catRes = await axios.get(`/public/room-qr/${tenantId}/${roomId}/catalogue`, {
          params: { lang },
          headers: { "X-Guest-Session": sessionStr }
        });
        
        if (catRes.status === 200) {
          if (!catRes.data?.departments || !catRes.data?.services) {
             throw new Error("Malformed catalogue");
          }
          setCatalogueData(catRes.data);
          setMode("catalogue");
        }
      } catch (catErr) {
        const status = catErr.response?.status;
        if (status === 404) {
          // Exact 404 means dynamic catalogue endpoint not implemented/available => fallback to legacy
          setMode("legacy");
        } else if (status === 401 || status === 403) {
          setMode("unavailable");
        } else if (status === 429) {
          setSubmitError(t.rateLimit);
          setMode("error");
        } else if (status >= 500 || !catErr.response) {
          setSubmitError(t.networkError || "Network error");
          setMode("error");
        } else {
          // Malformed 200 or other errors
          setSubmitError(t.loadError);
          setMode("error");
        }
      }

    } catch (e) {
       const status = e.response?.status;
       if (status === 401 || status === 403 || status === 410) {
         setMode("unavailable");
       } else if (status === 429) {
         setSubmitError(t.rateLimit);
         setMode("error");
       } else {
         setSubmitError(t.networkError || "Network error");
         setMode("error");
       }
    }
  }, [tenantId, roomId, token, lang, t]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const submitLegacy = async () => {
    if (!legacyCategory || submitting || !guestSession) return;
    setSubmitting(true);
    setSubmitError("");
    try {
      const selectedCat = meta.categories.find(c => c.id === legacyCategory);
      const catLabel = selectedCat?.labels[lang] || selectedCat?.labels.en || legacyCategory;
      const finalDesc = legacyDescription.trim() || catLabel;

      await axios.post(`/public/room-qr/${tenantId}/${roomId}/submit`, {
        category: legacyCategory, description: finalDesc, priority: legacyPriority, language: lang,
        guest_name: name.trim() || undefined,
        guest_phone: phone.trim() || undefined,
      }, { headers: { "X-Guest-Session": guestSession } });
      setView("success");
    } catch (e) {
      handleSubmitError(e);
    } finally {
      setSubmitting(false);
    }
  };

  const submitStructured = async () => {
    if (cartState.cart.length === 0 || submitting || !guestSession) return;
    setSubmitting(true);
    setSubmitError("");

    const key = cartState.getOrGenerateKey();
    const payloadItems = cartState.cart.map(c => {
      return {
        service_code: c.service_code,
        value: c.value,
        note: c.note?.trim() || undefined
      };
    });

    const payload = {
      language: lang,
      idempotency_key: key,
      items: payloadItems
    };

    if (name.trim()) payload.guest_name = name.trim();
    if (phone.trim()) payload.guest_phone = phone.trim();

    try {
      await axios.post(`/public/room-qr/${tenantId}/${roomId}/submit`, payload, {
        headers: { "X-Guest-Session": guestSession }
      });
      cartState.clearCart();
      setView("success");
    } catch (e) {
      handleSubmitError(e);
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmitError = (e) => {
    const status = e.response?.status;
    if (status === 401 || status === 403 || status === 410) {
      setMode("unavailable");
      setGuestSession(null);
    } else if (status === 409) {
      setSubmitError(t.conflictError);
      alertDialog({ message: t.conflictError });
    } else if (status === 429) {
      setSubmitError(t.rateLimit);
      alertDialog({ message: t.rateLimit });
    } else {
      const detail = e.response?.data?.detail || t.sendError;
      setSubmitError(detail);
      alertDialog({ message: detail });
    }
  };

  const resetFlow = () => {
    setView("departments");
    setSelectedDeptCode(null);
    setLegacyCategory(null);
    setLegacyDescription("");
    setLegacyPriority("normal");
    setSubmitError("");
    if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const accent = meta?.primary_color || "#0ea5e9";

  if (mode === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <Loader2 className="w-10 h-10 animate-spin text-slate-400" />
      </div>
    );
  }

  if (mode === "unavailable") {
    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-slate-50">
        <Card className="max-w-md w-full shadow-xl">
          <CardContent className="p-8 text-center">
            <div className="flex justify-center mb-4"><AlertTriangle className="w-14 h-14 text-slate-400" /></div>
            <h2 className="text-xl font-semibold mb-2">{t.unavailableTitle}</h2>
            <p className="text-gray-600 text-sm">{t.unavailableDesc}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (mode === "error") {
    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-slate-50">
        <Card className="max-w-md w-full shadow-xl">
          <CardContent className="p-8 text-center space-y-4">
            <div className="flex justify-center mb-4"><AlertTriangle className="w-14 h-14 text-red-600" /></div>
            <h2 className="text-xl font-semibold mb-2">{t.errorTitle}</h2>
            <p className="text-gray-600 text-sm">{submitError || t.loadError}</p>
            <Button onClick={loadData} className="w-full mt-4">{t.tryAgain}</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Common Header
  const renderHeader = () => (
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
            <SelectTrigger className="w-28 bg-white/20 border-white/30 text-white min-h-[44px]">
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
  );

  // Success View (Shared)
  if (view === "success") {
    return (
      <div dir={rtl ? "rtl" : "ltr"} className="min-h-screen bg-slate-50 pb-24">
        {renderHeader()}
        <div className="max-w-2xl mx-auto px-4 -mt-4">
          <Card className="shadow-xl">
            <CardContent className="p-10 text-center">
              <div className="w-20 h-20 mx-auto rounded-full bg-emerald-100 flex items-center justify-center mb-4">
                <CheckCircle2 className="w-12 h-12 text-emerald-600" />
              </div>
              <h2 className="text-2xl font-bold mb-2">{t.sent}</h2>
              <p className="text-gray-600 mb-6">{mode === "catalogue" ? t.structuredSentDesc : t.sentDesc}</p>
              <div className="space-y-3">
                <Button onClick={resetFlow} className="w-full text-white min-h-[44px]" style={{ background: accent }}>{t.newReq}</Button>
              </div>
            </CardContent>
          </Card>
          <GuestThread tenantId={tenantId} roomId={roomId} token={guestSession} t={t} lang={lang} rtl={rtl} accent={accent} alwaysShow={true} />
        </div>
      </div>
    );
  }

  // Legacy Mode Rendering
  if (mode === "legacy") {
    return (
      <div dir={rtl ? "rtl" : "ltr"} className="min-h-screen bg-slate-50 pb-24">
        {renderHeader()}
        <div className="max-w-2xl mx-auto px-4 -mt-4">
          {!selectedDeptCode ? (
             <Card className="shadow-xl">
               <CardHeader><CardTitle>{t.pick}</CardTitle></CardHeader>
               <CardContent className="grid grid-cols-2 md:grid-cols-3 gap-3">
                 {[...new Set(meta.categories.map(c => c.department))].map(dept => {
                   const Icon = DEPT_ICONS[dept] || MessageSquare;
                   const label = (DEPT_LABELS[lang] || DEPT_LABELS.tr)[dept] || dept;
                   return (
                     <button key={dept} onClick={() => setSelectedDeptCode(dept)} className="flex flex-col items-center gap-3 p-4 rounded-xl border-2 border-slate-200 hover:border-slate-400 min-h-[44px]">
                       <div className="w-14 h-14 rounded-full flex items-center justify-center" style={{ background: `${accent}15`, color: accent }}>
                         <Icon className="w-7 h-7" />
                       </div>
                       <span className="text-sm font-semibold text-center">{label}</span>
                     </button>
                   );
                 })}
               </CardContent>
             </Card>
          ) : !legacyCategory ? (
             <Card className="shadow-xl">
               <CardHeader className="flex flex-row items-center justify-between pb-2 border-b">
                 <CardTitle className="text-lg">{(DEPT_LABELS[lang] || DEPT_LABELS.tr)[selectedDeptCode] || selectedDeptCode}</CardTitle>
                 <Button variant="ghost" size="sm" onClick={() => setSelectedDeptCode(null)} className="min-h-[44px]">{t.back}</Button>
               </CardHeader>
               <CardContent className="grid grid-cols-2 gap-3 pt-4">
                 {meta.categories.filter(c => c.department === selectedDeptCode).map(c => {
                   const Icon = ICONS[c.icon] || MessageSquare;
                   const label = c.labels[lang] || c.labels.en || c.id;
                   return (
                     <button key={c.id} onClick={() => { setLegacyCategory(c.id); setLegacyPriority(c.default_priority || "normal"); }} className="flex flex-col items-center gap-2 p-3 rounded-xl border-2 border-slate-100 min-h-[44px]">
                       <div className="w-10 h-10 rounded-full flex items-center justify-center bg-slate-100"><Icon className="w-5 h-5 text-slate-600"/></div>
                       <span className="text-sm font-medium text-center">{label}</span>
                     </button>
                   );
                 })}
               </CardContent>
             </Card>
          ) : (
             <Card className="shadow-xl">
               <CardHeader className="flex flex-row items-center justify-between">
                 <CardTitle className="text-lg">{meta.categories.find(c => c.id === legacyCategory)?.labels[lang] || legacyCategory}</CardTitle>
                 <Button variant="ghost" size="sm" onClick={() => setLegacyCategory(null)} className="min-h-[44px]">{t.back}</Button>
               </CardHeader>
               <CardContent className="space-y-4">
                 <div>
                   <Label>{t.describe}</Label>
                   <Textarea value={legacyDescription} onChange={e => setLegacyDescription(e.target.value)} placeholder={t.placeholder} className="mt-1" />
                 </div>
                 <div>
                   <Label>{t.priority}</Label>
                   <Select value={legacyPriority} onValueChange={setLegacyPriority}>
                     <SelectTrigger className="mt-1 min-h-[44px]"><SelectValue /></SelectTrigger>
                     <SelectContent>
                       <SelectItem value="low">{t.low}</SelectItem>
                       <SelectItem value="normal">{t.normal}</SelectItem>
                       <SelectItem value="high">{t.high}</SelectItem>
                       <SelectItem value="urgent">{t.urgent}</SelectItem>
                     </SelectContent>
                   </Select>
                 </div>
                 <div className="grid grid-cols-2 gap-3">
                   <div><Label>{t.name}</Label><Input value={name} onChange={e => setName(e.target.value)} className="min-h-[44px] mt-1" /></div>
                   <div><Label>{t.phone}</Label><Input value={phone} onChange={e => setPhone(e.target.value)} className="min-h-[44px] mt-1" /></div>
                 </div>
                 <Button onClick={submitLegacy} disabled={submitting} className="w-full text-white min-h-[44px]" style={{ background: accent }}>
                   {submitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}{submitting ? t.sending : t.submit}
                 </Button>
               </CardContent>
             </Card>
          )}
          <GuestThread tenantId={tenantId} roomId={roomId} token={guestSession} t={t} lang={lang} rtl={rtl} accent={accent} alwaysShow={false} />
        </div>
      </div>
    );
  }

  // Catalogue Mode Rendering
  return (
    <div dir={rtl ? "rtl" : "ltr"} className="min-h-screen bg-slate-50 pb-32">
      {renderHeader()}
      <div className="max-w-2xl mx-auto px-4 -mt-4 relative">
        {view === "departments" && (
          <Card className="shadow-xl">
            <CardHeader><CardTitle>{t.pick}</CardTitle></CardHeader>
            <CardContent className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {catalogueData.departments.map(dept => {
                const Icon = ICONS[dept.icon] || MessageSquare;
                return (
                  <button key={dept.department_code} onClick={() => { setSelectedDeptCode(dept.department_code); setView("services"); }} className="flex flex-col items-center gap-3 p-4 rounded-xl border-2 border-slate-200 hover:border-slate-400 active:scale-95 transition-all min-h-[44px]" data-testid={`dept-${dept.department_code}`}>
                    <div className="w-14 h-14 rounded-full flex items-center justify-center" style={{ background: `${accent}15`, color: accent }}>
                      <Icon className="w-7 h-7" />
                    </div>
                    <span className="text-sm font-semibold text-center">{dept.label}</span>
                  </button>
                );
              })}
            </CardContent>
          </Card>
        )}

        {view === "services" && (
          <Card className="shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between pb-2 border-b">
              <CardTitle className="text-lg">
                {catalogueData.departments.find(d => d.department_code === selectedDeptCode)?.label || selectedDeptCode}
              </CardTitle>
              <Button variant="ghost" size="sm" onClick={() => setView("departments")} className="min-h-[44px]">{t.back}</Button>
            </CardHeader>
            <CardContent className="pt-4 space-y-4">
              {catalogueData.services.filter(s => s.department_code === selectedDeptCode).map(service => {
                const Icon = ICONS[service.icon] || MessageSquare;
                const cartItem = cartState.cart.find(c => c.service_code === service.service_code);
                
                return (
                  <div key={service.service_code} className="flex flex-col p-4 rounded-xl border border-slate-200 bg-white" data-testid={`service-${service.service_code}`}>
                    <div className="flex items-start gap-3">
                      <div className="w-10 h-10 rounded-full flex items-center justify-center shrink-0 bg-slate-100 text-slate-600">
                        <Icon className="w-5 h-5" />
                      </div>
                      <div className="flex-1">
                        <h4 className="font-semibold text-slate-800">{service.label}</h4>
                        {service.description && <p className="text-xs text-slate-500 mt-1">{service.description}</p>}
                        {service.is_chargeable && (
                           <p className="text-[10px] text-amber-600 font-medium bg-amber-50 inline-block px-1.5 py-0.5 rounded mt-1">
                             {service.charge_warning || t.chargeWarning}
                           </p>
                        )}
                      </div>
                    </div>
                    <ServiceInput 
                      service={service} 
                      cartItem={cartItem} 
                      onChange={(updates) => {
                         if (updates === null) {
                            cartState.removeItem(service.service_code);
                         } else {
                            cartState.updateItem(service.service_code, { ...updates, input_type: service.input_type, department_code: service.department_code, catalogueItem: service });
                         }
                      }} 
                      t={t} 
                      accent={accent}
                    />
                  </div>
                );
              })}
            </CardContent>
          </Card>
        )}

        {view === "review" && (
          <Card className="shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between pb-2 border-b">
              <CardTitle className="text-lg">{t.reviewReq}</CardTitle>
              <Button variant="ghost" size="sm" onClick={() => setView(selectedDeptCode ? "services" : "departments")} className="min-h-[44px]">{t.back}</Button>
            </CardHeader>
            <CardContent className="pt-4 space-y-4">
              {cartState.cart.length === 0 ? (
                <div className="text-center py-6 text-slate-500">{t.emptyCart}</div>
              ) : (
                <div className="space-y-4">
                  {cartState.cart.map(c => {
                     const service = catalogueData.services.find(s => s.service_code === c.service_code) || c.catalogueItem;
                     const Icon = ICONS[service?.icon] || MessageSquare;
                     return (
                       <div key={c.service_code} className="p-3 border border-slate-200 rounded-xl bg-slate-50" data-testid={`review-item-${c.service_code}`}>
                         <div className="flex items-center gap-3 mb-2">
                           <div className="w-8 h-8 rounded-full bg-white flex items-center justify-center shrink-0">
                             <Icon className="w-4 h-4 text-slate-600" />
                           </div>
                           <div className="flex-1 font-medium text-sm text-slate-800">{service?.label || c.service_code}</div>
                         </div>
                         <ServiceInput 
                           service={service} 
                           cartItem={c} 
                           onChange={(updates) => {
                             if (updates === null) cartState.removeItem(c.service_code);
                             else cartState.updateItem(c.service_code, updates);
                           }} 
                           t={t} accent={accent} 
                         />
                         <Input 
                           value={c.note || ""} 
                           onChange={(e) => cartState.updateItem(c.service_code, { note: e.target.value })}
                           placeholder={t.addNote}
                           className="mt-2 text-sm min-h-[44px]"
                         />
                       </div>
                     );
                  })}

                  {cartState.hasChargeable && (
                    <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-start gap-2">
                      <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
                      <p className="text-sm text-amber-800">{t.chargeWarning}</p>
                    </div>
                  )}

                  <div className="grid grid-cols-2 gap-3 pt-2">
                     <div><Label>{t.name}</Label><Input value={name} onChange={e => setName(e.target.value)} className="min-h-[44px] mt-1" /></div>
                     <div><Label>{t.phone}</Label><Input value={phone} onChange={e => setPhone(e.target.value)} className="min-h-[44px] mt-1" /></div>
                  </div>

                  <Button onClick={submitStructured} disabled={submitting || cartState.cart.length === 0} className="w-full text-white min-h-[44px] mt-4" style={{ background: accent }}>
                    {submitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}{submitting ? t.sending : t.submit}
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        <GuestThread tenantId={tenantId} roomId={roomId} token={guestSession} t={t} lang={lang} rtl={rtl} accent={accent} alwaysShow={false} />
      </div>

      {/* Sticky Cart Summary */}
      {cartState.totalItems > 0 && view !== "review" && (
        <div className="fixed bottom-0 left-0 right-0 p-4 bg-white border-t border-slate-200 shadow-[0_-4px_12px_rgba(0,0,0,0.05)] z-50 pb-[env(safe-area-inset-bottom,16px)]" data-testid="sticky-cart">
          <div className="max-w-2xl mx-auto flex items-center justify-between gap-4">
             <div className="flex flex-col">
               <span className="font-semibold text-slate-800">{cartState.totalItems} {t.items}</span>
               {cartState.hasChargeable && <span className="text-xs text-amber-600 flex items-center gap-1"><AlertTriangle className="w-3 h-3"/> Ücretli</span>}
             </div>
             <Button onClick={() => setView("review")} className="flex-1 text-white min-h-[44px]" style={{ background: accent }}>
               {t.reviewReq}
             </Button>
          </div>
        </div>
      )}
    </div>
  );
}
