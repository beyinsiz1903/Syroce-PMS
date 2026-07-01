import { useEffect, useRef } from 'react';
import { websocket, useWebSocket } from '@/lib/websocket';
import { TYPING_INDICATOR_TTL_MS } from '../constants';

/**
 * Personel mesajlaşması için Socket.IO event'lerini tek bir noktadan dinler.
 * Üç ayrı useEffect (inbox+thread mesaj akışı, read receipt, typing) burada
 * konsolide. `selectedConvUserIdRef` parent'ta kalır — handler'lar her render
 * tazelenmeden açık thread'i okuyabilsin diye ref geçiyoruz.
 */
export function useChatRealtime({
  currentUser,
  selectedConvUserIdRef,
  setInbox,
  setUnreadCount,
  setThreadMessages,
  setTypingPartnerName,
}) {
  // Task #43: pass no room — the server auto-enrols the socket in
  // tenant-scoped internal_chat / pms rooms at connect time based on
  // the JWT identity. Passing the legacy global 'pms' room used to
  // be silently denied by the protected-room guard.
  const { on: wsOn } = useWebSocket();
  const typingClearTimerRef = useRef(null);

  // Yeni mesaj + güncellenen mesaj akışı (`internal_message`, `internal_message_updated`).
  useEffect(() => {
    let teardown = null;
    let cancelled = false;

    const onMessage = (envelope) => {
      const msg = envelope?.message;
      if (!msg) return;
      const fromMe = msg.from_user_id && currentUser?.id && msg.from_user_id === currentUser.id;

      setInbox((prev) => {
        if (prev.some((m) => m.id === msg.id)) return prev;
        return [{ ...msg, time_ago: msg.time_ago || 'şimdi' }, ...prev].slice(0, 200);
      });

      if (!fromMe && !msg.read) {
        setUnreadCount((c) => c + 1);
      }

      const openPartner = selectedConvUserIdRef.current;
      if (openPartner) {
        const partnerId = fromMe ? msg.to_user_id : msg.from_user_id;
        if (partnerId && partnerId === openPartner) {
          setThreadMessages((prev) => {
            if (prev.some((m) => m.id === msg.id)) return prev;
            return [...prev, { ...msg, time_ago: msg.time_ago || 'şimdi' }];
          });
        }
      }
    };

    const onMessageUpdate = (envelope) => {
      const msg = envelope?.message;
      if (!msg || !msg.id) return;
      const patch = (m) => (m.id === msg.id
        ? { ...m, message: msg.message, edited: !!msg.edited, edited_at: msg.edited_at || m.edited_at }
        : m);
      setInbox((prev) => prev.map(patch));
      setThreadMessages((prev) => prev.map(patch));
    };

    (async () => {
      try {
        await websocket.connect();
        if (cancelled) return;
        const off1 = websocket.on('internal_message', onMessage);
        const off2 = websocket.on('internal_message_updated', onMessageUpdate);
        teardown = () => { if (off1) off1(); if (off2) off2(); };
      } catch {
        /* noop — polling fallback devrede */
      }
    })();

    return () => {
      cancelled = true;
      if (teardown) teardown();
    };
  }, [currentUser?.id, selectedConvUserIdRef, setInbox, setUnreadCount, setThreadMessages]);

  // Read receipt: karşı taraf okuyunca ✓✓ anında dönsün.
  useEffect(() => {
    const myId = currentUser?.id;
    if (!myId) return undefined;
    const off = wsOn('internal_message_read', (data) => {
      if (!data || data.sender_id !== myId) return;
      const readerId = data.reader_id;
      const ids = Array.isArray(data.message_ids) ? data.message_ids : [];
      if (selectedConvUserIdRef.current !== readerId) return;
      setThreadMessages((prev) => prev.map((m) => {
        if (!m.is_from_me) return m;
        if (ids.length === 0 || ids.includes(m.id)) return { ...m, read: true };
        return m;
      }));
    });
    return off;
  }, [wsOn, currentUser?.id, selectedConvUserIdRef, setThreadMessages]);

  // "Yazıyor…" indicator — TTL ile otomatik temizlenir.
  useEffect(() => {
    const myId = currentUser?.id;
    if (!myId) return undefined;
    const off = wsOn('internal_user_typing', (data) => {
      if (!data) return;
      if (data.to_user_id !== myId) return;
      if (data.from_user_id !== selectedConvUserIdRef.current) return;
      if (data.is_typing === false) {
        setTypingPartnerName('');
        if (typingClearTimerRef.current) {
          clearTimeout(typingClearTimerRef.current);
          typingClearTimerRef.current = null;
        }
        return;
      }
      setTypingPartnerName(data.from_user_name || 'Kullanıcı');
      if (typingClearTimerRef.current) clearTimeout(typingClearTimerRef.current);
      typingClearTimerRef.current = setTimeout(() => {
        setTypingPartnerName('');
        typingClearTimerRef.current = null;
      }, TYPING_INDICATOR_TTL_MS);
    });
    return off;
  }, [wsOn, currentUser?.id, selectedConvUserIdRef, setTypingPartnerName]);

  // Unmount'ta sarkan typing timer'ı temizle.
  useEffect(() => () => {
    if (typingClearTimerRef.current) clearTimeout(typingClearTimerRef.current);
  }, []);
}
