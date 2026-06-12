import React, { useEffect, useState } from 'react';
import { Modal, Pressable, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuthStore } from '../state/authStore';
import { useTheme } from '../theme';
import { useKeepAwakeSafe } from '../hooks/useKeepAwakeSafe';
import { tr } from '../i18n/tr';

// Gece Ekrani: gece vardiyasinda cihazi karartmak isteyenler icin opsiyonel,
// tamamen istemci-tarafi gorsel bir tam-ekran siyah katman (web'deki
// NightScreen ile ayni davranis). Hicbir veri/oturum/auth durumuna dokunmaz;
// authStore yalnizca render kapisi olarak OKUNUR.
//
// Tek mount noktasi (app/_layout.tsx RootShell) ile her ekrandan erisilebilir:
// kucuk yuzen Ay butonu (sol-alt, home tab bar'inin uzerinde) + RN Modal siyah
// katman. Modal RN'de kok seviyeye portallenir -> her seyin uzerinde tam-ekran
// kaplar. Katmana dokunma veya Android donanim geri tusu ile cikilir.

function pad(n: number): string {
  return n < 10 ? `0${n}` : `${n}`;
}

// Katman govdesi yalnizca aktifken mount edilir: bu sayede saat interval'i ve
// keep-awake yalnizca ekran acikken calisir, kapaninca (unmount) ikisi de
// otomatik temizlenir. Keep-awake en iyi-caba: olmazsa cihaz normal uyku
// zamanlamasina doner (dim saat kaybolur), islevsellik bozulmaz.
const NightOverlayBody: React.FC<{ onExit: () => void }> = ({ onExit }) => {
  useKeepAwakeSafe('night-screen');
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const clock = `${pad(now.getHours())}:${pad(now.getMinutes())}`;

  return (
    <Pressable
      onPress={onExit}
      accessibilityRole="button"
      accessibilityLabel={tr.app.nightScreen.hint}
      testID="night-screen-overlay"
      style={{
        flex: 1,
        backgroundColor: '#000000',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <Text style={{ color: '#3a3a3a', fontSize: 64, fontWeight: '200', letterSpacing: 2 }}>
        {clock}
      </Text>
      <Text style={{ color: '#262626', fontSize: 13, marginTop: 16 }}>
        {tr.app.nightScreen.hint}
      </Text>
    </Pressable>
  );
};

export const NightScreen: React.FC = () => {
  const c = useTheme();
  const insets = useSafeAreaInsets();
  const user = useAuthStore((s) => s.user);
  const role = useAuthStore((s) => s.role);
  const [active, setActive] = useState(false);

  // Giris yapilmadan (login ekrani) ve misafir deneyiminde gosterme — web'de de
  // gece ekrani yalnizca kimlik dogrulanmis PERSONEL kabugunda bulunur.
  if (!user || role === 'guest_app') return null;

  return (
    <>
      <Pressable
        onPress={() => setActive(true)}
        accessibilityRole="button"
        accessibilityLabel={tr.app.nightScreen.title}
        testID="night-screen-trigger"
        hitSlop={8}
        style={{
          position: 'absolute',
          left: 16,
          // Home tab bar'i (60 + insets.bottom) net asar; tab bari olmayan
          // gruplarda da alttan rahat bir bosluk birakir.
          bottom: insets.bottom + 72,
          width: 44,
          height: 44,
          borderRadius: 22,
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: c.surfaceGlass,
          borderWidth: 1,
          borderColor: c.border,
        }}
      >
        <Ionicons name="moon-outline" size={20} color={c.textMuted} />
      </Pressable>

      <Modal
        visible={active}
        transparent={false}
        animationType="fade"
        statusBarTranslucent
        onRequestClose={() => setActive(false)}
      >
        {active ? <NightOverlayBody onExit={() => setActive(false)} /> : null}
      </Modal>
    </>
  );
};

export default NightScreen;
