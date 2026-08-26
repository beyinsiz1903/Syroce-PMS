import { AlertTriangle, ArrowLeft, RefreshCw, Settings2 } from "lucide-react";
import { Button } from "@/components/ui/button";

const SETUP_STATUSES = new Set([402, 403]);

export function moduleLoadState(error) {
  const status = error?.response?.status;
  if (SETUP_STATUSES.has(status)) return "setup";
  if (status === 429) return "throttled";
  return "temporary";
}

export function ModuleAvailabilityState({
  moduleName = "Bu modül",
  reason = "disabled",
  onRetry,
  compact = false,
}) {
  const isSetup = reason === "disabled" || reason === "setup";
  const isThrottled = reason === "throttled";
  const title = isSetup
    ? "Kurulum gerekli"
    : isThrottled
      ? "İstek sınırına ulaşıldı"
      : "Modül şu anda doğrulanamıyor";
  const description = isSetup
    ? `${moduleName} tesisinizde etkin değil veya kullanıcı yetkiniz bulunmuyor. Paket ve yetki ayarlarını kontrol edin.`
    : isThrottled
      ? `${moduleName} kısa süre içinde otomatik olarak yeniden denenmesine rağmen yüklenemedi. Biraz bekleyip tekrar deneyin.`
      : `${moduleName} verilerine şu anda ulaşılamıyor. Mevcut verileriniz etkilenmedi; bağlantı düzeldiğinde yeniden deneyebilirsiniz.`;
  const Icon = isSetup ? Settings2 : AlertTriangle;

  return (
    <div
      data-testid="module-availability-state"
      data-state={reason}
      className={compact
        ? "rounded-xl border border-amber-200 bg-amber-50/60 p-5"
        : "min-h-[45vh] flex items-center justify-center p-6"}
    >
      <div className={compact ? "max-w-2xl" : "w-full max-w-xl rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm"}>
        <div className={compact ? "flex items-start gap-3" : "flex flex-col items-center"}>
          <div className="rounded-full bg-amber-100 p-3 text-amber-700">
            <Icon className="h-6 w-6" />
          </div>
          <div className={compact ? "flex-1" : "mt-4"}>
            <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>
            <div className={`mt-5 flex flex-wrap gap-2 ${compact ? "" : "justify-center"}`}>
              {onRetry && (
                <Button type="button" onClick={onRetry} variant="outline">
                  <RefreshCw className="mr-2 h-4 w-4" /> Yeniden Dene
                </Button>
              )}
              {!compact && (
                <Button asChild variant="ghost">
                  <a href="/app/dashboard">
                    <ArrowLeft className="mr-2 h-4 w-4" /> Kontrol Paneline Dön
                  </a>
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function ModuleLoadError({ moduleName, error, onRetry, compact = false }) {
  return (
    <ModuleAvailabilityState
      moduleName={moduleName}
      reason={moduleLoadState(error)}
      onRetry={onRetry}
      compact={compact}
    />
  );
}
