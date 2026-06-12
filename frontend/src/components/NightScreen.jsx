import React, { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { Moon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

// Gece ekranı: resepsiyonun gece vardiyasında ekrani karartmak isteyenler icin
// tum gorunumu kaplayan siyah bir katman. Uzerinde sadece dim bir saat ve
// cikis ipucu gosterilir; herhangi bir yere dokunmak veya ESC'e basmak ile
// aninda calismaya geri donulur. Hicbir veri/oturum durumu degismez.
const NightScreen = () => {
  const [active, setActive] = useState(false);
  const [visible, setVisible] = useState(false);
  const [now, setNow] = useState(() => new Date());

  const exit = useCallback(() => setActive(false), []);

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

  const hh = String(now.getHours()).padStart(2, '0');
  const mm = String(now.getMinutes()).padStart(2, '0');

  return (
    <>
      <TooltipProvider delayDuration={300}>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setActive(true)}
              className="h-8 w-8 p-0 text-gray-600 hover:bg-gray-100"
              data-testid="night-screen-button"
              aria-label="Gece Ekranı"
            >
              <Moon className="w-4 h-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p>Gece Ekranı</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      {active && createPortal(
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
          <div className="text-neutral-600 text-7xl md:text-8xl font-light tabular-nums tracking-wider">
            {hh}:{mm}
          </div>
          <p className="mt-6 text-neutral-700 text-xs uppercase tracking-[0.3em]">
            Çıkmak için dokunun veya ESC
          </p>
        </div>,
        document.body,
      )}
    </>
  );
};

export default NightScreen;
