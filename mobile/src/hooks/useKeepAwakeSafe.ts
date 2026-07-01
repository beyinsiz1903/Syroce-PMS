import { useEffect, useId } from 'react';
import { activateKeepAwakeAsync, deactivateKeepAwake } from 'expo-keep-awake';

/**
 * useKeepAwake'in web-güvenli sarmalayıcısı.
 *
 * expo-keep-awake web'de `navigator.wakeLock.request('screen')` çağırır. Belge
 * görünür değilken (sekme arka planda) veya headless tarayıcıda (CI smoke)
 * bu çağrı "Wake Lock permission request denied" ile reddeder. Kütüphanenin
 * `useKeepAwake` hook'u bu reddi (hem aktivasyonda hem temizlikte) yakalamadığı
 * için yakalanmamış bir promise reddi -> `pageerror` olarak yüzeye çıkar ve
 * render-only smoke'u kırar (gerçek cihazda değil, yalnızca CI/arka-plan'da).
 *
 * Keep-awake en iyi-çaba bir iyileştirmedir: reddedilirse ekran yalnızca normal
 * uyku zamanlamasına döner, işlevsellik bozulmaz. Bu yüzden aktivasyonu ve
 * deaktivasyonu kendimiz yapıp reddi sessizce yutuyoruz.
 *
 * Tag, kütüphane `useKeepAwake` davranışını birebir korumak için varsayılan
 * olarak bileşene özgü `useId()`'dir — paylaşılan sabit bir tag iki ekran aynı
 * anda mount'luyken (navigator inaktif ekranları mount tutar) kilidi birbirine
 * serbest bıraktırır/sızdırır.
 */
export function useKeepAwakeSafe(tag?: string): void {
  const fallbackTag = useId();
  const resolvedTag = tag ?? fallbackTag;
  useEffect(() => {
    activateKeepAwakeAsync(resolvedTag).catch(() => {
      // wakeLock reddi (izin / görünürlük) — beklenen, yoksay.
    });
    return () => {
      deactivateKeepAwake(resolvedTag).catch(() => {
        // zaten serbest / desteklenmiyor — yoksay.
      });
    };
  }, [resolvedTag]);
}
