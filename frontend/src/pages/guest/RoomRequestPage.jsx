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
import { Loader2, Hotel, AlertTriangle, CheckCircle2, Minus, Plus, MessageSquare, ChevronLeft, ChevronRight, ShieldCheck } from "lucide-react";
import { ICONS, LANGS, UI, LOCALE, DEPT_LABELS, DEPT_ICONS, DEPT_DESCRIPTIONS, EXPERIENCE_COPY } from "./constants";
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

function getLocalDateString(offsetDays = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  const pad = n => n.toString().padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function getLabel(item, lang, fallbackCode) {
  if (!item) return fallbackCode || "";
  if (typeof item.label === "string" && item.label.trim()) return item.label.trim();
  const labels = item.labels;
  if (!labels || typeof labels !== "object") return fallbackCode || "";
  if (labels[lang]) return labels[lang];
  if (labels.en) return labels.en;
  for (const key of Object.keys(labels)) {
    if (labels[key]) return labels[key];
  }
  return fallbackCode || "";
}

function getLocalizedText(value, lang, fallback = "") {
  if (typeof value === "string") return value;
  if (value && typeof value === "object") return getLabel({ labels: value }, lang, fallback);
  return fallback;
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
    <Card className="mt-4 rounded-[1.5rem] border-slate-200/80 shadow-[0_18px_45px_-32px_rgba(15,23,42,0.6)]" data-testid="guest-thread-card">
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
function ServiceInput({ service, cartItem, onChange, t, accent, lang, experience }) {
  const type = service.input_type;
  const config = service.input_config || {};
  
  if (type === "one_tap") {
    const isSelected = !!cartItem;
    return (
      <Button 
        variant={isSelected ? "default" : "outline"}
        onClick={() => isSelected ? onChange(null) : onChange({ value: {} })}
        className="w-full mt-3 min-h-[46px] rounded-xl font-semibold"
        style={isSelected ? { background: accent } : { color: accent, borderColor: `${accent}66`, background: `${accent}08` }}
      >
        {isSelected ? experience.serviceAdded : experience.serviceAdd}
      </Button>
    );
  }

  if (type === "quantity") {
    const qty = cartItem?.value?.quantity;
    const min = config.min ?? 1;
    const max = config.max ?? 99;
    const def = config.default ?? min;
    const currentQty = qty === undefined ? 0 : qty;
    
    return (
      <div className="mt-2 flex flex-col gap-2">
        <div className="flex items-center justify-between bg-slate-50 rounded-lg p-1">
          <Button 
            variant="ghost" 
            size="icon" 
            onClick={() => {
              if (currentQty === 0) return;
              if (currentQty > min) {
                 onChange({ value: { quantity: currentQty - 1 } });
              }
            }}
            disabled={currentQty <= min}
            className="h-8 w-8 min-w-[44px] min-h-[44px]"
          >
            <Minus className="w-4 h-4" />
          </Button>
          <span className="font-semibold text-base min-w-[32px] text-center" data-testid={`qty-${service.service_code}`}>{currentQty}</span>
          <Button 
            variant="ghost" 
            size="icon" 
            onClick={() => {
               if (currentQty === 0) {
                 onChange({ value: { quantity: def } });
               } else if (currentQty < max) {
                 onChange({ value: { quantity: currentQty + 1 } });
               }
            }}
            disabled={currentQty >= max && currentQty > 0}
            className="h-8 w-8 min-w-[44px] min-h-[44px]"
            style={{ color: accent }}
          >
            <Plus className="w-4 h-4" />
          </Button>
        </div>
        {cartItem && (
          <Button variant="ghost" size="sm" onClick={() => onChange(null)} className="text-red-500 self-start p-0 h-auto min-h-[44px]">
            {t.remove}
          </Button>
        )}
      </div>
    );
  }

  if (type === "single_choice") {
    const opts = config.options || [];
    const selected = cartItem?.value?.selected_options?.[0] || "";
    return (
      <div className="mt-2 flex flex-col gap-2">
        <Select value={selected} onValueChange={(val) => onChange({ value: { selected_options: [val] } })}>
          <SelectTrigger className="w-full min-h-[44px]"><SelectValue placeholder={t.selectOption} /></SelectTrigger>
          <SelectContent>
            {opts.map(o => (
              <SelectItem key={o.code} value={o.code}>{getLabel(o, lang, o.code)}</SelectItem>
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
    const opts = config.options || [];
    const selected = cartItem?.value?.selected_options || [];
    const minSel = config.min_selections ?? 0;
    const maxSel = config.max_selections ?? 99;

    return (
      <div className="mt-2 flex flex-col gap-2">
        {opts.map(o => {
          const checked = selected.includes(o.code);
          const disabled = !checked && selected.length >= maxSel;
          return (
            <label key={o.code} className={`flex items-center gap-2 min-h-[44px] ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}>
              <input 
                type="checkbox" 
                checked={checked} 
                disabled={disabled}
                onChange={(e) => {
                  let newSel = e.target.checked ? [...selected, o.code] : selected.filter(x => x !== o.code);
                  newSel = [...new Set(newSel)]; // ensure no duplicates
                  
                  // if min_selections > 0, we still allow UI removal but backend will reject if we submit below min
                  // we will let the cart remove it entirely if length becomes 0 and min_selections is 0
                  if (newSel.length === 0 && minSel === 0) onChange(null);
                  else onChange({ value: { selected_options: newSel } });
                }}
                className="w-5 h-5 rounded border-slate-300"
                style={{ accentColor: accent }}
              />
              <span className="text-sm">{getLabel(o, lang, o.code)}</span>
            </label>
          );
        })}
        {cartItem && minSel > 0 && selected.length < minSel && (
           <span className="text-xs text-red-500">Lütfen en az {minSel} seçim yapın</span>
        )}
        {cartItem && (
          <Button variant="ghost" size="sm" onClick={() => onChange(null)} className="text-red-500 self-start p-0 h-auto min-h-[44px]">
            {t.remove}
          </Button>
        )}
      </div>
    );
  }

  if (type === "date" || type === "time" || type === "datetime") {
    const key = `${type}_value`;
    const val = cartItem?.value?.[key] || "";
    
    let inputType = "date";
    let min = undefined;
    let max = undefined;
    let step = undefined;

    if (type === "date" || type === "datetime") {
      const minDays = config.min_days_ahead ?? 0;
      const maxDays = config.max_days_ahead ?? 365;
      
      if (type === "date") {
        inputType = "date";
        min = getLocalDateString(minDays);
        max = getLocalDateString(maxDays);
      } else {
        inputType = "datetime-local";
        min = getLocalDateString(minDays) + "T00:00";
        max = getLocalDateString(maxDays) + "T23:59";
      }
    }

    if (type === "time") {
      inputType = "time";
    }

    if (type === "time" || type === "datetime") {
      if (config.interval_minutes) {
        step = config.interval_minutes * 60;
      }
    }

    return (
      <div className="mt-2 flex flex-col gap-2">
        <Input 
          type={inputType}
          value={val}
          min={min}
          max={max}
          step={step}
          onChange={(e) => {
            if (!e.target.value) {
               onChange(null);
               return;
            }
            
            const selectedVal = e.target.value;
            if (min && selectedVal < min) return;
            if (max && selectedVal > max) return;
            
            if ((type === "time" || type === "datetime") && config.interval_minutes) {
               const timePart = type === "datetime" ? selectedVal.split('T')[1] : selectedVal;
               if (timePart) {
                  const [hh, mm] = timePart.split(':');
                  const totalMins = parseInt(hh || 0) * 60 + parseInt(mm || 0);
                  if (totalMins % config.interval_minutes !== 0) return;
               }
            }
            
            onChange({ value: { [key]: selectedVal } });
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
    const nav = (typeof navigator !== "undefined" && navigator.language) ? navigator.language.slice(0, 2) : "tr";
    return UI[nav] ? nav : "tr";
  });
  const t = UI[lang] || UI.tr;
  const experience = EXPERIENCE_COPY[lang] || EXPERIENCE_COPY.en;
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
  
  // Submit state
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [submittedItems, setSubmittedItems] = useState([]);
  const submitGuard = useRef(false);

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
          if (!catRes.data || !Array.isArray(catRes.data.departments) || !Array.isArray(catRes.data.services)) {
             setSubmitError(t.loadError);
             setMode("error");
             return;
          }
          
          let valid = true;
          const deptCodes = new Set();
          for (const d of catRes.data.departments) {
             if (!d.department_code) valid = false;
             deptCodes.add(d.department_code);
          }
          
          const sCodes = new Set();
          const SUPPORTED_TYPES = ["one_tap", "quantity", "single_choice", "multi_choice", "date", "time", "datetime"];
          
          for (const s of catRes.data.services) {
             if (!s.service_code || sCodes.has(s.service_code)) valid = false;
             sCodes.add(s.service_code);
             if (!deptCodes.has(s.department_code)) valid = false;
             if (!SUPPORTED_TYPES.includes(s.input_type)) valid = false;
             if (s.input_config === null || typeof s.input_config !== "object" || Array.isArray(s.input_config)) valid = false;
          }

          if (!valid) {
             setSubmitError(t.loadError);
             setMode("error");
             return;
          }

          setCatalogueData(catRes.data);
          setMode("catalogue");
        }
      } catch (catErr) {
        const status = catErr.response?.status;
        if (status === 404) {
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
    if (submitGuard.current) return;
    submitGuard.current = true;
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
      setSubmittedItems([catLabel]);
      setView("success");
    } catch (e) {
      handleSubmitError(e);
    } finally {
      submitGuard.current = false;
      setSubmitting(false);
    }
  };

  const submitStructured = async () => {
    if (cartState.cart.length === 0 || submitting || !guestSession) return;
    if (submitGuard.current) return;
    
    // Validate min_selections for multi_choice
    for (const item of cartState.cart) {
      const config = item.catalogueItem?.input_config || {};
      if (item.input_type === "multi_choice" && config.min_selections > 0) {
        const len = item.value?.selected_options?.length || 0;
        if (len < config.min_selections) {
          alertDialog({ message: `Lütfen ${getLabel(item.catalogueItem, lang, item.service_code)} için en az ${config.min_selections} seçim yapın.` });
          return;
        }
      }
    }
    
    submitGuard.current = true;
    setSubmitting(true);
    setSubmitError("");

    let key, payload;
    if (cartState.snapshot) {
      key = cartState.snapshot.key;
      payload = cartState.snapshot.payload;
    } else {
      key = cartState.generateIdempotencyKey();
      payload = {
        language: lang,
        idempotency_key: key,
        items: cartState.cart.map(c => {
           const obj = { service_code: c.service_code };
           if (c.value && Object.keys(c.value).length > 0) obj.value = c.value;
           if (c.note?.trim()) obj.note = c.note.trim();
           return obj;
        })
      };
      cartState.setSnapshot({ key, payload });
    }

    try {
      const readableItems = cartState.cart.map((item) =>
        getLabel(item.catalogueItem, lang, item.service_code),
      );
      await axios.post(`/public/room-qr/${tenantId}/${roomId}/submit`, payload, {
        headers: { "X-Guest-Session": guestSession }
      });
      cartState.clearCart();
      setSubmittedItems(readableItems);
      setView("success");
    } catch (e) {
      handleSubmitError(e);
    } finally {
      submitGuard.current = false;
      setSubmitting(false);
    }
  };

  const handleSubmitError = (e) => {
    const status = e.response?.status;
    if (status === 401 || status === 403 || status === 410) {
      setMode("unavailable");
      setGuestSession(null);
    } else if (status === 409) {
      // 409 -> do not retry automatically, keep snapshot? Wait, cart edit clears it.
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
    setSubmittedItems([]);
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

  const renderHeader = () => (
    <header
      className="relative overflow-hidden rounded-b-[2rem] text-white shadow-[0_18px_45px_-28px_rgba(15,23,42,0.85)]"
      style={{ background: `linear-gradient(135deg, ${accent} 0%, #172033 112%)` }}
    >
      <div className="pointer-events-none absolute -right-16 -top-20 h-52 w-52 rounded-full bg-white/10" />
      <div className="pointer-events-none absolute -bottom-24 -left-16 h-48 w-48 rounded-full bg-slate-950/10" />
      <div className="relative mx-auto max-w-xl px-4 pb-16 pt-[max(1.25rem,env(safe-area-inset-top))] sm:px-6">
        <div className="mb-8 flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            {meta.hotel_logo ? (
              <img src={meta.hotel_logo} alt={meta.hotel_name} className="h-11 w-11 shrink-0 rounded-xl bg-white object-contain p-1.5 shadow-sm" />
            ) : (
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-white/20 bg-white/15 backdrop-blur-sm">
                <Hotel className="h-6 w-6" />
              </div>
            )}
            <div className="min-w-0">
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-white/70">{experience.guestServices}</div>
              <div className="truncate text-base font-semibold sm:text-lg">{meta.hotel_name}</div>
            </div>
          </div>
          <Select value={lang} onValueChange={setLang}>
            <SelectTrigger aria-label={t.language} className="h-10 min-h-10 w-[110px] shrink-0 border-white/20 bg-white text-slate-700 shadow-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LANGS.map((l) => <SelectItem key={l.code} value={l.code}>{l.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <div className="mb-2 text-sm font-medium text-white/75">{t.welcome}</div>
          <div className="max-w-sm text-2xl font-semibold leading-tight tracking-tight sm:text-3xl">{experience.heroSubtitle}</div>
        </div>
        <div className="mt-5 inline-flex max-w-full items-center gap-2 rounded-full border border-white/20 bg-white/15 px-3.5 py-2 text-sm font-medium backdrop-blur-sm">
          <span className="text-white/70">{t.room}</span>
          <strong className="text-base">{meta.room_number}</strong>
          {meta.room_type && <><span className="h-1 w-1 rounded-full bg-white/50" /><span className="truncate text-white/80">{meta.room_type}</span></>}
        </div>
      </div>
    </header>
  );

  if (view === "success") {
    return (
      <div dir={rtl ? "rtl" : "ltr"} className="min-h-screen bg-slate-50 pb-24">
        {renderHeader()}
        <div className="mx-auto -mt-8 max-w-xl px-4">
          <Card className="rounded-[1.75rem] border-0 shadow-[0_18px_50px_-30px_rgba(15,23,42,0.5)]">
            <CardContent className="p-10 text-center">
              <div className="w-20 h-20 mx-auto rounded-full bg-emerald-100 flex items-center justify-center mb-4">
                <CheckCircle2 className="w-12 h-12 text-emerald-600" />
              </div>
              <h2 className="text-2xl font-bold mb-2">{t.sent}</h2>
              <p className="text-gray-600 mb-6">{mode === "catalogue" ? t.structuredSentDesc : t.sentDesc}</p>
              
              {submittedItems.length > 0 && (
                <div className="mb-6 rounded-2xl border border-emerald-100 bg-emerald-50/70 p-4 text-left" data-testid="success-summary">
                  <div className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-emerald-800/70">
                    {t.requestSummary}
                  </div>
                  <div className="space-y-2">
                    {submittedItems.map((label, index) => (
                      <div key={`${label}-${index}`} className="flex items-center gap-2 text-sm font-medium text-slate-800">
                        <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
                        <span>{label}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

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

  if (mode === "legacy") {
    return (
      <div dir={rtl ? "rtl" : "ltr"} className="min-h-screen bg-slate-50 pb-24">
        {renderHeader()}
        <div className="mx-auto -mt-8 max-w-xl px-4">
          {!selectedDeptCode ? (
             <Card className="rounded-[1.75rem] border-0 shadow-[0_18px_50px_-30px_rgba(15,23,42,0.5)]">
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

  return (
    <div dir={rtl ? "rtl" : "ltr"} className="min-h-screen bg-[#f4f6fa] pb-32 text-slate-900">
      {renderHeader()}
      <main className="relative mx-auto -mt-8 max-w-xl px-4">
        {view === "departments" && (
          <Card className="overflow-hidden rounded-[1.75rem] border-0 bg-white/95 shadow-[0_22px_60px_-34px_rgba(15,23,42,0.55)] backdrop-blur">
            <CardHeader className="px-5 pb-3 pt-6 sm:px-6">
              <CardTitle className="text-[1.35rem] font-semibold leading-tight tracking-tight">{experience.pickTitle}</CardTitle>
              <p className="pt-1 text-sm leading-6 text-slate-500">{experience.pickHint}</p>
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-3 px-4 pb-5 sm:grid-cols-3 sm:px-6">
              {catalogueData.departments.map(dept => {
                const Icon = ICONS[dept.icon] || MessageSquare;
                const deptDescriptions = DEPT_DESCRIPTIONS[lang] || DEPT_DESCRIPTIONS.en;
                const description = deptDescriptions[dept.department_code] || experience.departmentFallback;
                return (
                  <button
                    key={dept.department_code}
                    onClick={() => { setSelectedDeptCode(dept.department_code); setView("services"); }}
                    className="group flex min-h-[76px] w-full items-center gap-4 rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-[0_8px_24px_-22px_rgba(15,23,42,0.8)] transition hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md active:translate-y-0 sm:min-h-[156px] sm:flex-col sm:justify-center sm:text-center"
                    data-testid={`dept-${dept.department_code}`}
                  >
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl transition-transform group-hover:scale-105 sm:h-14 sm:w-14" style={{ background: `${accent}12`, color: accent }}>
                      <Icon className="h-6 w-6 sm:h-7 sm:w-7" />
                    </div>
                    <span className="min-w-0 flex-1 sm:flex-none">
                      <span className="block text-[15px] font-semibold text-slate-900">{getLabel(dept, lang, dept.department_code)}</span>
                      <span className="mt-0.5 block text-xs leading-5 text-slate-500 sm:hidden">{description}</span>
                    </span>
                    <ChevronRight className={`h-5 w-5 shrink-0 text-slate-300 sm:hidden ${rtl ? "rotate-180" : ""}`} />
                  </button>
                );
              })}
            </CardContent>
            <div className="flex items-center justify-center gap-2 border-t border-slate-100 px-5 py-3.5 text-xs text-slate-500">
              <ShieldCheck className="h-4 w-4" style={{ color: accent }} />
              <span>{experience.secureNote}</span>
            </div>
          </Card>
        )}

        {view === "services" && (
          <Card className="overflow-hidden rounded-[1.75rem] border-0 shadow-[0_22px_60px_-34px_rgba(15,23,42,0.55)]">
            <CardHeader className="border-b border-slate-100 px-5 pb-4 pt-5">
              <div className="flex items-center gap-3">
                <Button variant="ghost" size="icon" onClick={() => setView("departments")} className="h-10 w-10 shrink-0 rounded-full" aria-label={t.back}>
                  <ChevronLeft className={`h-5 w-5 ${rtl ? "rotate-180" : ""}`} />
                  <span className="sr-only">{t.back}</span>
                </Button>
                <div className="min-w-0">
                  <CardTitle className="truncate text-lg font-semibold">
                    {getLabel(catalogueData.departments.find(d => d.department_code === selectedDeptCode), lang, selectedDeptCode)}
                  </CardTitle>
                  <p className="mt-0.5 text-xs text-slate-500">{experience.serviceHint}</p>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-3 bg-slate-50/70 px-4 py-4 sm:px-5">
              {catalogueData.services.filter(s => s.department_code === selectedDeptCode).map(service => {
                const Icon = ICONS[service.icon] || MessageSquare;
                const cartItem = cartState.cart.find(c => c.service_code === service.service_code);
                const description = getLocalizedText(service.description, lang);
                const chargeWarning = getLocalizedText(service.charge_warning, lang, t.chargeWarning);
                
                return (
                  <div key={service.service_code} className="flex flex-col rounded-2xl border border-slate-200/80 bg-white p-4 shadow-[0_10px_28px_-26px_rgba(15,23,42,0.9)]" data-testid={`service-${service.service_code}`}>
                    <div className="flex items-start gap-3">
                      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl" style={{ background: `${accent}12`, color: accent }}>
                        <Icon className="h-5 w-5" />
                      </div>
                      <div className="min-w-0 flex-1 pt-0.5">
                        <h4 className="font-semibold leading-5 text-slate-900">{getLabel(service, lang, service.service_code)}</h4>
                        {description && <p className="mt-1 text-xs leading-5 text-slate-500">{description}</p>}
                        {service.is_chargeable && (
                           <p className="mt-2 inline-block rounded-full bg-amber-50 px-2 py-1 text-[11px] font-medium text-amber-700">
                             {chargeWarning}
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
                      lang={lang}
                      experience={experience}
                    />
                  </div>
                );
              })}
            </CardContent>
          </Card>
        )}

        {view === "review" && (
          <Card className="overflow-hidden rounded-[1.75rem] border-0 shadow-[0_22px_60px_-34px_rgba(15,23,42,0.55)]">
            <CardHeader className="border-b border-slate-100 px-5 pb-4 pt-5">
              <div className="flex items-center gap-3">
                <Button variant="ghost" size="icon" onClick={() => setView(selectedDeptCode ? "services" : "departments")} className="h-10 w-10 shrink-0 rounded-full" aria-label={t.back}>
                  <ChevronLeft className={`h-5 w-5 ${rtl ? "rotate-180" : ""}`} />
                  <span className="sr-only">{t.back}</span>
                </Button>
                <CardTitle className="text-lg font-semibold">{t.reviewReq}</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="space-y-4 bg-slate-50/70 px-4 py-4 sm:px-5">
              {cartState.cart.length === 0 ? (
                <div className="text-center py-6 text-slate-500">{t.emptyCart}</div>
              ) : (
                <div className="space-y-4">
                  {cartState.cart.map(c => {
                     const service = catalogueData.services.find(s => s.service_code === c.service_code) || c.catalogueItem;
                     const Icon = ICONS[service?.icon] || MessageSquare;
                     return (
                       <div key={c.service_code} className="rounded-2xl border border-slate-200 bg-white p-4" data-testid={`review-item-${c.service_code}`}>
                         <div className="flex items-center gap-3 mb-2">
                           <div className="w-8 h-8 rounded-full bg-white flex items-center justify-center shrink-0">
                             <Icon className="w-4 h-4 text-slate-600" />
                           </div>
                           <div className="flex-1 font-medium text-sm text-slate-800">{getLabel(service, lang, c.service_code)}</div>
                         </div>
                         <ServiceInput 
                           service={service} 
                           cartItem={c} 
                           onChange={(updates) => {
                             if (updates === null) cartState.removeItem(c.service_code);
                             else cartState.updateItem(c.service_code, updates);
                           }} 
                           t={t} accent={accent} lang={lang} experience={experience}
                         />
                         <Input 
                           value={c.note || ""} 
                           onChange={(e) => cartState.updateItem(c.service_code, { note: e.target.value })}
                           placeholder={t.addNote}
                           className="mt-2 text-sm min-h-[44px]"
                           data-testid={`note-${c.service_code}`}
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

                  <Button onClick={submitStructured} disabled={submitting || cartState.cart.length === 0} className="mt-4 min-h-[48px] w-full rounded-xl font-semibold text-white" style={{ background: accent }} data-testid="button-structured-submit">
                    {submitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}{submitting ? t.sending : t.submit}
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        <GuestThread tenantId={tenantId} roomId={roomId} token={guestSession} t={t} lang={lang} rtl={rtl} accent={accent} alwaysShow={false} />
      </main>

      {cartState.totalItems > 0 && view !== "review" && (
        <div className="fixed bottom-0 left-0 right-0 z-50 border-t border-slate-200/80 bg-white/95 p-4 pb-[max(1rem,env(safe-area-inset-bottom))] shadow-[0_-12px_35px_-28px_rgba(15,23,42,0.7)] backdrop-blur" data-testid="sticky-cart">
          <div className="mx-auto flex max-w-xl items-center justify-between gap-4">
             <div className="flex flex-col">
               <span className="font-semibold text-slate-800">{cartState.totalItems} {t.items}</span>
               {cartState.hasChargeable && <span className="text-xs text-amber-600 flex items-center gap-1"><AlertTriangle className="w-3 h-3"/> Ücretli</span>}
             </div>
             <Button onClick={() => setView("review")} className="min-h-[48px] flex-1 rounded-xl font-semibold text-white" style={{ background: accent }}>
               {t.reviewReq}
             </Button>
          </div>
        </div>
      )}
    </div>
  );
}
