import { AlertTriangle, ArrowLeft, RefreshCw, Settings2, ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

const STATE_CONTENT = {
  empty: {
    icon: Settings2,
    title: "Henüz gösterilecek kayıt yok",
    description: "Filtreleri değiştirin veya ilk kaydı oluşturarak başlayın.",
  },
  forbidden: {
    icon: ShieldAlert,
    title: "Bu ekran için yetkiniz yok",
    description: "Rolünüz veya kullanıcıya özel erişiminiz bu ekranı açmaya yetmiyor. Otel yöneticinizden erişim isteyin.",
  },
  setup: {
    icon: Settings2,
    title: "Kurulum gerekli",
    description: "Bu modül tesisinizde etkin değil veya bağlantısı henüz tamamlanmadı. Paket, modül ve entegrasyon ayarlarını kontrol edin.",
  },
  error: {
    icon: AlertTriangle,
    title: "Veriler şu anda yüklenemiyor",
    description: "Mevcut kayıtlarınız etkilenmedi. Bağlantı düzeldiğinde yeniden deneyebilirsiniz.",
  },
  throttled: {
    icon: AlertTriangle,
    title: "İstek sınırına ulaşıldı",
    description: "Çok fazla istek gönderildi. Biraz bekleyip yeniden deneyin.",
  },
};

/**
 * Product-wide state contract for every operational workspace.
 *
 * State type, accessible announcement and recovery controls are intentionally
 * central: routes and individual modules must not invent a different meaning
 * for an empty result, denied access, incomplete setup or transient failure.
 */
export default function ProductState({
  state = "error",
  moduleName,
  title,
  titleKey,
  titleDefaultValue,
  description,
  descriptionKey,
  descriptionDefaultValue,
  onRetry,
  retryLabel,
  retryLabelKey,
  retryDefaultValue,
  retryTestId,
  action,
  actionLabel,
  compact = false,
  showDashboardLink = true,
}) {
  const { t } = useTranslation();
  const content = STATE_CONTENT[state] || STATE_CONTENT.error;
  const Icon = content.icon;
  const key = `uiQuality.states.${state}`;
  const resolvedTitle = title || t(titleKey || `${key}.title`, { defaultValue: titleDefaultValue || content.title });
  const resolvedDescription = description || t(descriptionKey || `${key}.description`, {
    defaultValue: descriptionDefaultValue || (moduleName ? `${moduleName}: ${content.description}` : content.description),
    moduleName,
  });
  const isCompact = compact;

  return (
    <section
      data-testid="product-state"
      data-state={state}
      role={state === "error" || state === "forbidden" ? "alert" : "status"}
      aria-live="polite"
      className={isCompact ? "rounded-xl border border-slate-200 bg-white p-5" : "flex min-h-[45vh] items-center justify-center p-6"}
    >
      <div className={isCompact ? "flex max-w-2xl items-start gap-3" : "w-full max-w-xl rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm"}>
        <div className="rounded-full bg-slate-100 p-3 text-slate-700"><Icon aria-hidden="true" className="h-6 w-6" /></div>
        <div className={isCompact ? "flex-1" : "mt-4"}>
          <h2 className="text-lg font-semibold text-slate-900">{resolvedTitle}</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">{resolvedDescription}</p>
          {(onRetry || action || (!isCompact && showDashboardLink)) && (
            <div className={`mt-5 flex flex-wrap gap-2 ${isCompact ? "" : "justify-center"}`}>
              {onRetry && <Button data-testid={retryTestId} type="button" onClick={onRetry} variant="outline"><RefreshCw className="mr-2 h-4 w-4" />{retryLabel || t(retryLabelKey || "uiQuality.actions.retry", { defaultValue: retryDefaultValue || "Yeniden dene" })}</Button>}
              {action && <Button type="button" onClick={action}>{actionLabel || t("uiQuality.actions.continue", { defaultValue: "Devam et" })}</Button>}
              {!isCompact && showDashboardLink && <Button asChild variant="ghost"><a href="/app/dashboard"><ArrowLeft className="mr-2 h-4 w-4" />{t("uiQuality.actions.backToDashboard", { defaultValue: "Kontrol paneline dön" })}</a></Button>}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

export { STATE_CONTENT };
