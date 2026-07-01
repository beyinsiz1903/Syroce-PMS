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
import axios from "axios";
import CallHistory from "./CallHistory";

import { SOFTPHONE_DIAL_EVENT } from "@/lib/softphone";

const TWILIO_VOICE_SDK_URL =
  "https://sdk.twilio.com/js/voice/releases/2.12.3/twilio.min.js";

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
  const deviceRef = useRef(null);
  const callRef = useRef(null);

  const role = user?.role || (user?.roles && user.roles[0]);
  const isStaff = role && role !== "guest";

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

  const activate = useCallback(async () => {
    setStatus("activating");
    setDetail("");
    // 1) Mikrofon izni — yalnızca açık kullanıcı eylemiyle.
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      // İzin alındı; canlı track'leri hemen serbest bırak (SDK kendi açar).
      stream.getTracks().forEach((t) => t.stop());
    } catch {
      setStatus("error");
      setDetail("Mikrofon izni reddedildi. Sesli çağrı için izin gerekir.");
      return;
    }

    // 2) Kısa-ömürlü AccessToken — fail-closed.
    let token;
    try {
      const res = await axios.post("/contact-center/voice/token");
      token = res.data?.token;
      if (!token) throw new Error("no_token");
    } catch (err) {
      if (err?.response?.status === 503) {
        setStatus("not_configured");
        setDetail(
          "Sesli arama altyapısı henüz yapılandırılmadı. Yönetici Twilio ayarlarını tamamlayınca aktifleşir.",
        );
      } else if (err?.response?.status === 403) {
        setStatus("error");
        setDetail("Bu işlem için yetkiniz yok.");
      } else {
        setStatus("error");
        setDetail("Token alınamadı. Daha sonra tekrar deneyin.");
      }
      return;
    }

    // 3) SDK + Device — yalnızca şimdi yüklenir.
    try {
      const Twilio = await loadTwilioVoiceSdk();
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
        callRef.current = call;
        setIncomingFrom(call?.parameters?.From || "");
        setStatus("incoming");
        setView("dialer");
        setOpen(true);
        call.on("disconnect", () => {
          callRef.current = null;
          setIncomingFrom("");
          setStatus(deviceRef.current ? "ready" : "idle");
        });
        call.on("cancel", () => {
          callRef.current = null;
          setIncomingFrom("");
          setStatus(deviceRef.current ? "ready" : "idle");
        });
      });

      await device.register();
    } catch {
      setStatus("error");
      setDetail("Sesli arama bileşeni yüklenemedi.");
    }
  }, [teardown]);

  const startCall = useCallback(async (override) => {
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
      const call = await device.connect({ params: { To: target } });
      callRef.current = call;
      setStatus("on_call");
      setDetail("");
      call.on("disconnect", () => {
        callRef.current = null;
        setStatus(deviceRef.current ? "ready" : "idle");
      });
      call.on("cancel", () => {
        callRef.current = null;
        setStatus(deviceRef.current ? "ready" : "idle");
      });
      call.on("error", () => {
        callRef.current = null;
        setStatus(deviceRef.current ? "ready" : "idle");
        setDetail("Çağrı sırasında hata oluştu.");
      });
    } catch {
      setStatus(deviceRef.current ? "ready" : "idle");
      setDetail("Giden çağrı başlatılamadı.");
    }
  }, [dialNumber]);

  // Tek-tıkla arama: misafir/rezervasyon ekranlarındaki "Ara" düğmeleri global
  // ``syroce:softphone-dial`` event'i yayar. Numarayı doldur, paneli aç; hazırsa
  // hemen ara, değilse kullanıcıyı aktivasyona yönlendir.
  useEffect(() => {
    if (!isStaff) return undefined;
    const onDial = (e) => {
      const number = (e?.detail?.number || "").trim();
      if (!number) return;
      setDialNumber(number);
      setOpen(true);
      if (status === "ready") {
        startCall(number);
      } else if (status === "on_call" || status === "incoming") {
        setDetail("Görüşme sürüyor; numara hazır, görüşme bitince arayabilirsiniz.");
      } else {
        setDetail("Numara hazır. Aramak için önce softphone'u aktifleştirin.");
      }
    };
    window.addEventListener("syroce:softphone-dial", onDial);
    return () => window.removeEventListener("syroce:softphone-dial", onDial);
  }, [isStaff, status, startCall]);

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
    try {
      callRef.current?.reject?.();
    } catch {
      /* noop */
    }
    callRef.current = null;
    setIncomingFrom("");
    setStatus(deviceRef.current ? "ready" : "idle");
  }, []);

  const hangUp = useCallback(() => {
    try {
      callRef.current?.disconnect?.();
    } catch {
      /* noop */
    }
    callRef.current = null;
    setStatus(deviceRef.current ? "ready" : "idle");
  }, []);

  const deactivate = useCallback(() => {
    teardown();
    setStatus("idle");
    setDetail("");
    setIncomingFrom("");
  }, [teardown]);

  if (!isStaff) return null;

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
              <button
                type="button"
                onClick={hangUp}
                className="w-full rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-700"
              >
                Görüşmeyi sonlandır
              </button>
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
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  Devre dışı bırak
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
                className="w-full rounded-md bg-black px-3 py-2 text-sm font-medium text-white hover:bg-gray-800"
              >
                Aktifleştir
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
