import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/hooks/use-toast';
import { useWebSocket } from '@/lib/websocket';
import { Send, RefreshCw, ChevronLeft, Loader2, MessageSquare } from 'lucide-react';
import { useVisibilityAwarePoller } from './hooks/useVisibilityAwarePoller';
import { POLL_INTERVAL_MS } from './constants';

// QR kategori id -> TR etiket (sohbette ikincil bilgi; bilinmeyen değer
// olduğu gibi gösterilir).
const CATEGORY_TR = {
  rooms: 'Oda / Temizlik',
  minibar: 'Minibar',
  laundry: 'Çamaşır',
  technical: 'Teknik',
  fnb: 'Yiyecek & İçecek',
  spa: 'Spa',
  transportation: 'Ulaşım',
  other: 'Diğer',
};

function fmtTime(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString('tr-TR', {
      day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return '';
  }
}

/**
 * Personel iç-sohbetinde "Misafir Talepleri" akışı (oda-grupli).
 *
 * Kendi durumunu yöneten bağımsız panel: thread listesi <-> oda thread'i.
 * Misafir QR taleplerini oda numarasına göre gruplar; personel yanıtı misafire
 * görünür. Görünürlük server-side ACL (require_guest_request_access) ile çift
 * korumalı; bu panel yalnızca yetkili kullanıcıya render edilir.
 *
 * `onUnreadChange` üst widget'taki sekme rozetini günceller.
 */
export default function GuestRequestsPanel({ onUnreadChange }) {
  const { toast } = useToast();
  const { on: wsOn } = useWebSocket();

  const [threads, setThreads] = useState([]);
  const [loadingThreads, setLoadingThreads] = useState(false);
  const [selectedRoomId, setSelectedRoomId] = useState(null);
  const [selectedRoomNumber, setSelectedRoomNumber] = useState('');
  const [messages, setMessages] = useState([]);
  const [loadingThread, setLoadingThread] = useState(false);
  const [reply, setReply] = useState('');
  const [sending, setSending] = useState(false);

  const isMountedRef = useRef(true);
  const scrollRef = useRef(null);
  const selectedRoomIdRef = useRef(null);

  useEffect(() => {
    selectedRoomIdRef.current = selectedRoomId;
  }, [selectedRoomId]);

  const loadThreads = useCallback(async (silent = false) => {
    if (!silent) setLoadingThreads(true);
    try {
      const res = await axios.get('/messaging/guest-requests/threads');
      if (!isMountedRef.current) return;
      setThreads(res.data?.threads || []);
      onUnreadChange?.(res.data?.total_unread || 0);
    } catch (err) {
      if (!silent) {
        toast({
          title: 'Misafir talepleri yüklenemedi',
          description: err.response?.data?.detail || err.message || 'Bilinmeyen hata',
          variant: 'destructive',
        });
      }
    } finally {
      if (!silent && isMountedRef.current) setLoadingThreads(false);
    }
  }, [onUnreadChange, toast]);

  const loadThread = useCallback(async (roomId, { silent = false, markRead = false } = {}) => {
    if (!roomId) return;
    if (!silent) setLoadingThread(true);
    try {
      const res = await axios.get(
        `/messaging/guest-requests/threads/${encodeURIComponent(roomId)}`,
      );
      if (!isMountedRef.current || selectedRoomIdRef.current !== roomId) return;
      setMessages(res.data?.messages || []);
      if (res.data?.room_number) setSelectedRoomNumber(res.data.room_number);
      if (markRead) {
        try {
          await axios.post(
            `/messaging/guest-requests/threads/${encodeURIComponent(roomId)}/mark-read`,
          );
          loadThreads(true);
        } catch { /* non-fatal */ }
      }
    } catch (err) {
      if (!silent) {
        toast({
          title: 'Konuşma yüklenemedi',
          description: err.response?.data?.detail || err.message || 'Bilinmeyen hata',
          variant: 'destructive',
        });
      }
    } finally {
      if (!silent && isMountedRef.current) setLoadingThread(false);
    }
  }, [loadThreads, toast]);

  const openRoom = useCallback((th) => {
    setSelectedRoomId(th.room_id);
    setSelectedRoomNumber(th.room_number || '');
    setMessages([]);
    setReply('');
    loadThread(th.room_id, { markRead: true });
  }, [loadThread]);

  const backToList = useCallback(() => {
    setSelectedRoomId(null);
    setSelectedRoomNumber('');
    setMessages([]);
    setReply('');
    loadThreads(true);
  }, [loadThreads]);

  const sendReply = useCallback(async () => {
    const text = reply.trim();
    if (!text || !selectedRoomId || sending) return;
    setSending(true);
    try {
      await axios.post(
        `/messaging/guest-requests/threads/${encodeURIComponent(selectedRoomId)}/reply`,
        { message: text },
      );
      if (!isMountedRef.current) return;
      setReply('');
      loadThread(selectedRoomId, { silent: true });
      loadThreads(true);
    } catch (err) {
      toast({
        title: 'Yanıt gönderilemedi',
        description: err.response?.data?.detail || err.message || 'Bilinmeyen hata',
        variant: 'destructive',
      });
    } finally {
      if (isMountedRef.current) setSending(false);
    }
  }, [reply, selectedRoomId, sending, loadThread, loadThreads, toast]);

  useEffect(() => {
    isMountedRef.current = true;
    loadThreads();
    return () => { isMountedRef.current = false; };
  }, [loadThreads]);

  // Websocket içeriksiz ping — yetkili istemci REST'ten tazeler.
  useEffect(() => {
    const off = wsOn('guest_requests:updated', () => {
      loadThreads(true);
      const open = selectedRoomIdRef.current;
      if (open) loadThread(open, { silent: true, markRead: true });
    });
    return off;
  }, [wsOn, loadThreads, loadThread]);

  // Polling güvenlik ağı (60s; sekme arka plana geçince durur).
  useVisibilityAwarePoller(
    useCallback(() => loadThreads(true), [loadThreads]),
    { intervalMs: POLL_INTERVAL_MS },
  );
  useVisibilityAwarePoller(
    useCallback(() => {
      if (selectedRoomId) loadThread(selectedRoomId, { silent: true, markRead: true });
    }, [selectedRoomId, loadThread]),
    { enabled: !!selectedRoomId, intervalMs: POLL_INTERVAL_MS },
  );

  useEffect(() => {
    if (!scrollRef.current) return;
    const node = scrollRef.current;
    requestAnimationFrame(() => { node.scrollTop = node.scrollHeight; });
  }, [messages]);

  if (selectedRoomId) {
    return (
      <div className="flex flex-col h-full min-h-0" data-testid="guest-requests-panel">
        <div className="flex items-center gap-2 px-2.5 py-2 border-b shrink-0">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={backToList}
            data-testid="button-gr-back"
            title="Listeye dön"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <div className="min-w-0">
            <div className="text-sm font-semibold truncate">
              Oda {selectedRoomNumber || '?'}
            </div>
            <div className="text-[11px] text-muted-foreground">Misafir talebi</div>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 ml-auto"
            onClick={() => loadThread(selectedRoomId, { markRead: true })}
            disabled={loadingThread}
            data-testid="button-gr-refresh-thread"
            title="Yenile"
          >
            <RefreshCw className={`h-4 w-4 ${loadingThread ? 'animate-spin' : ''}`} />
          </Button>
        </div>

        <div
          ref={scrollRef}
          className="flex-1 min-h-0 overflow-y-auto p-3 space-y-2"
          data-testid="gr-thread-messages"
        >
          {loadingThread && messages.length === 0 ? (
            <div className="flex items-center justify-center py-10 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
          ) : messages.length === 0 ? (
            <div className="text-center text-sm text-muted-foreground py-10">
              Bu odada henüz mesaj yok.
            </div>
          ) : (
            messages.map((m) => {
              const isGuest = m.sender_type === 'guest';
              return (
                <div key={m.id} className={`flex ${isGuest ? 'justify-start' : 'justify-end'}`}>
                  <div
                    className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${isGuest ? 'bg-muted text-foreground' : 'bg-foreground text-background'}`}
                  >
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="text-[11px] font-medium opacity-80">
                        {isGuest ? (m.sender_name || 'Misafir') : (m.sender_name || 'Personel')}
                      </span>
                      {m.category && (
                        <span className="text-[10px] opacity-60">
                          {CATEGORY_TR[m.category] || m.category}
                        </span>
                      )}
                    </div>
                    <div className="whitespace-pre-wrap break-words">{m.body}</div>
                    <div className="text-[10px] opacity-60 mt-0.5 text-right">
                      {fmtTime(m.created_at)}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        <div className="border-t p-2.5 shrink-0 space-y-1.5">
          <div className="text-[11px] text-amber-600">Bu yanıt misafire görünür.</div>
          <div className="flex items-end gap-2">
            <Textarea
              value={reply}
              onChange={(e) => setReply(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendReply(); }
              }}
              placeholder="Misafire yanıt yazın..."
              rows={2}
              className="resize-none"
              data-testid="input-gr-reply"
            />
            <Button
              type="button"
              onClick={sendReply}
              disabled={!reply.trim() || sending}
              size="icon"
              className="h-9 w-9 shrink-0"
              data-testid="button-gr-send"
              title="Gönder"
            >
              {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full min-h-0" data-testid="guest-requests-panel">
      <div className="flex items-center px-2.5 py-2 border-b shrink-0">
        <div className="text-xs text-muted-foreground">
          Oda numarasına göre misafir talepleri
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 ml-auto"
          onClick={() => loadThreads()}
          disabled={loadingThreads}
          data-testid="button-gr-refresh-list"
          title="Yenile"
        >
          <RefreshCw className={`h-4 w-4 ${loadingThreads ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto" data-testid="gr-threads-list">
        {loadingThreads && threads.length === 0 ? (
          <div className="flex items-center justify-center py-10 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        ) : threads.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
            <MessageSquare className="h-8 w-8 mb-2 opacity-40" />
            <div className="text-sm">Henüz misafir talebi yok.</div>
          </div>
        ) : (
          threads.map((th) => (
            <button
              key={th.room_id}
              type="button"
              onClick={() => openRoom(th)}
              data-testid={`gr-thread-${th.room_id}`}
              className="w-full text-left px-3 py-2.5 border-b hover:bg-muted/60 transition-colors flex items-center gap-3"
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold">
                {th.room_number || '?'}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium truncate">Oda {th.room_number || '?'}</span>
                  {th.last_category && (
                    <span className="text-[10px] text-muted-foreground">
                      {CATEGORY_TR[th.last_category] || th.last_category}
                    </span>
                  )}
                </div>
                <div className="text-xs text-muted-foreground truncate">
                  {th.last_sender_type === 'staff' ? 'Siz: ' : ''}{th.last_body || ''}
                </div>
              </div>
              <div className="flex flex-col items-end gap-1 shrink-0">
                <span className="text-[10px] text-muted-foreground">{fmtTime(th.last_created_at)}</span>
                {(th.unread || 0) > 0 && (
                  <span className="inline-flex items-center justify-center rounded-full bg-red-500 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-white min-w-[16px]">
                    {th.unread > 99 ? '99+' : th.unread}
                  </span>
                )}
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
