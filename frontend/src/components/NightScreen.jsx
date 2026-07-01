import React, { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';

// Gece ekrani: resepsiyonun gece vardiyasinda ekrani karartmak icin tum
// gorunumu kaplayan siyah bir katman. Uzerinde sadece dim bir saat ve cikis
// ipucu gosterilir; herhangi bir yere dokunmak veya ESC'e basmak ile aninda
// calismaya geri donulur. Hicbir veri/oturum durumu degismez.
//
// Tetikleme: header'da BUTON YOK. Katman, kullanici belirli bir sure (IDLE_MS)
// HICBIR etkilesim (fare/klavye/dokunma/kaydirma) yapmadiginda OTOMATIK acilir;
// en ufak etkilesimde sayac sifirlanir, ekran acikken dokunma/ESC ile kapanir.
// Durum kalici DEGIL: her oturum temiz (inactive) baslar, idle sayaci karar verir.

// Otomatik gece ekrani esigi: 10 dakika boyunca hicbir etkilesim olmazsa.
const IDLE_MS = 10 * 60 * 1000;

const NightScreen = () => {
  const [active, setActive] = useState(false);
  const [visible, setVisible] = useState(false);
  const [now, setNow] = useState(() => new Date());

  const exit = useCallback(() => setActive(false), []);

  // Otomatik tetikleme: katman KAPALIYKEN bir hareketsizlik sayaci tutulur;
  // her etkilesimde sifirlanir, IDLE_MS dolunca gece ekrani acilir. Katman
  // acikken listener kurulmaz (early return) -> cikis dokunma/ESC ile yapilir.
  useEffect(() => {
    if (active || typeof window === 'undefined') return undefined;
    let timer;
    const schedule = () => {
      clearTimeout(timer);
      timer = setTimeout(() => setActive(true), IDLE_MS);
    };
    const events = ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll', 'wheel'];
    events.forEach((e) => window.addEventListener(e, schedule, { passive: true }));
    schedule();
    return () => {
      clearTimeout(timer);
      events.forEach((e) => window.removeEventListener(e, schedule));
    };
  }, [active]);

  // Katman acikken: saati her saniye guncelle + ESC ile cikis.
  useEffect(() => {
    if (!active) return undefined;
    const tick = setInterval(() => setNow(new Date()), 1000);
    const onKey = (event) => {
      if (event.key === 'Escape') setActive(false);
    };
    window.addEventListener('keydown', onKey);
    return () => {
      clearInterval(tick);
      window.removeEventListener('keydown', onKey);
    };
  }, [active]);

  // Yumusak fade-in (eklenti bagimliligi olmadan opacity gecisi ile).
  useEffect(() => {
    if (active) {
      setNow(new Date());
      const raf = requestAnimationFrame(() => setVisible(true));
      return () => cancelAnimationFrame(raf);
    }
    setVisible(false);
    return undefined;
  }, [active]);

  if (!active) return null;

  const hh = String(now.getHours()).padStart(2, '0');
  const mm = String(now.getMinutes()).padStart(2, '0');

  return createPortal(
    <div
      role="button"
      tabIndex={0}
      aria-label="Gece ekranindan cik"
      onClick={exit}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          exit();
        }
      }}
      className={`fixed inset-0 z-[9999] flex flex-col items-center justify-center bg-black cursor-pointer select-none transition-opacity duration-300 ${
        visible ? 'opacity-100' : 'opacity-0'
      }`}
      data-testid="night-screen-overlay"
    >
      {/* Los renkler arbitrary deger ile sabitlendi: gece-ekrani her zaman
          siyah zemin uzerinde los kalmali; .dark compat katmani arbitrary
          (text-[#...]) siniflarini bilincli olarak ezmez, boylece
          text-neutral-600/700 -> parlak token remap'inden korunur. */}
      <div className="text-[#525252] text-7xl md:text-8xl font-light tabular-nums tracking-wider">
        {hh}:{mm}
      </div>
      <p className="mt-6 text-[#404040] text-xs uppercase tracking-[0.3em]">
        Çıkmak için dokunun veya ESC
      </p>
    </div>,
    document.body,
  );
};

export default NightScreen;
