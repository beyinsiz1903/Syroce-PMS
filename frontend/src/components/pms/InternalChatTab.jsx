import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useToast } from '@/hooks/use-toast';
import { websocket, useWebSocket } from '@/lib/websocket';
import { useNotifications } from '@/context/NotificationContext';
import { canSendUrgentMessage } from '@/utils/authRoles';
import { Send, RefreshCw, MessagesSquare, CheckCheck } from 'lucide-react';

// R4 split: render-helpers extracted into sub-components.
import {
  STAFF_ROLES,
  CONVERSATION_DEPARTMENT_FILTERS,
  POLL_INTERVAL_MS,
  TYPING_INDICATOR_TTL_MS,
  TYPING_EMIT_THROTTLE_MS,
} from './internalChat/constants';
import InboxList from './internalChat/InboxList';
import ComposeForm from './internalChat/ComposeForm';
import ConversationsList from './internalChat/ConversationsList';
import ThreadView from './internalChat/ThreadView';


const InternalChatTab = ({ currentUser }) => {
  const { toast } = useToast();
  // Keep the global bell counter in sync when this tab mutates read state.
  const {
    decrementInternalUnread,
    markAllInternalRead,
  } = useNotifications();
  const { on: wsOn, socketEmit: wsSocketEmit } = useWebSocket('pms');
  const [composeOpen, setComposeOpen] = useState(false);
  const [markingAllRead, setMarkingAllRead] = useState(false);

  // "Acil" mesaj kanalı alıcıda alarm tetiklediği için ayrı bir izinle
  // korunuyor. Yetkisiz roller (front_desk, housekeeping, vb.) bu seçeneği
  // hiç görmesin — backend de aynı kontrolü yapıyor (defense-in-depth).
  // Task #28: rol-bazlı yetki yoksa kullanıcıya tek tek verilen
  // `granted_permissions: ["send_urgent_message"]` izni de kabul edilir.
  const canSendUrgent = useMemo(
    () => canSendUrgentMessage(currentUser),
    [currentUser],
  );

  const [inbox, setInbox] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [myDepartment, setMyDepartment] = useState('');
  const [loadingInbox, setLoadingInbox] = useState(false);
  const [showUnreadOnly, setShowUnreadOnly] = useState(false);

  const [users, setUsers] = useState([]);
  const [usersLoaded, setUsersLoaded] = useState(false);
  const [usersAccessDenied, setUsersAccessDenied] = useState(false);

  const [recipientType, setRecipientType] = useState('department');
  const [toDepartment, setToDepartment] = useState('Reception');
  const [toUserId, setToUserId] = useState('');
  const [userSearch, setUserSearch] = useState('');
  const [userDeptFilter, setUserDeptFilter] = useState('all');
  // Task #25: "Sadece çevrimiçi personeli göster" filtresi.
  // `onlineUsers` bir Set<string> tutar; presence endpoint'i her dialog
  // açıldığında ve toggle her açılıp kapatıldığında yeniden çekilir.
  // Endpoint patlarsa boş set'le degrade ederiz — toggle hâlâ çalışır
  // ama "Eşleşen kullanıcı yok" gösterir, sessiz hata UX'i bozmaz.
  const [onlineOnly, setOnlineOnly] = useState(false);
  const [onlineUsers, setOnlineUsers] = useState(() => new Set());
  const [messageText, setMessageText] = useState('');
  const [priority, setPriority] = useState('normal');
  const [sending, setSending] = useState(false);

  const [conversations, setConversations] = useState([]);
  const [loadingConversations, setLoadingConversations] = useState(false);
  const [selectedConvUserId, setSelectedConvUserId] = useState(null);
  const [selectedConvUserName, setSelectedConvUserName] = useState('');
  const [threadMessages, setThreadMessages] = useState([]);
  const [loadingThread, setLoadingThread] = useState(false);
  const [threadReply, setThreadReply] = useState('');
  const [threadPriority, setThreadPriority] = useState('normal');
  const [sendingThreadReply, setSendingThreadReply] = useState(false);
  const [urgentConfirmOpen, setUrgentConfirmOpen] = useState(false);
  // Inline edit state — at most one message per thread can be in edit mode at
  // a time. `editingDraft` mirrors the textarea so the user can cancel
  // without losing their place in the thread.
  const [editingMessageId, setEditingMessageId] = useState(null);
  const [editingDraft, setEditingDraft] = useState('');
  const [savingEdit, setSavingEdit] = useState(false);
  // Task #39: per-message edit-history cache. The popover is opened on
  // demand so we don't prefetch history for every "(düzenlendi)" badge in
  // a long thread; once loaded for a message we keep the result so
  // re-opening the popover is instant.
  // Shape: { [messageId]: { loading: boolean, error: string|null,
  //                          history: Array, current_message: string } }
  const [editHistoryByMsg, setEditHistoryByMsg] = useState({});
  const [conversationSearch, setConversationSearch] = useState('');
  const [conversationDeptFilter, setConversationDeptFilter] = useState('all');
  const [conversationOnlyUnread, setConversationOnlyUnread] = useState(false);
  // Task #30: badge tıklayınca dropdown'ı programmatik olarak kapatabilmek
  // için Select'i controlled yapıyoruz.
  const [conversationDeptOpen, setConversationDeptOpen] = useState(false);

  // Live "yazıyor…" indicator — partner_id of the user currently typing
  // to me in the open thread. Auto-clears after TYPING_INDICATOR_TTL_MS.
  const [typingPartnerName, setTypingPartnerName] = useState('');

  const pollTimerRef = useRef(null);
  const conversationPollTimerRef = useRef(null);
  const threadPollTimerRef = useRef(null);
  const threadScrollRef = useRef(null);
  const isMountedRef = useRef(true);
  const inboxRequestIdRef = useRef(0);
  const inboxAbortRef = useRef(null);
  const conversationsRequestIdRef = useRef(0);
  const conversationsAbortRef = useRef(null);
  const threadRequestIdRef = useRef(0);
  const threadAbortRef = useRef(null);
  // Refs that don't trigger re-renders — used by WS handlers and the
  // throttled typing emitter.
  const selectedConvUserIdRef = useRef(null);
  const typingClearTimerRef = useRef(null);
  const lastTypingEmitRef = useRef(0);

  useEffect(() => {
    selectedConvUserIdRef.current = selectedConvUserId;
    // Switching threads clears any stale "yazıyor…" indicator from the
    // previous partner.
    setTypingPartnerName('');
    if (typingClearTimerRef.current) {
      clearTimeout(typingClearTimerRef.current);
      typingClearTimerRef.current = null;
    }
  }, [selectedConvUserId]);

  const loadInbox = useCallback(async (silent = false) => {
    // Cancel any in-flight inbox request — prevents stale responses from
    // overwriting state when the filter changes faster than the network.
    if (inboxAbortRef.current) {
      inboxAbortRef.current.abort();
    }
    const controller = new AbortController();
    inboxAbortRef.current = controller;
    const requestId = ++inboxRequestIdRef.current;

    if (!silent) setLoadingInbox(true);
    try {
      const res = await axios.get('/messaging/internal/inbox', {
        params: { limit: 100, unread_only: showUnreadOnly },
        signal: controller.signal,
      });
      // Drop the response if a newer request superseded this one or component unmounted
      if (
        !isMountedRef.current ||
        requestId !== inboxRequestIdRef.current ||
        controller.signal.aborted
      ) {
        return;
      }
      setInbox(res.data?.messages || []);
      setUnreadCount(res.data?.unread_count || 0);
      setMyDepartment(res.data?.my_department || '');
    } catch (err) {
      if (axios.isCancel?.(err) || err.name === 'CanceledError' || err.name === 'AbortError') {
        return;
      }
      if (!silent) {
        toast({
          title: 'Gelen kutusu yüklenemedi',
          description: err.response?.data?.detail || err.message || 'Bilinmeyen hata',
          variant: 'destructive',
        });
      }
    } finally {
      if (
        !silent &&
        isMountedRef.current &&
        requestId === inboxRequestIdRef.current
      ) {
        setLoadingInbox(false);
      }
    }
  }, [showUnreadOnly, toast]);

  const loadConversations = useCallback(async (silent = false) => {
    if (conversationsAbortRef.current) {
      conversationsAbortRef.current.abort();
    }
    const controller = new AbortController();
    conversationsAbortRef.current = controller;
    const requestId = ++conversationsRequestIdRef.current;

    if (!silent) setLoadingConversations(true);
    try {
      const res = await axios.get('/messaging/internal/conversations', {
        signal: controller.signal,
      });
      if (
        !isMountedRef.current ||
        requestId !== conversationsRequestIdRef.current ||
        controller.signal.aborted
      ) {
        return;
      }
      setConversations(res.data?.conversations || []);
    } catch (err) {
      if (axios.isCancel?.(err) || err.name === 'CanceledError' || err.name === 'AbortError') {
        return;
      }
      if (!silent) {
        toast({
          title: 'Konuşmalar yüklenemedi',
          description: err.response?.data?.detail || err.message || 'Bilinmeyen hata',
          variant: 'destructive',
        });
      }
    } finally {
      if (
        !silent &&
        isMountedRef.current &&
        requestId === conversationsRequestIdRef.current
      ) {
        setLoadingConversations(false);
      }
    }
  }, [toast]);

  const loadThread = useCallback(
    async (userId, { silent = false, markRead = false } = {}) => {
      if (!userId) return;
      if (threadAbortRef.current) {
        threadAbortRef.current.abort();
      }
      const controller = new AbortController();
      threadAbortRef.current = controller;
      const requestId = ++threadRequestIdRef.current;

      if (!silent) setLoadingThread(true);
      try {
        const res = await axios.get(
          `/messaging/internal/conversation/${encodeURIComponent(userId)}`,
          { signal: controller.signal },
        );
        if (
          !isMountedRef.current ||
          requestId !== threadRequestIdRef.current ||
          controller.signal.aborted
        ) {
          return;
        }
        setThreadMessages(res.data?.messages || []);

        if (markRead) {
          // Mark the whole thread as read on the server, then refresh the
          // conversations list so the unread badge clears immediately.
          try {
            await axios.put(
              `/messaging/internal/conversation/${encodeURIComponent(userId)}/mark-read`,
            );
            if (isMountedRef.current) {
              setConversations((prev) =>
                prev.map((c) =>
                  c.user_id === userId ? { ...c, unread_count: 0 } : c,
                ),
              );
              // Inbox unread count may also change for DMs to me
              loadInbox(true);
            }
          } catch {
            /* non-fatal */
          }
        }
      } catch (err) {
        if (axios.isCancel?.(err) || err.name === 'CanceledError' || err.name === 'AbortError') {
          return;
        }
        if (!silent) {
          toast({
            title: 'Konuşma yüklenemedi',
            description: err.response?.data?.detail || err.message || 'Bilinmeyen hata',
            variant: 'destructive',
          });
        }
      } finally {
        if (
          !silent &&
          isMountedRef.current &&
          requestId === threadRequestIdRef.current
        ) {
          setLoadingThread(false);
        }
      }
    },
    [loadInbox, toast],
  );

  const handleSelectConversation = useCallback(
    (conv) => {
      setSelectedConvUserId(conv.user_id);
      setSelectedConvUserName(conv.user_name);
      setThreadReply('');
      setThreadPriority('normal');
      setThreadMessages([]);
      setUrgentConfirmOpen(false);
      // Drop any in-flight edit when switching threads — the message id is
      // about to disappear from the rendered list anyway.
      setEditingMessageId(null);
      setEditingDraft('');
      setSavingEdit(false);
      loadThread(conv.user_id, { markRead: true });
    },
    [loadThread],
  );

  // Task #30: Departman dropdown badge'i tıklanınca dropdown'ı kapat,
  // o departmana filtre koy ve listede ilk okunmamış mesajı olan
  // konuşmayı aç. Geleneksel Item.onSelect davranışı badge dışında
  // (label/whitespace) kalır, dolayısıyla normal seçim yapısı bozulmaz.
  const jumpToFirstUnreadInDepartment = useCallback(
    (deptValue) => {
      setConversationDeptFilter(deptValue);
      setConversationDeptOpen(false);
      const opt = CONVERSATION_DEPARTMENT_FILTERS.find(
        (o) => o.value === deptValue,
      );
      const allowed = opt?.roles ? new Set(opt.roles) : null;
      const target = conversations.find((c) => {
        if (allowed && !allowed.has(c.user_role || '')) return false;
        return (c.unread_count || 0) > 0;
      });
      if (target) {
        handleSelectConversation(target);
      }
    },
    [conversations, handleSelectConversation],
  );

  const performSendThreadReply = useCallback(async () => {
    const trimmed = threadReply.trim();
    if (!trimmed || !selectedConvUserId) return;
    setSendingThreadReply(true);
    try {
      await axios.post('/messaging/internal/send', null, {
        params: {
          message: trimmed,
          to_user_id: selectedConvUserId,
          priority: threadPriority,
        },
      });
      setThreadReply('');
      // Reset to normal so the next message doesn't accidentally inherit
      // an "urgent" flag from a previous one-off alert.
      setThreadPriority('normal');
      // Refresh thread + conversation list
      await loadThread(selectedConvUserId, { silent: true });
      loadConversations(true);
    } catch (err) {
      const status = err.response?.status;
      const serverDetail = err.response?.data?.detail;
      let description = serverDetail || err.message;
      if (status === 403) {
        if (threadPriority === 'urgent') {
          // Backend gates urgent priority behind a separate permission. Show
          // the exact reason and reset the picker so a retry without urgent
          // succeeds without the user having to manually flip it back.
          description =
            serverDetail ||
            'Acil mesaj gönderme yetkiniz yok. Bu kanal yalnızca yönetici/süpervizör rollerine açıktır.';
          setThreadPriority('normal');
        } else {
          description = 'Bu işlem için yetkiniz yok. Yöneticinizden "Mesajlaşma" izni isteyin.';
        }
      }
      toast({ title: 'Yanıt gönderilemedi', description, variant: 'destructive' });
    } finally {
      setSendingThreadReply(false);
    }
  }, [threadReply, threadPriority, selectedConvUserId, loadThread, loadConversations, toast]);

  // Wrapper used by Send button / Enter key. For "urgent" priority we first
  // pop a quick confirmation so a misclick on Acil doesn't blast an alarm.
  // Normal/High priorities are unaffected.
  const handleSendThreadReply = useCallback(() => {
    const trimmed = threadReply.trim();
    if (!trimmed || !selectedConvUserId || sendingThreadReply) return;
    if (threadPriority === 'urgent') {
      setUrgentConfirmOpen(true);
      return;
    }
    performSendThreadReply();
  }, [threadReply, selectedConvUserId, sendingThreadReply, threadPriority, performSendThreadReply]);

  const handleConfirmUrgentSend = useCallback(() => {
    setUrgentConfirmOpen(false);
    performSendThreadReply();
  }, [performSendThreadReply]);

  // ── Inline edit handlers ────────────────────────────────────────────────
  // Begin editing: snapshot the current text into the draft so cancel is a
  // pure local rollback. We deliberately allow editing even if the bubble
  // priority is 'urgent' — the alarm has already fired and the recipient
  // should still be able to read the corrected wording.
  const beginEditMessage = useCallback((msg) => {
    if (!msg) return;
    setEditingMessageId(msg.id);
    setEditingDraft(msg.message || '');
  }, []);

  const cancelEditMessage = useCallback(() => {
    setEditingMessageId(null);
    setEditingDraft('');
    setSavingEdit(false);
  }, []);

  // Task #39: lazy-load the edit history for the "(düzenlendi)" popover.
  // Called when the user opens the popover for a message; subsequent opens
  // for the same message reuse the cached payload. We do not retry on
  // error — the popover surfaces the failure and the user can re-open it
  // (which clears the entry) to retry.
  const fetchEditHistory = useCallback(
    async (messageId) => {
      if (!messageId) return;
      setEditHistoryByMsg((prev) => ({
        ...prev,
        [messageId]: { loading: true, error: null, history: [], current_message: '' },
      }));
      try {
        const res = await axios.get(`/messaging/internal/${messageId}/history`);
        const data = res?.data || {};
        setEditHistoryByMsg((prev) => ({
          ...prev,
          [messageId]: {
            loading: false,
            error: null,
            history: Array.isArray(data.history) ? data.history : [],
            current_message: data.current_message || '',
          },
        }));
      } catch (err) {
        const detail =
          err?.response?.data?.detail ||
          err?.message ||
          'Geçmiş yüklenemedi';
        setEditHistoryByMsg((prev) => ({
          ...prev,
          [messageId]: { loading: false, error: detail, history: [], current_message: '' },
        }));
      }
    },
    [],
  );

  const handleSubmitEditMessage = useCallback(
    async (messageId) => {
      if (!messageId) return;
      const trimmed = (editingDraft || '').trim();
      if (!trimmed) {
        toast({
          title: 'Boş mesaj',
          description: 'Mesaj metni boş olamaz.',
          variant: 'destructive',
        });
        return;
      }
      // No-op short-circuit — saves a server round trip and avoids polluting
      // the edit history with a "no change" entry.
      const original = threadMessages.find((m) => m.id === messageId);
      if (original && (original.message || '') === trimmed) {
        cancelEditMessage();
        return;
      }
      setSavingEdit(true);
      try {
        const res = await axios.patch(
          `/messaging/internal/${encodeURIComponent(messageId)}`,
          { message: trimmed },
        );
        const editedAt = res.data?.edited_at || new Date().toISOString();
        // Optimistic update: stamp the bubble with the new text + badge so
        // the change appears instantly. The silent thread refresh + the
        // websocket update event will reconcile shortly.
        setThreadMessages((prev) =>
          prev.map((m) =>
            m.id === messageId
              ? { ...m, message: trimmed, edited: true, edited_at: editedAt }
              : m,
          ),
        );
        setInbox((prev) =>
          prev.map((m) =>
            m.id === messageId
              ? { ...m, message: trimmed, edited: true, edited_at: editedAt }
              : m,
          ),
        );
        cancelEditMessage();
        toast({
          title: 'Mesaj güncellendi',
          description: 'Karşı tarafta "düzenlendi" etiketi ile görünecek.',
        });
        if (selectedConvUserId) {
          loadThread(selectedConvUserId, { silent: true });
        }
        loadConversations(true);
      } catch (err) {
        const status = err.response?.status;
        let description = err.response?.data?.detail || err.message;
        if (status === 403) {
          description = 'Sadece kendi gönderdiğiniz mesajları düzenleyebilirsiniz.';
        }
        toast({
          title: 'Mesaj düzenlenemedi',
          description,
          variant: 'destructive',
        });
        setSavingEdit(false);
      }
    },
    [
      editingDraft,
      threadMessages,
      cancelEditMessage,
      selectedConvUserId,
      loadThread,
      loadConversations,
      toast,
    ],
  );

  const handleRecallMessage = useCallback(
    async (messageId) => {
      if (!messageId) return;
      // Plain confirm() keeps the surface area small and avoids dragging a
      // dialog primitive into the per-message hot path. The action is
      // destructive but reversible only by sending a new message.
      const ok = window.confirm(
        'Bu mesajı geri almak istediğinize emin misiniz? Karşı tarafta "Bu mesaj kaldırıldı" olarak görünecek.',
      );
      if (!ok) return;
      try {
        const res = await axios.delete(
          `/messaging/internal/${encodeURIComponent(messageId)}`,
        );
        // Optimistically mark the bubble as deleted so the UI reflects the
        // change before the silent refresh lands.
        setThreadMessages((prev) =>
          prev.map((m) =>
            m.id === messageId
              ? { ...m, deleted: true, message: '' }
              : m,
          ),
        );
        toast({
          title: 'Mesaj geri alındı',
          description: res.data?.alarm_cleared
            ? 'Acil alarmı da otomatik kapatıldı.'
            : 'Karşı tarafta "Bu mesaj kaldırıldı" olarak görünecek.',
        });
        // Refresh thread + conversations preview so the tombstone is canonical.
        if (selectedConvUserId) {
          loadThread(selectedConvUserId, { silent: true });
        }
        loadConversations(true);
      } catch (err) {
        const status = err.response?.status;
        let description = err.response?.data?.detail || err.message;
        if (status === 403) {
          description = 'Sadece kendi gönderdiğiniz mesajları geri alabilirsiniz.';
        }
        toast({
          title: 'Mesaj geri alınamadı',
          description,
          variant: 'destructive',
        });
      }
    },
    [selectedConvUserId, loadThread, loadConversations, toast],
  );

  const handleStartConversationFromUser = useCallback(
    (user) => {
      const existing = conversations.find((c) => c.user_id === user.id);
      if (existing) {
        handleSelectConversation(existing);
        return;
      }
      // Synthetic conversation row for a partner with no history yet.
      handleSelectConversation({ user_id: user.id, user_name: user.name });
    },
    [conversations, handleSelectConversation],
  );

  const loadUsers = useCallback(async () => {
    try {
      const res = await axios.get('/admin/users', { params: { limit: 200 } });
      if (!isMountedRef.current) return;
      const list = (res.data?.users || [])
        .filter((u) => u.is_active !== false && STAFF_ROLES.has(u.role) && u.id !== currentUser?.id)
        .map((u) => ({
          id: u.id,
          name: u.name || u.username || u.email || 'Kullanıcı',
          email: u.email || '',
          role: u.role,
        }))
        .sort((a, b) => (a.name || '').localeCompare(b.name || '', 'tr'));
      setUsers(list);
      setUsersLoaded(true);
      setUsersAccessDenied(false);
    } catch (err) {
      if (!isMountedRef.current) return;
      const status = err.response?.status;
      if (status === 401 || status === 403) {
        setUsersAccessDenied(true);
      }
      setUsersLoaded(true);
    }
  }, [currentUser?.id]);

  // Task #25: tenant kapsamlı çevrimiçi kullanıcı listesi.
  // Hata durumunda sessiz: presence bir UX ipucu, güvenlik sınırı değil.
  const loadOnlinePresence = useCallback(async () => {
    try {
      // axios.defaults.baseURL zaten `/api` ile bitiyor — diğer
      // mesajlaşma çağrılarıyla aynı şekilde göreli yol kullan,
      // aksi halde `/api/api/...` çift prefix'i 404'e yol açar.
      const res = await axios.get('/messaging/internal/presence/online');
      if (!isMountedRef.current) return;
      const ids = Array.isArray(res.data?.user_ids) ? res.data.user_ids : [];
      setOnlineUsers(new Set(ids));
    } catch {
      if (!isMountedRef.current) return;
      // Endpoint'e ulaşılamıyorsa boş set'e düşür ki toggle yanıltıcı
      // şekilde "herkes online" göstermesin.
      setOnlineUsers(new Set());
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    loadInbox();
    loadUsers();
    loadConversations();
    return () => {
      isMountedRef.current = false;
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
      if (conversationPollTimerRef.current) clearInterval(conversationPollTimerRef.current);
      if (threadPollTimerRef.current) clearInterval(threadPollTimerRef.current);
      if (inboxAbortRef.current) inboxAbortRef.current.abort();
      if (conversationsAbortRef.current) conversationsAbortRef.current.abort();
      if (threadAbortRef.current) threadAbortRef.current.abort();
    };
  }, [loadInbox, loadUsers, loadConversations]);

  // Polling timers — Socket.IO ana iletim, polling güvenlik ağı.
  // Tarayıcı sekmesi arka plana geçince timer'lar duraklatılır,
  // tekrar öne gelince hem hemen bir tetikleme yapılır hem timer
  // yeniden başlatılır (boşta sekmelerden gereksiz yük olmasın).
  useEffect(() => {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    pollTimerRef.current = null;
    const start = () => {
      if (pollTimerRef.current !== null || document.hidden) return;
      pollTimerRef.current = setInterval(() => loadInbox(true), POLL_INTERVAL_MS);
    };
    const stop = () => {
      if (pollTimerRef.current !== null) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
    const onVis = () => {
      if (document.hidden) stop();
      else { loadInbox(true); start(); }
    };
    start();
    document.addEventListener('visibilitychange', onVis);
    return () => {
      stop();
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [loadInbox]);

  useEffect(() => {
    if (conversationPollTimerRef.current) clearInterval(conversationPollTimerRef.current);
    conversationPollTimerRef.current = null;
    const start = () => {
      if (conversationPollTimerRef.current !== null || document.hidden) return;
      conversationPollTimerRef.current = setInterval(
        () => loadConversations(true),
        POLL_INTERVAL_MS,
      );
    };
    const stop = () => {
      if (conversationPollTimerRef.current !== null) {
        clearInterval(conversationPollTimerRef.current);
        conversationPollTimerRef.current = null;
      }
    };
    const onVis = () => {
      if (document.hidden) stop();
      else { loadConversations(true); start(); }
    };
    start();
    document.addEventListener('visibilitychange', onVis);
    return () => {
      stop();
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [loadConversations]);

  // Poll the open thread every 60s so incoming messages from the partner
  // appear without a manual refresh. Only runs while a thread is selected.
  // (Socket.IO is the primary delivery mechanism — this is a safety net.)
  useEffect(() => {
    if (threadPollTimerRef.current) clearInterval(threadPollTimerRef.current);
    threadPollTimerRef.current = null;
    if (!selectedConvUserId) return;
    const tick = () => loadThread(selectedConvUserId, { silent: true, markRead: true });
    const start = () => {
      if (threadPollTimerRef.current !== null || document.hidden) return;
      threadPollTimerRef.current = setInterval(tick, POLL_INTERVAL_MS);
    };
    const stop = () => {
      if (threadPollTimerRef.current !== null) {
        clearInterval(threadPollTimerRef.current);
        threadPollTimerRef.current = null;
      }
    };
    const onVis = () => {
      if (document.hidden) stop();
      else { tick(); start(); }
    };
    start();
    document.addEventListener('visibilitychange', onVis);
    return () => {
      stop();
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [selectedConvUserId, loadThread]);

  // Auto-scroll the thread to the bottom whenever new messages arrive.
  useEffect(() => {
    if (!threadScrollRef.current) return;
    const node = threadScrollRef.current;
    // requestAnimationFrame ensures the DOM is painted before scrolling
    requestAnimationFrame(() => {
      node.scrollTop = node.scrollHeight;
    });
  }, [threadMessages]);

  // ── Live updates: subscribe to Socket.IO so new messages appear instantly. ──
  // The server-side `internal_message` event already filters by tenant + room
  // (user / department / broadcast), so anything that lands here is for us.
  // Updates the inbox AND, if a thread for the same partner is open, appends
  // the message to the thread view so partner replies stream in live too.
  useEffect(() => {
    let teardown = null;
    let cancelled = false;

    const onMessage = (envelope) => {
      const msg = envelope?.message;
      if (!msg) return;

      const fromMe = msg.from_user_id && currentUser?.id && msg.from_user_id === currentUser.id;

      setInbox((prev) => {
        if (prev.some((m) => m.id === msg.id)) return prev;
        const merged = [{ ...msg, time_ago: msg.time_ago || 'şimdi' }, ...prev];
        return merged.slice(0, 200);
      });

      if (!fromMe && !msg.read) {
        setUnreadCount((c) => c + 1);
      }

      // If the open thread is with the sender (or recipient, for echo of
      // our own messages from another tab), append it live so the user
      // doesn't have to wait for the 60s safety-net poll.
      if (selectedConvUserId) {
        const partnerId = fromMe ? msg.to_user_id : msg.from_user_id;
        if (partnerId && partnerId === selectedConvUserId) {
          setThreadMessages((prev) => {
            if (prev.some((m) => m.id === msg.id)) return prev;
            return [...prev, { ...msg, time_ago: msg.time_ago || 'şimdi' }];
          });
        }
      }
    };

    // In-place updates (e.g. edits) — replace the existing entry rather than
    // prepending a new bubble so the conversation stays in chronological
    // order and the "düzenlendi" badge appears immediately for the recipient.
    const onMessageUpdate = (envelope) => {
      const msg = envelope?.message;
      if (!msg || !msg.id) return;

      setInbox((prev) =>
        prev.map((m) =>
          m.id === msg.id
            ? {
                ...m,
                message: msg.message,
                edited: !!msg.edited,
                edited_at: msg.edited_at || m.edited_at,
              }
            : m,
        ),
      );
      setThreadMessages((prev) =>
        prev.map((m) =>
          m.id === msg.id
            ? {
                ...m,
                message: msg.message,
                edited: !!msg.edited,
                edited_at: msg.edited_at || m.edited_at,
              }
            : m,
        ),
      );
    };

    (async () => {
      try {
        await websocket.connect();
        if (cancelled) return;
        const off1 = websocket.on('internal_message', onMessage);
        const off2 = websocket.on('internal_message_updated', onMessageUpdate);
        teardown = () => {
          if (off1) off1();
          if (off2) off2();
        };
      } catch {
        /* noop — falls back to polling */
      }
    })();

    return () => {
      cancelled = true;
      if (teardown) teardown();
    };
  }, [currentUser?.id, selectedConvUserId]);

  // ── Live read receipts via WebSocket ───────────────────────────────
  // When the partner reads my messages, flip the ✓✓ icon immediately
  // instead of waiting for the next safety-net poll. The polling fallback
  // remains in place so if WS is unavailable nothing breaks.
  useEffect(() => {
    const myId = currentUser?.id;
    if (!myId) return undefined;
    const off = wsOn('internal_message_read', (data) => {
      if (!data || data.sender_id !== myId) return;
      const readerId = data.reader_id;
      const ids = Array.isArray(data.message_ids) ? data.message_ids : [];
      // Update the open thread if it matches the reader.
      if (selectedConvUserIdRef.current === readerId) {
        setThreadMessages((prev) =>
          prev.map((m) => {
            if (!m.is_from_me) return m;
            if (ids.length === 0 || ids.includes(m.id)) {
              return { ...m, read: true };
            }
            return m;
          }),
        );
      }
    });
    return off;
  }, [wsOn, currentUser?.id]);

  // ── Live "yazıyor…" indicator via WebSocket ───────────────────────
  useEffect(() => {
    const myId = currentUser?.id;
    if (!myId) return undefined;
    const off = wsOn('internal_user_typing', (data) => {
      if (!data) return;
      // Only react to typing events addressed to me from the open partner.
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
      if (typingClearTimerRef.current) {
        clearTimeout(typingClearTimerRef.current);
      }
      typingClearTimerRef.current = setTimeout(() => {
        setTypingPartnerName('');
        typingClearTimerRef.current = null;
      }, TYPING_INDICATOR_TTL_MS);
    });
    return off;
  }, [wsOn, currentUser?.id]);

  useEffect(
    () => () => {
      if (typingClearTimerRef.current) clearTimeout(typingClearTimerRef.current);
    },
    [],
  );

  // Throttled emitter for the local user's typing activity. Called from
  // the reply textarea's onChange handler.
  const emitTyping = useCallback(() => {
    const partnerId = selectedConvUserIdRef.current;
    const myId = currentUser?.id;
    if (!partnerId || !myId) return;
    const now = Date.now();
    if (now - lastTypingEmitRef.current < TYPING_EMIT_THROTTLE_MS) return;
    lastTypingEmitRef.current = now;
    wsSocketEmit('internal_typing', {
      from_user_id: myId,
      from_user_name: currentUser?.name || '',
      to_user_id: partnerId,
      tenant_id: currentUser?.tenant_id,
      is_typing: true,
    });
  }, [wsSocketEmit, currentUser?.id, currentUser?.name, currentUser?.tenant_id]);

  const filteredUsers = useMemo(() => {
    const q = userSearch.trim().toLocaleLowerCase('tr');
    const deptOption = CONVERSATION_DEPARTMENT_FILTERS.find(
      (opt) => opt.value === userDeptFilter,
    );
    const allowedRoles = deptOption?.roles ? new Set(deptOption.roles) : null;

    const matches = users.filter((u) => {
      if (allowedRoles && !allowedRoles.has(u.role || '')) return false;
      // Task #25: çevrimiçi-yalnızca filtresi. Online listesi tenant
      // kapsamlı geldiği için ekstra tenant kontrolüne gerek yok.
      if (onlineOnly && !onlineUsers.has(u.id)) return false;
      if (q) {
        const name = (u.name || '').toLocaleLowerCase('tr');
        const email = (u.email || '').toLocaleLowerCase('tr');
        if (!name.includes(q) && !email.includes(q)) return false;
      }
      return true;
    });

    return matches.slice(0, 50);
  }, [users, userSearch, userDeptFilter, onlineOnly, onlineUsers]);

  const filteredConversations = useMemo(() => {
    const q = conversationSearch.trim().toLocaleLowerCase('tr');
    const deptOption = CONVERSATION_DEPARTMENT_FILTERS.find(
      (opt) => opt.value === conversationDeptFilter,
    );
    const allowedRoles = deptOption?.roles ? new Set(deptOption.roles) : null;

    return conversations.filter((c) => {
      if (q && !(c.user_name || '').toLocaleLowerCase('tr').includes(q)) {
        return false;
      }
      if (allowedRoles && !allowedRoles.has(c.user_role || '')) {
        return false;
      }
      if (conversationOnlyUnread && (c.unread_count || 0) <= 0) {
        return false;
      }
      return true;
    });
  }, [conversations, conversationSearch, conversationDeptFilter, conversationOnlyUnread]);

  const conversationFiltersActive =
    conversationDeptFilter !== 'all' ||
    conversationOnlyUnread ||
    !!conversationSearch.trim();

  const totalConversationUnread = useMemo(
    () => conversations.reduce((sum, c) => sum + (c.unread_count || 0), 0),
    [conversations],
  );

  // Per-department unread totals keyed by the filter `value`. Counts are derived
  // from the same `conversations` state used by the list, so they refresh
  // automatically whenever polling pulls in new data.
  const conversationUnreadByDept = useMemo(() => {
    const counts = {};
    for (const opt of CONVERSATION_DEPARTMENT_FILTERS) {
      if (opt.value === 'all') {
        counts[opt.value] = conversations.reduce(
          (sum, c) => sum + (c.unread_count || 0),
          0,
        );
        continue;
      }
      const allowed = opt.roles ? new Set(opt.roles) : null;
      counts[opt.value] = conversations.reduce((sum, c) => {
        if (allowed && !allowed.has(c.user_role || '')) return sum;
        return sum + (c.unread_count || 0);
      }, 0);
    }
    return counts;
  }, [conversations]);

  const handleMarkAllRead = useCallback(async () => {
    if (markingAllRead || unreadCount === 0) return;
    setMarkingAllRead(true);
    // Optimistically clear local state so the badge / inbox flip read
    // immediately — the global bell counter is reset inside the context
    // helper, the conversations panel below picks the new state up via
    // its existing refresh.
    setInbox((prev) => prev.map((m) => ({ ...m, read: true })));
    setUnreadCount(0);
    setConversations((prev) => prev.map((c) => ({ ...c, unread_count: 0 })));
    try {
      const result = await markAllInternalRead();
      if (!result?.success) {
        // Roll back to server truth on failure.
        await loadInbox(true);
        await loadConversations(true);
        toast({
          title: 'İşaretleme başarısız',
          description:
            result?.error?.response?.data?.detail ||
            result?.error?.message ||
            'Mesajlar işaretlenirken bir sorun oluştu.',
          variant: 'destructive',
        });
        return;
      }
      toast({
        title: 'Tüm mesajlar okundu olarak işaretlendi',
        description:
          result.updated_count > 0
            ? `${result.updated_count} mesaj güncellendi.`
            : 'Okunmamış mesaj kalmamıştı.',
      });
      // Pull a fresh inbox so any messages that arrived during the request
      // (and so were not part of the bulk update) are reflected accurately.
      loadInbox(true);
      loadConversations(true);
    } finally {
      setMarkingAllRead(false);
    }
  }, [
    markingAllRead,
    unreadCount,
    markAllInternalRead,
    loadInbox,
    loadConversations,
    toast,
  ]);

  const markAsRead = useCallback(
    async (messageId) => {
      // Find current read state so we don't double-decrement the bell when
      // the same message is clicked twice.
      const wasUnread = inbox.find((m) => m.id === messageId)?.read === false;
      try {
        await axios.put(`/messaging/internal/${messageId}/mark-read`);
        setInbox((prev) =>
          prev.map((m) => (m.id === messageId ? { ...m, read: true } : m)),
        );
        if (wasUnread) {
          setUnreadCount((c) => Math.max(0, c - 1));
          decrementInternalUnread(1);
        }
      } catch (err) {
        toast({
          title: 'İşaretleme başarısız',
          description: err.response?.data?.detail || err.message,
          variant: 'destructive',
        });
      }
    },
    [inbox, toast, decrementInternalUnread],
  );

  const handleReply = useCallback(
    (msg) => {
      // For 1-to-1 DMs (sender to a specific user), prefer opening the
      // WhatsApp-style thread so the operator sees full context.
      // Detect DMs by `to_user_id` (canonical signal) so we still route
      // legacy records that lack a denormalized `to_user_name`.
      if (msg.from_user_id && (msg.to_user_id || msg.to_user_name)) {
        const partner = {
          user_id: msg.from_user_id,
          user_name: msg.from_user_name || 'Kullanıcı',
        };
        setComposeOpen(false);
        handleSelectConversation(partner);
        return;
      }
      if (msg.from_user_id) {
        setRecipientType('user');
        setToUserId(msg.from_user_id);
        setUserSearch(msg.from_user_name || '');
      } else if (msg.from_department) {
        setRecipientType('department');
        setToDepartment(msg.from_department);
      }
      setMessageText('');
      setComposeOpen(true);
    },
    [handleSelectConversation],
  );

  const resetForm = () => {
    setMessageText('');
    setPriority('normal');
    setUserSearch('');
    setToUserId('');
  };

  const handleSend = async () => {
    const trimmed = messageText.trim();
    if (!trimmed) {
      toast({ title: 'Boş mesaj gönderilemez', variant: 'destructive' });
      return;
    }
    if (recipientType === 'user' && !toUserId) {
      toast({ title: 'Lütfen bir alıcı seçin', variant: 'destructive' });
      return;
    }

    const params = { message: trimmed, priority };
    if (recipientType === 'department') {
      params.to_department = toDepartment;
    } else if (recipientType === 'user') {
      params.to_user_id = toUserId;
    }
    // 'broadcast' → ne to_department ne to_user_id (backend tüm departmanlara gönderir)

    setSending(true);
    try {
      const res = await axios.post('/messaging/internal/send', null, { params });
      toast({
        title: 'Mesaj gönderildi',
        description: `Alıcı: ${res.data?.delivered_to || 'Bilinmiyor'}`,
      });
      resetForm();
      loadInbox(true);
    } catch (err) {
      const status = err.response?.status;
      const serverDetail = err.response?.data?.detail;
      let description = serverDetail || err.message;
      if (status === 403) {
        if (priority === 'urgent') {
          // Surface the exact urgent-permission reason and roll the picker
          // back to "normal" so the next attempt isn't auto-blocked again.
          description =
            serverDetail ||
            'Acil mesaj gönderme yetkiniz yok. Bu kanal yalnızca yönetici/süpervizör rollerine açıktır.';
          setPriority('normal');
        } else {
          description = 'Bu işlem için yetkiniz yok. Yöneticinizden "Mesajlaşma" izni isteyin.';
        }
      }
      toast({ title: 'Gönderim başarısız', description, variant: 'destructive' });
    } finally {
      setSending(false);
    }
  };





  const totalUnread = (unreadCount || 0) + (totalConversationUnread || 0);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <MessagesSquare className="h-5 w-5" /> Personel Mesajlaşması
            {totalUnread > 0 && (
              <Badge variant="destructive" data-testid="badge-total-unread">
                {totalUnread}
              </Badge>
            )}
          </h2>
          <p className="text-xs text-muted-foreground">
            {myDepartment && (
              <>
                Departmanım: <span className="font-medium">{myDepartment}</span>
                {' · '}
              </>
            )}
            Canlı bildirim açık · Yedek yenileme: 60 sn
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleMarkAllRead}
            disabled={markingAllRead || unreadCount === 0}
            data-testid="button-mark-all-read"
            title="Gelen kutusundaki tüm okunmamış mesajları işaretle"
          >
            <CheckCheck className={`h-4 w-4 mr-1 ${markingAllRead ? 'animate-pulse' : ''}`} />
            {markingAllRead ? 'İşaretleniyor…' : 'Tümünü okundu'}
          </Button>
          <Button
            type="button"
            variant={showUnreadOnly ? 'default' : 'outline'}
            size="sm"
            onClick={() => setShowUnreadOnly((v) => !v)}
            data-testid="button-toggle-unread"
          >
            {showUnreadOnly ? 'Tümü' : 'Sadece okunmamış'}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => loadInbox()}
            disabled={loadingInbox}
            data-testid="button-refresh-inbox"
          >
            <RefreshCw className={`h-4 w-4 mr-1 ${loadingInbox ? 'animate-spin' : ''}`} />
            Yenile
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={() => setComposeOpen(true)}
            data-testid="button-open-compose"
          >
            <Send className="h-4 w-4 mr-1" /> Yeni Mesaj
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[340px_1fr] gap-3 md:h-[640px]">
        <div
          className={`${selectedConvUserId ? 'hidden md:block' : 'block'} h-[280px] md:h-full overflow-hidden`}
          data-testid="pane-conversations-list"
        >
          <ConversationsList
            conversations={conversations}
            filteredConversations={filteredConversations}
            loadingConversations={loadingConversations}
            loadConversations={loadConversations}
            selectedConvUserId={selectedConvUserId}
            handleSelectConversation={handleSelectConversation}
            totalConversationUnread={totalConversationUnread}
            conversationSearch={conversationSearch}
            setConversationSearch={setConversationSearch}
            conversationDeptFilter={conversationDeptFilter}
            setConversationDeptFilter={setConversationDeptFilter}
            conversationDeptOpen={conversationDeptOpen}
            setConversationDeptOpen={setConversationDeptOpen}
            conversationOnlyUnread={conversationOnlyUnread}
            setConversationOnlyUnread={setConversationOnlyUnread}
            conversationUnreadByDept={conversationUnreadByDept}
            conversationFiltersActive={conversationFiltersActive}
            jumpToFirstUnreadInDepartment={jumpToFirstUnreadInDepartment}
          />
        </div>
        <div
          className="block h-[440px] md:h-full overflow-hidden"
          data-testid="pane-detail"
        >
          {selectedConvUserId ? (
            <ThreadView
              selectedConvUserId={selectedConvUserId}
              selectedConvUserName={selectedConvUserName}
              setSelectedConvUserId={setSelectedConvUserId}
              setSelectedConvUserName={setSelectedConvUserName}
              setThreadMessages={setThreadMessages}
              threadMessages={threadMessages}
              loadingThread={loadingThread}
              loadThread={loadThread}
              threadScrollRef={threadScrollRef}
              typingPartnerName={typingPartnerName}
              usersAccessDenied={usersAccessDenied}
              users={users}
              handleStartConversationFromUser={handleStartConversationFromUser}
              editingMessageId={editingMessageId}
              editingDraft={editingDraft}
              setEditingDraft={setEditingDraft}
              savingEdit={savingEdit}
              beginEditMessage={beginEditMessage}
              cancelEditMessage={cancelEditMessage}
              handleSubmitEditMessage={handleSubmitEditMessage}
              handleRecallMessage={handleRecallMessage}
              editHistoryByMsg={editHistoryByMsg}
              fetchEditHistory={fetchEditHistory}
              threadReply={threadReply}
              setThreadReply={setThreadReply}
              threadPriority={threadPriority}
              setThreadPriority={setThreadPriority}
              emitTyping={emitTyping}
              handleSendThreadReply={handleSendThreadReply}
              sendingThreadReply={sendingThreadReply}
              canSendUrgent={canSendUrgent}
              urgentConfirmOpen={urgentConfirmOpen}
              setUrgentConfirmOpen={setUrgentConfirmOpen}
              handleConfirmUrgentSend={handleConfirmUrgentSend}
            />
          ) : (
            <InboxList
              inbox={inbox}
              unreadCount={unreadCount}
              loadingInbox={loadingInbox}
              showUnreadOnly={showUnreadOnly}
              markAsRead={markAsRead}
              handleReply={handleReply}
            />
          )}
        </div>
      </div>

      <Dialog
        open={composeOpen}
        onOpenChange={(open) => {
          setComposeOpen(open);
          if (open) {
            loadUsers();
            // Task #25: dialog her açıldığında presence taze olsun.
            loadOnlinePresence();
          }
        }}
      >
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="dialog-compose">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Send className="h-5 w-5" /> Yeni Mesaj
            </DialogTitle>
            <DialogDescription>
              Bir departmana, belirli bir personele veya tüm otele mesaj gönderin.
            </DialogDescription>
          </DialogHeader>
          <ComposeForm
            recipientType={recipientType}
            setRecipientType={setRecipientType}
            toDepartment={toDepartment}
            setToDepartment={setToDepartment}
            usersAccessDenied={usersAccessDenied}
            userSearch={userSearch}
            setUserSearch={setUserSearch}
            toUserId={toUserId}
            setToUserId={setToUserId}
            userDeptFilter={userDeptFilter}
            setUserDeptFilter={setUserDeptFilter}
            onlineOnly={onlineOnly}
            setOnlineOnly={setOnlineOnly}
            onlineUsers={onlineUsers}
            loadOnlinePresence={loadOnlinePresence}
            usersLoaded={usersLoaded}
            users={users}
            filteredUsers={filteredUsers}
            messageText={messageText}
            setMessageText={setMessageText}
            priority={priority}
            setPriority={setPriority}
            canSendUrgent={canSendUrgent}
            resetForm={resetForm}
            handleSend={handleSend}
            sending={sending}
          />
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default InternalChatTab;
