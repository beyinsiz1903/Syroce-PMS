/**
 * Syroce Contact Center — Faz 2 sesli softphone (WebRTC).
 *
 * Tasarım kararları (doktrin):
 *  - LAZY: Bu bileşen App'te ``React.lazy`` ile yüklenir; Twilio Voice SDK'sı da
 *    yalnızca operatör "Aktifleştir"e basınca CDN'den enjekte edilir — uygulama
 *    açılışında ne SDK ne de mikrofon izni istenir (gizlilik + bundle maliyeti).
 *  - MIKROFON İZNİ AKTİVASYONDA: ``getUserMedia`` yalnızca açık kullanıcı
 *    eylemiyle çağrılır.
 *  - FAIL-CLOSED: Token ucu 503 (not_configured) dönerse softphone "yapılandırılmamış"
 *    durumunda kalır; sahte/çevrimdışı çağrı simülasyonu YOK.
 *  - PII/SECRET: AccessToken loglanmaz; arayan numarası yalnızca SDK'nın verdiği
 *    kadar gösterilir, kalıcılaştırılmaz.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Phone, PhoneIncoming, PhoneOutgoing, Mic, MicOff, Grid, MessageCircle, PhoneForwarded } from "lucide-react";
import axios from "axios";
import CallHistory from "./CallHistory";

import { SOFTPHONE_DIAL_EVENT } from "@/lib/softphone";

const TWILIO_VOICE_SDK_URL =
  "https://unpkg.com/@twilio/voice-sdk@2.11.2/dist/twilio.min.js";

let _sdkPromise = null;

// Twilio Voice SDK'sını yalnızca bir kez, ihtiyaç anında CDN'den yükler.
function loadTwilioVoiceSdk() {
  if (typeof window !== "undefined" && window.Twilio?.Device) {
    return Promise.resolve(window.Twilio);
  }
  if (_sdkPromise) return _sdkPromise;
  _sdkPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector(
      `script[src="${TWILIO_VOICE_SDK_URL}"]`,
    );
    if (existing) {
      existing.addEventListener("load", () => resolve(window.Twilio));
      existing.addEventListener("error", () =>
        reject(new Error("sdk_load_failed")),
      );
      return;
    }
    const script = document.createElement("script");
    script.src = TWILIO_VOICE_SDK_URL;
    script.async = true;
    script.onload = () => {
      if (window.Twilio?.Device) resolve(window.Twilio);
      else reject(new Error("sdk_unavailable"));
    };
    script.onerror = () => {
      _sdkPromise = null;
      reject(new Error("sdk_load_failed"));
    };
    document.head.appendChild(script);
  });
  return _sdkPromise;
}

function getJwtExpiration(token) {
  try {
    if (!token) return null;
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = JSON.parse(
      atob(parts[1].replace(/-/g, "+").replace(/_/g, "/"))
    );
    return payload.exp ? payload.exp * 1000 : null; // in milliseconds
  } catch {
    return null;
  }
}

const STATUS_LABEL = {
  idle: "Kapalı",
  activating: "Etkinleştiriliyor...",
  ready: "Hazır",
  incoming: "Gelen çağrı",
  on_call: "Görüşmede",
  not_configured: "Yapılandırılmamış",
  error: "Hata",
};

export default function Softphone({ user }) {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState("dialer");
  const [status, setStatus] = useState("idle");
  const [detail, setDetail] = useState("");
  const [incomingFrom, setIncomingFrom] = useState("");
  const [dialNumber, setDialNumber] = useState("");
  const [isMuted, setIsMuted] = useState(false);
  const [callDuration, setCallDuration] = useState(0);
  const [showDialpad, setShowDialpad] = useState(false);
  const [showTransfer, setShowTransfer] = useState(false);
  const [transferTarget, setTransferTarget] = useState("");
  const [transferring, setTransferring] = useState(false);
  const [sendingWhatsapp, setSendingWhatsapp] = useState(false);
  const [token, setToken] = useState(null);
  const [isSdkReady, setIsSdkReady] = useState(false);
  const deviceRef = useRef(null);
  const callRef = useRef(null);

  const role = user?.role || (user?.roles && user.roles[0]);
  const isStaff = role && role !== "guest";

  const fetchToken = useCallback(() => {
    axios.post("/contact-center/voice/token")
      .then((res) => {
        if (res.data?.token) {
          setToken(res.data.token);
        }
      })
      .catch((err) => {
        console.warn("[CC-VOICE] Fetching voice token failed:", err);
      });
  }, []);

  // Pre-load SDK on mount
  useEffect(() => {
    if (!isStaff) return;
    loadTwilioVoiceSdk()
      .then(() => {
        setIsSdkReady(true);
      })
      .catch((err) => {
        console.warn("[CC-VOICE] Twilio SDK preloading failed:", err);
      });
  }, [isStaff]);

  // Keep token fresh in background + visibility checks + sleep protection (only when drawer is open)
  useEffect(() => {
    if (!isStaff || !open) return;

    const checkAndRefresh = () => {
      const exp = getJwtExpiration(token);
      const isStale = !token || (exp ? Date.now() >= exp - 5 * 60 * 1000 : true);
      if (isStale) {
        fetchToken();
      }
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        checkAndRefresh();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    checkAndRefresh();

    // Check every 1 minute to detect sleep/timer-throttling recovery
    const checkInterval = setInterval(checkAndRefresh, 60 * 1000);

    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      clearInterval(checkInterval);
    };
  }, [isStaff, fetchToken, token, open]);

  useEffect(() => {
    let timer;
    if (status === "on_call") {
      timer = setInterval(() => setCallDuration((prev) => prev + 1), 1000);
    } else {
      setCallDuration(0);
    }
    return () => clearInterval(timer);
  }, [status]);

  const teardown = useCallback(() => {
    try {
      callRef.current?.disconnect?.();
    } catch {
      /* noop */
    }
    callRef.current = null;
    try {
      deviceRef.current?.destroy?.();
    } catch {
      /* noop */
    }
    deviceRef.current = null;
  }, []);

  useEffect(() => () => teardown(), [teardown]);

  const activate = useCallback(() => {
    // If SDK is not ready or token is stale/missing, do not proceed (prevents async network yields under user gesture)
    const exp = getJwtExpiration(token);
    const isTokenReady = token && (exp ? Date.now() < exp - 5 * 60 * 1000 : false);
    const Twilio = window.Twilio;
    if (!Twilio?.Device || !isTokenReady) {
      setStatus("error");
      setDetail("Bağlantı hazırlanamadı. Lütfen bekleyin veya sayfayı yenileyin.");
      if (!isTokenReady) fetchToken();
      return;
    }

    setStatus("activating");
    setDetail("");

    // 1) AudioContext aktivasyonu — doğrudan tıklama anında SİNKRON olarak başlatılır (Safari autoplay kilidini kaldırır).
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (AudioContextClass) {
      try {
        const audioCtx = new AudioContextClass();
        if (audioCtx.state === "suspended") {
          audioCtx.resume().catch((err) => {
            console.warn("[CC-VOICE] Synchronous AudioContext resume rejected:", err);
          });
        }
      } catch (err) {
        console.warn("[CC-VOICE] AudioContext creation failed:", err);
      }
    }

    // 2) Mikrofon izni — asenkron istek (kullanıcıya sorar, cihaz kaydını engellemez)
    navigator.mediaDevices.getUserMedia({ audio: true })
      .then((stream) => {
        stream.getTracks().forEach((t) => t.stop());
      })
      .catch((err) => {
        console.warn("[CC-VOICE] Microphone permission handling:", err);
        setStatus("error");
        if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
          setDetail("Mikrofon izni reddedildi. Sesli çağrı için tarayıcı ayarlarından mikrofon izni vermeniz gerekir.");
        } else {
          setDetail("Mikrofon erişim hatası: " + (err.message || err.name));
        }
      });

    // 3) Cihaz kurulumu ve Kayıt — senkron call-stack içinde
    try {
      teardown();
      const device = new Twilio.Device(token, { closeProtection: true });
      deviceRef.current = device;

      device.on("registered", () => {
        setStatus("ready");
        setDetail("");
      });
      device.on("error", (e) => {
        setStatus("error");
        setDetail("Cihaz hatası: " + (e?.code || "bilinmiyor"));
      });
      device.on("incoming", (call) => {
        if (callRef.current) {
          try { call.reject(); } catch { /* noop */ }
          return;
        }
        callRef.current = call;
        setIncomingFrom(call?.parameters?.From || "");
        setStatus("incoming");
        setView("dialer");
        setOpen(true);
        call.on("disconnect", () => {
          callRef.current = null;
          setIncomingFrom("");
          setIsMuted(false);
          setStatus(deviceRef.current ? "ready" : "idle");
        });
        call.on("cancel", () => {
          callRef.current = null;
          setIncomingFrom("");
          setIsMuted(false);
          setStatus(deviceRef.current ? "ready" : "idle");
        });
      });

      device.register().catch((err) => {
        console.error("[CC-VOICE] Twilio device registration error:", err);
        setStatus("error");
        setDetail("Cihaz kaydı yapılamadı.");
      });
    } catch (err) {
      console.error("[CC-VOICE] Twilio device initialization error:", err);
      setStatus("error");
      setDetail("Sesli arama cihazı başlatılamadı.");
    }
  }, [teardown, token, fetchToken]);

  const startCall = useCallback((override) => {
    const device = deviceRef.current;
    if (!device) {
      setDetail("Önce softphone'u aktifleştirin.");
      return;
    }
    // onClick event objesi de ilk argüman olarak gelebilir → yalnız string
    // override'ı dikkate al, aksi halde input state'ini kullan.
    const target = (typeof override === "string" ? override : dialNumber || "").trim();
    if (!target) {
      setDetail("Aranacak numarayı girin.");
      return;
    }
    try {
      // Twilio buradaki params'ı TwiML App voiceUrl'ine (/api/voice/outbound)
      // POST eder; kiracı sunucu tarafında client kimliğinden türetilir.
      const call = device.connect({ params: { To: target } });
      callRef.current = call;
      setStatus("on_call");
      setDetail("");
      call.on("disconnect", () => {
        setStatus("idle");
        setCallDuration(0);
        setIsMuted(false);
        setShowDialpad(false);
        setShowTransfer(false);
        callRef.current = null;
      });
      call.on("cancel", () => {
        setStatus("idle");
        setCallDuration(0);
        setIsMuted(false);
        setShowDialpad(false);
        setShowTransfer(false);
        callRef.current = null;
      });
      call.on("reject", () => {
        setStatus("idle");
        setCallDuration(0);
        setIsMuted(false);
        setShowDialpad(false);
        setShowTransfer(false);
        callRef.current = null;
      });
      call.on("error", (e) => {
        callRef.current = null;
        setIsMuted(false);
        setStatus(deviceRef.current ? "ready" : "idle");
        setDetail("Çağrı hatası: " + (e?.message || e?.name || "bilinmiyor"));
      });
    } catch (err) {
      setStatus(deviceRef.current ? "ready" : "idle");
      if (err.name === "NotAllowedError") {
        setDetail("Tarayıcı engeli: Ses çalmak veya arama başlatmak için bir kullanıcı hareketi gerekiyor.");
      } else {
        setDetail("Giden çağrı başlatılamadı: " + (err.message || err.name));
      }
    }
  }, [dialNumber]);

  // Browser Notifications & Ringtones
  useEffect(() => {
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  useEffect(() => {
    if (status === "incoming" && "Notification" in window && Notification.permission === "granted") {
      const notif = new Notification("Gelen Çağrı", {
        body: `Arayan: ${incomingFrom}`,
        icon: "/favicon.ico",
        requireInteraction: true
      });
      return () => notif.close();
    }
  }, [status, incomingFrom]);



  useEffect(() => {
    if (!isStaff) return;
    const onDial = (e) => {
      const number = (e?.detail?.number || "").trim();
      if (!number) return;
      setDialNumber(number);
      setOpen(true);
      if (status === "ready") {
        setDetail("Numara hazır. Arama başlatmak için 'Ara' butonuna tıklayın.");
      } else if (status === "on_call" || status === "incoming") {
        setDetail("Görüşme sürüyor; numara hazır, görüşme bitince arayabilirsiniz.");
      } else {
        setDetail("Numara hazır. Aramak için önce softphone'u aktifleştirin.");
      }
    };
    window.addEventListener("syroce:softphone-dial", onDial);
    return () => window.removeEventListener("syroce:softphone-dial", onDial);
  }, [isStaff, status]);

  const acceptCall = useCallback(() => {
    try {
      callRef.current?.accept?.();
      setStatus("on_call");
    } catch {
      setStatus("error");
      setDetail("Çağrı kabul edilemedi.");
    }
  }, []);

  const rejectCall = useCallback(() => {
    if (callRef.current) callRef.current.reject();
    setStatus("idle");
    setCallDuration(0);
    setIsMuted(false);
    setShowDialpad(false);
    setShowTransfer(false);
  }, []);

  const endCall = useCallback(() => {
    if (callRef.current) callRef.current.disconnect();
    setStatus("idle");
    setCallDuration(0);
    setIsMuted(false);
    setShowDialpad(false);
    setShowTransfer(false);
  }, []);

  const toggleMute = useCallback(() => {
    if (callRef.current) {
      const currentMuted = callRef.current.isMuted();
      callRef.current.mute(!currentMuted);
      setIsMuted(!currentMuted);
    }
  }, []);

  // Keyboard Shortcuts
  useEffect(() => {
    if (status !== "incoming" && status !== "on_call") return;
    
    const handleKeyDown = (e) => {
      // Don't trigger if user is typing in an input field
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;

      switch(e.key.toLowerCase()) {
        case 'enter':
          if (status === "incoming") {
            e.preventDefault();
            callRef.current?.accept?.();
            setStatus("on_call");
          }
          break;
        case 'escape':
          e.preventDefault();
          if (status === "incoming") callRef.current?.reject?.();
          else if (status === "on_call") callRef.current?.disconnect?.();
          setStatus("idle");
          setCallDuration(0);
          break;
        case 'm':
          if (status === "on_call") {
            e.preventDefault();
            toggleMute();
          }
          break;
        case 't':
          if (status === "on_call") {
            e.preventDefault();
            setShowTransfer(prev => !prev);
            setShowDialpad(false);
          }
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [status, toggleMute]);

  const transferCall = async () => {
    if (!transferTarget.trim() || !callRef.current) return;
    setTransferring(true);
    try {
      await axios.post(`/api/contact-center/voice/live/${callRef.current.parameters.CallSid}/transfer`, {
        target: transferTarget.trim()
      });
      setShowTransfer(false);
      setTransferTarget("");
    } catch (err) {
      console.error("Transfer failed", err);
      alert("Aktarma başarısız oldu.");
    } finally {
      setTransferring(false);
    }
  };

  const sendWhatsAppTemplate = async (templateName) => {
    if (!callRef.current) return;
    setSendingWhatsapp(true);
    try {
      const phone = callRef.current.parameters.From || callRef.current.parameters.To || incomingFrom || dialNumber;
      if (!phone) throw new Error("No phone number to send message to.");
      
      await axios.post(`/api/contact-center/voice/live/${callRef.current.parameters.CallSid}/whatsapp`, {
        phone: phone,
        template_name: templateName,
        language_code: "tr"
      });
      alert("WhatsApp mesajı başarıyla gönderildi.");
    } catch (err) {
      console.error("WhatsApp error", err);
      alert("WhatsApp mesajı gönderilemedi.");
    } finally {
      setSendingWhatsapp(false);
    }
  };

  const deactivate = useCallback(() => {
    teardown();
    setStatus("idle");
    setDetail("");
    setIncomingFrom("");
    setIsMuted(false);
  }, [teardown]);

  if (!isStaff) return null;

  const exp = getJwtExpiration(token);
  const isTokenReady = !!(token && exp && Date.now() < exp - 5 * 60 * 1000);
  const isReadyToActivate = isSdkReady && isTokenReady;

  const formatTimer = (sec) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  return (
    <div className="fixed bottom-4 left-4 z-50">
      {open ? (
        <div className="w-72 rounded-lg border border-gray-200 bg-white shadow-xl">
          <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
            <div className="flex items-center gap-2">
              <span
                className={`inline-block h-2 w-2 rounded-full ${
                  status === "ready"
                    ? "bg-emerald-500"
                    : status === "on_call" || status === "incoming"
                      ? "bg-amber-500"
                      : status === "error" || status === "not_configured"
                        ? "bg-red-500"
                        : "bg-gray-300"
                }`}
              />
              <span className="text-sm font-medium text-gray-900">Softphone</span>
              <span className="text-[9px] font-mono text-gray-400">({import.meta.env.VITE_COMMIT_SHA?.slice(0, 7) || "unknown"})</span>
              <span className="text-xs text-gray-500">
                {STATUS_LABEL[status] || status}
              </span>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="text-gray-400 hover:text-gray-600"
              aria-label="Kapat"
            >
              ×
            </button>
          </div>

          <div className="flex border-b border-gray-100">
            <button
              type="button"
              onClick={() => setView("dialer")}
              className={`flex-1 px-4 py-2 text-xs font-medium ${
                view === "dialer"
                  ? "border-b-2 border-gray-900 text-gray-900"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              Telefon
            </button>
            <button
              type="button"
              onClick={() => setView("history")}
              className={`flex-1 px-4 py-2 text-xs font-medium ${
                view === "history"
                  ? "border-b-2 border-gray-900 text-gray-900"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              Geçmiş
            </button>
          </div>

          {view === "history" ? (
            <div className="px-4 py-4">
              <CallHistory />
            </div>
          ) : (
          <div className="space-y-3 px-4 py-4">
            {detail ? (
              <p className="text-xs leading-relaxed text-gray-600">{detail}</p>
            ) : null}

            {status === "incoming" ? (
              <div className="space-y-2">
                <p className="text-sm text-gray-700">
                  Gelen çağrı{incomingFrom ? `: ${incomingFrom}` : ""}
                </p>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={acceptCall}
                    className="flex-1 rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700"
                  >
                    Yanıtla
                  </button>
                  <button
                    type="button"
                    onClick={rejectCall}
                    className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                  >
                    Reddet
                  </button>
                </div>
              </div>
            ) : status === "on_call" ? (
              <div className="space-y-4">
                <div className="flex flex-col items-center justify-center p-4 bg-gray-50 rounded-lg border border-gray-100">
                  <div className="text-sm text-gray-500 mb-1">Görüşme Süresi</div>
                  <div className="text-3xl font-mono font-medium text-gray-800 tracking-wider">
                    {formatTimer(callDuration)}
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={toggleMute}
                      className={`flex flex-1 items-center justify-center gap-2 rounded-md border px-3 py-2 text-sm font-medium transition-colors ${
                        isMuted
                          ? "border-red-300 bg-red-50 text-red-700 hover:bg-red-100"
                          : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                      }`}
                    >
                      {isMuted ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
                      {isMuted ? "Sesi Aç" : "Sustur"}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setShowDialpad(!showDialpad);
                        setShowTransfer(false);
                      }}
                      className={`flex flex-1 items-center justify-center gap-2 rounded-md border px-3 py-2 text-sm font-medium transition-colors ${
                        showDialpad
                          ? "border-indigo-300 bg-indigo-50 text-indigo-700 hover:bg-indigo-100"
                          : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                      }`}
                    >
                      <Grid className="h-4 w-4" />
                      Tuş Takımı
                    </button>
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setShowTransfer(!showTransfer);
                        setShowDialpad(false);
                      }}
                      className={`flex flex-1 items-center justify-center gap-2 rounded-md border px-3 py-2 text-sm font-medium transition-colors ${
                        showTransfer
                          ? "border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100"
                          : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                      }`}
                    >
                      <PhoneForwarded className="h-4 w-4" />
                      Aktar
                    </button>
                    <div className="flex w-full gap-2 mt-2">
                      <select
                        className="flex-1 rounded-md border-gray-300 text-sm py-1.5 focus:border-emerald-500 focus:ring-emerald-500"
                        onChange={(e) => {
                          if (e.target.value) {
                            sendWhatsAppTemplate(e.target.value);
                            e.target.value = ""; // reset after send
                          }
                        }}
                        disabled={sendingWhatsapp}
                      >
                        <option value="">WhatsApp Gönder...</option>
                        <option value="welcome_location">Lokasyon & Karşılama</option>
                        <option value="reservation_confirmation">Rezervasyon Onayı</option>
                        <option value="satisfaction_survey">Memnuniyet Anketi</option>
                      </select>
                    </div>
                  </div>
                </div>
                {showTransfer && (
                  <div className="p-3 bg-amber-50 rounded-md border border-amber-100 flex flex-col gap-2">
                    <label className="text-xs font-medium text-amber-800">Aktarılacak Hedef</label>
                    <div className="flex flex-col gap-2">
                      <select 
                        className="w-full rounded-md border-gray-300 text-sm py-1.5 focus:border-amber-500 focus:ring-amber-500"
                        onChange={(e) => setTransferTarget(e.target.value)}
                        value={transferTarget.startsWith("client:") ? transferTarget : "custom"}
                      >
                        <option value="">-- Hedef Seçin --</option>
                        <option value="client:reception">Resepsiyon</option>
                        <option value="client:restaurant">Restoran</option>
                        <option value="client:spa">Spa & Wellness</option>
                        <option value="client:concierge">Concierge</option>
                        <option value="custom">Diğer Numara (Dış Hat)...</option>
                      </select>
                      
                      {(!transferTarget.startsWith("client:") || transferTarget === "custom") && (
                        <input
                          type="text"
                          value={transferTarget === "custom" ? "" : transferTarget}
                          onChange={(e) => setTransferTarget(e.target.value)}
                          className="w-full rounded-md border-gray-300 shadow-sm focus:border-amber-500 focus:ring-amber-500 sm:text-sm px-3 py-2"
                          placeholder="+90555... veya dahili"
                        />
                      )}
                      
                      <button
                        onClick={transferCall}
                        disabled={transferring || !transferTarget || transferTarget === "custom"}
                        className="w-full bg-amber-600 text-white px-3 py-2 rounded-md text-sm font-medium hover:bg-amber-700 disabled:opacity-50 mt-1"
                      >
                        {transferring ? 'Aktarılıyor...' : 'Çağrıyı Aktar'}
                      </button>
                    </div>
                  </div>
                )}
                {showDialpad && (
                  <div className="grid grid-cols-3 gap-2 p-2 bg-gray-50 rounded-md border border-gray-100">
                    {['1', '2', '3', '4', '5', '6', '7', '8', '9', '*', '0', '#'].map((digit) => (
                      <button
                        key={digit}
                        type="button"
                        onClick={() => {
                          if (callRef.current) callRef.current.sendDigits(digit);
                        }}
                        className="flex items-center justify-center h-10 bg-white border border-gray-200 rounded-md shadow-sm text-lg font-medium text-gray-700 hover:bg-gray-50 active:bg-gray-100"
                      >
                        {digit}
                      </button>
                    ))}
                  </div>
                )}
                <button
                  type="button"
                  onClick={endCall}
                  className="w-full rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-700"
                >
                  Görüşmeyi sonlandır
                </button>
              </div>
            ) : status === "ready" ? (
              <div className="space-y-2">
                <label className="block text-xs font-medium text-gray-600">
                  Aranacak numara
                </label>
                <input
                  type="tel"
                  inputMode="tel"
                  value={dialNumber}
                  onChange={(e) => setDialNumber(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") startCall();
                  }}
                  placeholder="+90 5XX XXX XX XX"
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:border-gray-500 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={startCall}
                  disabled={!dialNumber.trim()}
                  className="w-full rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500"
                >
                  Ara
                </button>
                <button
                  type="button"
                  onClick={deactivate}
                  className="w-full flex items-center justify-center gap-2 rounded-md border border-gray-300 bg-amber-50 text-amber-700 px-3 py-2 text-sm font-medium hover:bg-amber-100 transition-colors"
                >
                  <span className="w-2 h-2 rounded-full bg-amber-500"></span>
                  Molaya Çık (Çevrimdışı)
                </button>
              </div>
            ) : status === "activating" ? (
              <button
                type="button"
                disabled
                className="w-full cursor-not-allowed rounded-md bg-gray-200 px-3 py-2 text-sm font-medium text-gray-500"
              >
                Etkinleştiriliyor...
              </button>
            ) : (
              <button
                type="button"
                onClick={activate}
                disabled={!isReadyToActivate}
                className={`w-full flex items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isReadyToActivate 
                    ? "bg-emerald-600 text-white hover:bg-emerald-700" 
                    : "bg-gray-200 text-gray-500 cursor-not-allowed"
                }`}
              >
                <span className={`w-2 h-2 rounded-full ${isReadyToActivate ? "bg-white" : "bg-gray-400"}`}></span>
                {isReadyToActivate ? "Müsait (Çevrimiçi Ol)" : "Telefon hazırlanıyor..."}
              </button>
            )}
          </div>
          )}
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className={`flex h-12 w-12 items-center justify-center rounded-full text-white shadow-lg ${
            status === "incoming"
              ? "animate-pulse bg-amber-500"
              : status === "ready" || status === "on_call"
                ? "bg-emerald-600"
                : "bg-black hover:bg-gray-800"
          }`}
          aria-label="Softphone"
          title="Softphone"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="currentColor"
            className="h-5 w-5"
          >
            <path d="M6.62 10.79a15.05 15.05 0 0 0 6.59 6.59l2.2-2.2a1 1 0 0 1 1.02-.24 11.36 11.36 0 0 0 3.57.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.57a1 1 0 0 1-.25 1.02l-2.2 2.2z" />
          </svg>
        </button>
      )}
    </div>
  );
}
