import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import * as SelectPrimitive from '@radix-ui/react-select';
import { Check } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Switch } from '@/components/ui/switch';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useToast } from '@/hooks/use-toast';
import { websocket, useWebSocket } from '@/lib/websocket';
import { useNotifications } from '@/context/NotificationContext';
import { canSendUrgentMessage, hasRole } from '@/utils/authRoles';
import {
  Inbox, Send, RefreshCw, AlertCircle, CheckCircle, Building2,
  Users, MessageSquare, Search, Reply, MessagesSquare, ArrowLeft, CheckCheck,
  MoreVertical, Trash2, Pencil, X,
} from 'lucide-react';

const DEPARTMENTS = [
  { value: 'Reception', label: 'Ön Büro' },
  { value: 'Housekeeping', label: 'Kat Hizmetleri' },
  { value: 'Maintenance', label: 'Teknik Servis' },
  { value: 'Finance', label: 'Muhasebe' },
  { value: 'Management', label: 'Yönetim' },
  { value: 'General', label: 'Genel' },
];

const ROLE_LABELS = {
  super_admin: 'Süper Yönetici',
  admin: 'Yönetici',
  supervisor: 'Süpervizör',
  front_desk: 'Ön Büro',
  housekeeping: 'Kat Hizmetleri',
  maintenance: 'Teknik',
  finance: 'Muhasebe',
  sales: 'Satış',
};

const STAFF_ROLES = new Set([
  'super_admin', 'admin', 'supervisor',
  'front_desk', 'housekeeping', 'maintenance', 'finance', 'sales',
]);

// Department filter options for the conversations list. Each entry maps a
// human-readable label to the set of backend `role` values it should match.
// `value: 'all'` is the no-op default that keeps every conversation visible.
const CONVERSATION_DEPARTMENT_FILTERS = [
  { value: 'all', label: 'Tümü', roles: null },
  { value: 'front_desk', label: 'Ön Büro', roles: ['front_desk'] },
  { value: 'housekeeping', label: 'HK', roles: ['housekeeping'] },
  { value: 'maintenance', label: 'Teknik', roles: ['maintenance'] },
  { value: 'finance', label: 'Muhasebe', roles: ['finance'] },
  { value: 'management', label: 'Yönetim', roles: ['super_admin', 'admin', 'supervisor'] },
];

// Real-time delivery happens via Socket.IO; this poll is now just a safety
// net for missed events / cross-tab sync, so we can run it much less often.
const POLL_INTERVAL_MS = 60000;

// Mirror of the backend RECALL_WINDOW_SECONDS — keeps the recall menu hidden
// once the message is past the window so we don't pretend the action is still
// available. The backend remains the source of truth and will reject late
// recalls with HTTP 400.
const RECALL_WINDOW_MS = 5 * 60 * 1000;

// How long after the last `typing` event we keep the indicator visible.
// Slightly longer than the emit cadence so brief pauses don't flicker.
const TYPING_INDICATOR_TTL_MS = 4000;
// Throttle how often we emit `internal_typing` while the user is typing.
const TYPING_EMIT_THROTTLE_MS = 1500;

// Same 5-minute window applies to in-place edits — kept identical to the
// recall window so the menu logic is straightforward (one age check covers
// both actions). Backend enforces the same limit and rejects stale edits
// with HTTP 400.
const EDIT_WINDOW_MS = 5 * 60 * 1000;

const InternalChatTab = ({ currentUser }) => {
  const { toast } = useToast();
  // Keep the global bell counter in sync when this tab mutates read state.
  const {
    decrementInternalUnread,
    refreshInternalUnread,
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

  const renderInboxList = () => (
    <div className="flex flex-col h-full border rounded-md bg-background overflow-hidden">
      <div className="px-3 py-2 border-b flex items-center justify-between gap-2 bg-muted/20">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Inbox className="h-4 w-4" /> Gelen Kutusu
          {unreadCount > 0 && (
            <Badge variant="destructive" className="px-1.5 py-0 text-[10px] h-4" data-testid="badge-unread-count">
              {unreadCount}
            </Badge>
          )}
        </div>
        <div className="text-[11px] text-muted-foreground">
          {showUnreadOnly ? 'Sadece okunmamış' : 'Tümü'}
        </div>
      </div>
      <div className="flex-1 overflow-hidden">
        {loadingInbox && inbox.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">Yükleniyor…</div>
        ) : inbox.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground px-4">
            <MessageSquare className="h-12 w-12 mx-auto mb-3 opacity-30" />
            <p>Henüz mesaj yok.</p>
            <p className="text-sm mt-1">"Yeni Mesaj" düğmesinden departmanlara veya kişilere mesaj gönderebilirsiniz.</p>
          </div>
        ) : (
          <ScrollArea className="h-full">
            <div className="space-y-2 p-3">
              {inbox.map((msg) => (
                <div
                  key={msg.id}
                  data-testid={`inbox-message-${msg.id}`}
                  className={`p-3 rounded-md border ${
                    msg.read
                      ? 'bg-background'
                      : 'bg-blue-50 dark:bg-blue-950/30 border-blue-200 dark:border-blue-800'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3 mb-1.5">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium text-sm" data-testid={`text-from-${msg.id}`}>
                          {msg.from_user_name || 'Bilinmeyen'}
                        </span>
                        {msg.from_department && (
                          <Badge variant="outline" className="text-xs">
                            {msg.from_department}
                          </Badge>
                        )}
                        {msg.priority === 'urgent' && (
                          <Badge variant="destructive" className="text-xs">
                            <AlertCircle className="h-3 w-3 mr-0.5" /> Acil
                          </Badge>
                        )}
                        {!msg.read && (
                          <Badge variant="default" className="text-xs">Yeni</Badge>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground mt-0.5">
                        {msg.to_user_name
                          ? `→ ${msg.to_user_name}`
                          : `→ ${msg.to_department || 'Tüm departmanlar'}`}
                        {' · '}
                        {msg.time_ago || msg.created_at}
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      {!msg.read && !msg.deleted && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => markAsRead(msg.id)}
                          data-testid={`button-mark-read-${msg.id}`}
                          title="Okundu olarak işaretle"
                        >
                          <CheckCircle className="h-4 w-4" />
                        </Button>
                      )}
                      {!msg.deleted && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => handleReply(msg)}
                          data-testid={`button-reply-${msg.id}`}
                          title="Yanıtla"
                        >
                          <Reply className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </div>
                  {msg.deleted ? (
                    <p
                      className="text-sm italic text-muted-foreground"
                      data-testid={`text-inbox-recalled-${msg.id}`}
                    >
                      Bu mesaj kaldırıldı
                    </p>
                  ) : (
                    <>
                      <p className="text-sm whitespace-pre-wrap break-words">{msg.message}</p>
                      {msg.edited && (
                        <span
                          className="text-[10px] text-muted-foreground italic mt-0.5 inline-block"
                          data-testid={`text-inbox-edited-${msg.id}`}
                          title={msg.edited_at ? `Son düzenleme: ${msg.edited_at}` : undefined}
                        >
                          (düzenlendi)
                        </span>
                      )}
                    </>
                  )}
                </div>
              ))}
            </div>
          </ScrollArea>
        )}
      </div>
    </div>
  );

  const renderCompose = () => (
    <div className="space-y-4">
        <div>
          <Label className="mb-2 block">Alıcı Tipi</Label>
          <div className="grid grid-cols-3 gap-2">
            <Button
              type="button"
              variant={recipientType === 'department' ? 'default' : 'outline'}
              onClick={() => setRecipientType('department')}
              data-testid="button-recipient-department"
            >
              <Building2 className="h-4 w-4 mr-1" /> Departman
            </Button>
            <Button
              type="button"
              variant={recipientType === 'user' ? 'default' : 'outline'}
              onClick={() => setRecipientType('user')}
              disabled={usersAccessDenied}
              data-testid="button-recipient-user"
              title={usersAccessDenied ? 'Kullanıcı listesine erişim yetkiniz yok' : ''}
            >
              <Users className="h-4 w-4 mr-1" /> Kişi
            </Button>
            <Button
              type="button"
              variant={recipientType === 'broadcast' ? 'default' : 'outline'}
              onClick={() => setRecipientType('broadcast')}
              data-testid="button-recipient-broadcast"
            >
              <MessageSquare className="h-4 w-4 mr-1" /> Herkese
            </Button>
          </div>
        </div>

        {recipientType === 'department' && (
          <div>
            <Label htmlFor="dept-select" className="mb-1 block">Departman Seç</Label>
            <Select value={toDepartment} onValueChange={setToDepartment}>
              <SelectTrigger id="dept-select" data-testid="select-department">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DEPARTMENTS.map((d) => (
                  <SelectItem key={d.value} value={d.value}>
                    {d.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        {recipientType === 'user' && (
          <div className="space-y-2">
            <Label htmlFor="user-search" className="mb-1 block">Personel Ara</Label>
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  id="user-search"
                  value={userSearch}
                  onChange={(e) => {
                    setUserSearch(e.target.value);
                    setToUserId('');
                  }}
                  placeholder="İsim veya e-posta…"
                  className="pl-8"
                  data-testid="input-user-search"
                />
              </div>
              <Select
                value={userDeptFilter}
                onValueChange={(v) => {
                  setUserDeptFilter(v);
                  setToUserId('');
                }}
              >
                <SelectTrigger
                  className="w-40 shrink-0"
                  data-testid="select-user-department-filter"
                >
                  <SelectValue placeholder="Departman" />
                </SelectTrigger>
                <SelectContent>
                  {CONVERSATION_DEPARTMENT_FILTERS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {/* Task #25: Sadece çevrimiçi personeli göster filtresi.
                Toggle her açıldığında presence listesini tazeleriz —
                kullanıcı toggle'ı tıkladığında "az önce oturum kapatmış"
                bir kişiyi yine de görmesinler. */}
            <div className="flex items-center justify-between rounded-md border px-3 py-1.5">
              <div className="flex items-center gap-2">
                <Switch
                  id="online-only-toggle"
                  checked={onlineOnly}
                  onCheckedChange={(checked) => {
                    setOnlineOnly(checked);
                    setToUserId('');
                    if (checked) loadOnlinePresence();
                  }}
                  data-testid="switch-online-only"
                />
                <Label
                  htmlFor="online-only-toggle"
                  className="text-xs font-normal cursor-pointer"
                >
                  Sadece çevrimiçi personeli göster
                </Label>
              </div>
              <span
                className="text-[10px] text-muted-foreground"
                data-testid="text-online-count"
              >
                {onlineUsers.size} çevrimiçi
              </span>
            </div>
            {!usersLoaded ? (
              <p className="text-xs text-muted-foreground">Personel listesi yükleniyor…</p>
            ) : users.length === 0 ? (
              <p className="text-xs text-muted-foreground">Kullanıcı bulunamadı.</p>
            ) : (
              <ScrollArea className="h-48 border rounded-md">
                <div className="p-1">
                  {filteredUsers.map((u) => (
                    <button
                      key={u.id}
                      type="button"
                      onClick={() => {
                        setToUserId(u.id);
                        setUserSearch(u.name);
                      }}
                      data-testid={`option-user-${u.id}`}
                      className={`w-full text-left px-2 py-1.5 rounded text-sm hover:bg-accent ${
                        toUserId === u.id ? 'bg-accent' : ''
                      }`}
                    >
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {/* Task #25: küçük yeşil nokta = bu kullanıcı şu
                            an WS'e bağlı. Sessiz, ekstra label yok —
                            yardımcı bir işaret, dikkat dağıtıcı değil. */}
                        {onlineUsers.has(u.id) && (
                          <span
                            className="inline-block h-2 w-2 rounded-full bg-green-500 shrink-0"
                            title="Çevrimiçi"
                            data-testid={`dot-online-${u.id}`}
                          />
                        )}
                        <span className="font-medium">{u.name}</span>
                        {u.role && ROLE_LABELS[u.role] && (
                          <Badge
                            variant="secondary"
                            className="px-1.5 py-0 text-[10px] h-4 font-normal text-muted-foreground shrink-0"
                            data-testid={`badge-user-role-${u.id}`}
                          >
                            {ROLE_LABELS[u.role]}
                          </Badge>
                        )}
                      </div>
                      {u.email && (
                        <div className="text-xs text-muted-foreground">{u.email}</div>
                      )}
                    </button>
                  ))}
                  {filteredUsers.length === 0 && (
                    <div className="px-2 py-4 text-center text-xs text-muted-foreground">
                      Eşleşen kullanıcı yok.
                    </div>
                  )}
                </div>
              </ScrollArea>
            )}
            {toUserId && (
              <p className="text-xs text-green-600 dark:text-green-400">
                Seçilen: <span className="font-medium">{userSearch}</span>
              </p>
            )}
          </div>
        )}

        {recipientType === 'broadcast' && (
          <div className="text-sm text-muted-foreground bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-md p-3">
            Bu mesaj <strong>tüm departmanlara</strong> ve sistemdeki tüm personele iletilecek.
          </div>
        )}

        <div>
          <Label htmlFor="msg-text" className="mb-1 block">Mesaj</Label>
          <Textarea
            id="msg-text"
            value={messageText}
            onChange={(e) => setMessageText(e.target.value)}
            placeholder="Mesajınızı yazın…"
            rows={5}
            maxLength={2000}
            data-testid="textarea-message"
          />
          <p className="text-xs text-muted-foreground mt-1">
            {messageText.length}/2000 karakter
          </p>
        </div>

        <div>
          <Label htmlFor="priority-select" className="mb-1 block">Öncelik</Label>
          <Select value={priority} onValueChange={setPriority}>
            <SelectTrigger id="priority-select" className="w-48" data-testid="select-priority">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="normal">Normal</SelectItem>
              <SelectItem value="high">Yüksek</SelectItem>
              {canSendUrgent && (
                <SelectItem value="urgent" data-testid="select-priority-urgent">
                  Acil (alarm oluşturur)
                </SelectItem>
              )}
            </SelectContent>
          </Select>
          {!canSendUrgent && (
            <p
              className="text-xs text-muted-foreground mt-1"
              data-testid="text-urgent-permission-hint"
            >
              Acil mesaj gönderme yetkisi yalnızca yönetici/süpervizör
              rollerine açıktır.
            </p>
          )}
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button
            type="button"
            variant="outline"
            onClick={resetForm}
            disabled={sending}
            data-testid="button-reset"
          >
            Temizle
          </Button>
          <Button
            type="button"
            onClick={handleSend}
            disabled={sending || !messageText.trim()}
            data-testid="button-send-message"
          >
            <Send className="h-4 w-4 mr-1" />
            {sending ? 'Gönderiliyor…' : 'Gönder'}
          </Button>
        </div>
    </div>
  );

  const renderConversationsList = () => (
    <div className="flex flex-col h-full border rounded-md bg-background">
      <div className="p-3 border-b space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h3 className="font-medium text-sm flex items-center gap-1.5">
            <MessagesSquare className="h-4 w-4" />
            Konuşmalar
            {totalConversationUnread > 0 && (
              <Badge
                variant="destructive"
                className="ml-1 px-1.5 py-0 text-xs"
                data-testid="badge-conversations-total-unread"
              >
                {totalConversationUnread}
              </Badge>
            )}
          </h3>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => loadConversations()}
            disabled={loadingConversations}
            data-testid="button-refresh-conversations"
            title="Yenile"
          >
            <RefreshCw className={`h-4 w-4 ${loadingConversations ? 'animate-spin' : ''}`} />
          </Button>
        </div>
        <div className="relative">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            value={conversationSearch}
            onChange={(e) => setConversationSearch(e.target.value)}
            placeholder="İsim ara…"
            className="pl-8 h-9"
            data-testid="input-conversation-search"
          />
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={conversationDeptFilter}
            onValueChange={setConversationDeptFilter}
            open={conversationDeptOpen}
            onOpenChange={setConversationDeptOpen}
          >
            <SelectTrigger
              className="h-9 flex-1"
              data-testid="select-conversation-department"
            >
              {/*
                Task #29: Seçili departmanın okunmamış sayısını trigger
                üzerinde göster. Dropdown açık değilken bile kullanıcı
                hangi filtrenin kaç okunmamışı olduğunu görsün. SelectValue
                children olarak veriliyor, böylece Radix kendi değerini
                yazmak yerine bizim gösterdiğimizi yansıtır.
              */}
              <SelectValue placeholder="Departman">
                {(() => {
                  const opt = CONVERSATION_DEPARTMENT_FILTERS.find(
                    (o) => o.value === conversationDeptFilter,
                  );
                  const label = opt?.label || 'Departman';
                  const count = conversationUnreadByDept[conversationDeptFilter] || 0;
                  return (
                    <span className="flex items-center justify-between gap-2 w-full pr-1">
                      <span className="truncate">{label}</span>
                      {count > 0 && (
                        <span
                          className="ml-2 inline-flex items-center justify-center rounded-full bg-red-500 text-white text-[10px] font-semibold leading-none px-1.5 py-0.5 min-w-[18px]"
                          data-testid="badge-dept-unread-trigger"
                        >
                          {count > 99 ? '99+' : count}
                        </span>
                      )}
                    </span>
                  );
                })()}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {CONVERSATION_DEPARTMENT_FILTERS.map((opt) => {
                const count = conversationUnreadByDept[opt.value] || 0;
                // Use the Radix primitive directly so the unread badge can sit
                // outside of `ItemText` — that keeps the trigger label clean
                // (no badge in the trigger) while still showing the count in
                // the dropdown row.
                return (
                  <SelectPrimitive.Item
                    key={opt.value}
                    value={opt.value}
                    className="relative flex w-full cursor-default select-none items-center rounded-sm py-1.5 pl-2 pr-8 text-sm outline-none focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50"
                  >
                    <span className="absolute right-2 flex h-3.5 w-3.5 items-center justify-center">
                      <SelectPrimitive.ItemIndicator>
                        <Check className="h-4 w-4" />
                      </SelectPrimitive.ItemIndicator>
                    </span>
                    <span className="flex items-center justify-between gap-2 w-full pr-4">
                      <SelectPrimitive.ItemText>{opt.label}</SelectPrimitive.ItemText>
                      {count > 0 ? (
                        // Task #30: Badge'i tıklanabilir yap. onPointerDown
                        // ile Radix Item'in select handler'ını engelliyoruz
                        // (onClick'te kullanırsak Item zaten seçilmiş oluyor).
                        // Sonra kendi handler'ımızla filtre + ilk okunmamış
                        // konuşmayı tek hamlede açıyoruz.
                        <button
                          type="button"
                          className="ml-2 inline-flex items-center justify-center rounded-full bg-red-500 hover:bg-red-600 text-white text-[10px] font-semibold leading-none px-1.5 py-0.5 min-w-[18px] cursor-pointer transition-colors"
                          data-testid={`badge-dept-unread-${opt.value}`}
                          aria-label={`${opt.label} departmanındaki ilk okunmamış mesaja git (${count})`}
                          onPointerDown={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                          }}
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            jumpToFirstUnreadInDepartment(opt.value);
                          }}
                        >
                          {count > 99 ? '99+' : count}
                        </button>
                      ) : null}
                    </span>
                  </SelectPrimitive.Item>
                );
              })}
            </SelectContent>
          </Select>
          <label
            className="flex items-center gap-1.5 text-xs text-muted-foreground whitespace-nowrap cursor-pointer select-none"
            title="Sadece okunmamış mesajları göster"
          >
            <Switch
              checked={conversationOnlyUnread}
              onCheckedChange={setConversationOnlyUnread}
              data-testid="switch-conversation-only-unread"
            />
            <span>Okunmamış</span>
          </label>
        </div>
      </div>
      {loadingConversations && conversations.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground text-sm">Yükleniyor…</div>
      ) : filteredConversations.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground px-4">
          <MessagesSquare className="h-10 w-10 mx-auto mb-2 opacity-30" />
          {conversations.length === 0 ? (
            <>
              <p className="text-sm">Henüz birebir konuşmanız yok.</p>
              <p className="text-xs mt-1">
                Yeni Mesaj sekmesinden bir personele DM gönderdiğinizde burada görünecek.
              </p>
            </>
          ) : (
            <>
              <p className="text-sm">Eşleşen konuşma bulunamadı.</p>
              {conversationFiltersActive && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="mt-2 h-7 text-xs"
                  onClick={() => {
                    setConversationSearch('');
                    setConversationDeptFilter('all');
                    setConversationOnlyUnread(false);
                  }}
                  data-testid="button-clear-conversation-filters"
                >
                  Filtreleri temizle
                </Button>
              )}
            </>
          )}
        </div>
      ) : (
        <ScrollArea className="flex-1">
          <ul className="divide-y">
            {filteredConversations.map((conv) => {
              const isSelected = conv.user_id === selectedConvUserId;
              return (
                <li key={conv.user_id}>
                  <button
                    type="button"
                    onClick={() => handleSelectConversation(conv)}
                    data-testid={`conversation-item-${conv.user_id}`}
                    className={`w-full text-left px-3 py-2.5 hover:bg-accent transition-colors ${
                      isSelected ? 'bg-accent' : ''
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2 mb-0.5">
                      <div className="flex items-center gap-1.5 min-w-0 flex-1">
                        <span
                          className={`text-sm truncate ${
                            conv.unread_count > 0 ? 'font-semibold' : 'font-medium'
                          }`}
                        >
                          {conv.user_name}
                        </span>
                        {conv.user_role && ROLE_LABELS[conv.user_role] && (
                          <Badge
                            variant="secondary"
                            className="px-1.5 py-0 text-[10px] h-4 font-normal text-muted-foreground shrink-0"
                            data-testid={`badge-role-${conv.user_id}`}
                          >
                            {ROLE_LABELS[conv.user_role]}
                          </Badge>
                        )}
                      </div>
                      <span className="text-[10px] text-muted-foreground shrink-0 mt-0.5">
                        {conv.time_ago || ''}
                      </span>
                    </div>
                    <div className="flex items-center justify-between gap-2">
                      <span
                        className={`text-xs truncate ${
                          conv.unread_count > 0
                            ? 'text-foreground'
                            : 'text-muted-foreground'
                        }`}
                      >
                        {conv.last_from_me && (
                          <span className="text-muted-foreground">Sen: </span>
                        )}
                        {conv.last_message || '(boş mesaj)'}
                      </span>
                      {conv.unread_count > 0 && (
                        <Badge
                          variant="destructive"
                          className="px-1.5 py-0 text-[10px] h-5 shrink-0"
                          data-testid={`badge-unread-${conv.user_id}`}
                        >
                          {conv.unread_count}
                        </Badge>
                      )}
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        </ScrollArea>
      )}
    </div>
  );

  const renderThread = () => {
    if (!selectedConvUserId) {
      return (
        <div className="flex flex-col h-full items-center justify-center border rounded-md bg-background text-muted-foreground p-6 text-center">
          <MessagesSquare className="h-14 w-14 mb-3 opacity-30" />
          <p className="text-sm font-medium">Bir konuşma seçin</p>
          <p className="text-xs mt-1 max-w-xs">
            Soldaki listeden bir personele tıklayarak mesaj geçmişinizi görüntüleyin
            ve hızlı yanıt gönderin.
          </p>
          {!usersAccessDenied && users.length > 0 && (
            <div className="mt-4 w-full max-w-xs text-left">
              <p className="text-xs text-muted-foreground mb-1.5">
                veya yeni bir konuşma başlatın:
              </p>
              <Select
                value=""
                onValueChange={(uid) => {
                  const u = users.find((x) => x.id === uid);
                  if (u) handleStartConversationFromUser(u);
                }}
              >
                <SelectTrigger data-testid="select-start-conversation">
                  <SelectValue placeholder="Personel seç…" />
                </SelectTrigger>
                <SelectContent>
                  {users.slice(0, 100).map((u) => (
                    <SelectItem key={u.id} value={u.id}>
                      {u.name}
                      {u.role ? ` · ${ROLE_LABELS[u.role] || u.role}` : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>
      );
    }

    return (
      <div className="flex flex-col h-full border rounded-md bg-background overflow-hidden">
        {/* Header */}
        <div className="px-3 py-2 border-b flex items-center gap-2 bg-muted/40">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="md:hidden"
            onClick={() => {
              setSelectedConvUserId(null);
              setSelectedConvUserName('');
              setThreadMessages([]);
            }}
            data-testid="button-back-to-conversations"
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="flex-1 min-w-0">
            <div
              className="font-medium text-sm truncate"
              data-testid="text-thread-partner-name"
            >
              {selectedConvUserName || 'Konuşma'}
            </div>
            <div className="text-[11px] text-muted-foreground h-[14px]">
              {typingPartnerName ? (
                <span
                  className="text-primary font-medium"
                  data-testid="text-thread-typing-indicator"
                >
                  yazıyor…
                </span>
              ) : (
                'Birebir mesaj · Otomatik yenileme: 15 sn'
              )}
            </div>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => loadThread(selectedConvUserId, { markRead: true })}
            disabled={loadingThread}
            data-testid="button-refresh-thread"
            title="Yenile"
          >
            <RefreshCw className={`h-4 w-4 ${loadingThread ? 'animate-spin' : ''}`} />
          </Button>
        </div>

        {/* Messages */}
        <div
          ref={threadScrollRef}
          className="flex-1 overflow-y-auto p-3 space-y-2 bg-[linear-gradient(to_bottom,_hsl(var(--muted)/0.2),_transparent)]"
          data-testid="thread-message-list"
        >
          {loadingThread && threadMessages.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground text-sm">
              Yükleniyor…
            </div>
          ) : threadMessages.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <MessageSquare className="h-10 w-10 mx-auto mb-2 opacity-30" />
              <p className="text-sm">Henüz mesaj yok.</p>
              <p className="text-xs mt-1">İlk mesajı aşağıdan gönderin.</p>
            </div>
          ) : (
            threadMessages.map((m) => {
              const fromMe = m.is_from_me;
              const isDeleted = !!m.deleted;
              const isEditing = editingMessageId === m.id;
              // Recall + edit are only offered for the sender's own,
              // non-deleted messages still inside the 5 min window. Parsing
              // failures fall through as "not actionable" — better safe than
              // sorry. Both actions share the same window so a single check
              // controls the menu visibility.
              let withinActionWindow = false;
              if (fromMe && !isDeleted && m.created_at) {
                const sentAt = Date.parse(m.created_at);
                if (!Number.isNaN(sentAt)) {
                  withinActionWindow =
                    Date.now() - sentAt < Math.max(RECALL_WINDOW_MS, EDIT_WINDOW_MS);
                }
              }
              return (
                <div
                  key={m.id}
                  data-testid={`thread-message-${m.id}`}
                  className={`group flex ${fromMe ? 'justify-end' : 'justify-start'}`}
                >
                  {/* Action menu sits outside the bubble for own messages so it
                      doesn't affect the bubble width and stays clickable.
                      Hidden while inline-edit mode is open to keep focus on
                      the textarea. */}
                  {fromMe && withinActionWindow && !isEditing && (
                    <div className="self-center mr-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="h-6 w-6 p-0"
                            data-testid={`button-message-menu-${m.id}`}
                            title="Mesaj seçenekleri"
                            aria-label="Mesaj seçenekleri"
                          >
                            <MoreVertical className="h-3.5 w-3.5" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-40">
                          <DropdownMenuItem
                            onSelect={(e) => {
                              e.preventDefault();
                              beginEditMessage(m);
                            }}
                            data-testid={`button-edit-message-${m.id}`}
                          >
                            <Pencil className="h-3.5 w-3.5 mr-2" />
                            Düzenle
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onSelect={(e) => {
                              e.preventDefault();
                              handleRecallMessage(m.id);
                            }}
                            className="text-destructive focus:text-destructive"
                            data-testid={`button-recall-message-${m.id}`}
                          >
                            <Trash2 className="h-3.5 w-3.5 mr-2" />
                            Geri al
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  )}
                  <div
                    className={`max-w-[78%] rounded-lg px-3 py-1.5 shadow-sm ${
                      isDeleted
                        ? 'bg-muted/60 text-muted-foreground italic border border-dashed'
                        : fromMe
                          ? 'bg-primary text-primary-foreground rounded-br-sm'
                          : 'bg-muted rounded-bl-sm'
                    } ${
                      !isDeleted && m.priority === 'urgent'
                        ? 'ring-2 ring-destructive'
                        : ''
                    }`}
                  >
                    {!isDeleted && m.priority === 'urgent' && (
                      <div className="flex items-center gap-1 text-[10px] font-semibold mb-0.5 opacity-90">
                        <AlertCircle className="h-3 w-3" /> Acil
                      </div>
                    )}
                    {isDeleted ? (
                      <p
                        className="text-sm break-words"
                        data-testid={`text-message-recalled-${m.id}`}
                      >
                        Bu mesaj kaldırıldı
                      </p>
                    ) : isEditing ? (
                      // Inline edit mode — keyboard shortcuts mirror the reply
                      // box (Enter saves, Shift+Enter newline, Esc cancels).
                      <div
                        className="flex flex-col gap-1.5 min-w-[220px]"
                        data-testid={`edit-message-${m.id}`}
                      >
                        <Textarea
                          value={editingDraft}
                          onChange={(e) => setEditingDraft(e.target.value)}
                          rows={2}
                          maxLength={2000}
                          autoFocus
                          disabled={savingEdit}
                          className="resize-none min-h-[40px] max-h-32 text-sm bg-background text-foreground"
                          data-testid={`textarea-edit-message-${m.id}`}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                              e.preventDefault();
                              if (!savingEdit) handleSubmitEditMessage(m.id);
                            } else if (e.key === 'Escape') {
                              e.preventDefault();
                              cancelEditMessage();
                            }
                          }}
                        />
                        <div className="flex items-center justify-end gap-1.5">
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className={`h-6 px-2 text-[11px] ${
                              fromMe ? 'text-primary-foreground hover:text-primary-foreground hover:bg-primary-foreground/10' : ''
                            }`}
                            onClick={cancelEditMessage}
                            disabled={savingEdit}
                            data-testid={`button-cancel-edit-${m.id}`}
                          >
                            <X className="h-3 w-3 mr-1" /> Vazgeç
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="secondary"
                            className="h-6 px-2 text-[11px]"
                            onClick={() => handleSubmitEditMessage(m.id)}
                            disabled={savingEdit || !editingDraft.trim()}
                            data-testid={`button-save-edit-${m.id}`}
                          >
                            {savingEdit ? 'Kaydediliyor…' : 'Kaydet'}
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <p className="text-sm whitespace-pre-wrap break-words">
                        {m.message}
                      </p>
                    )}
                    <div
                      className={`flex items-center gap-1 mt-0.5 text-[10px] ${
                        isDeleted
                          ? 'text-muted-foreground'
                          : fromMe
                            ? 'opacity-80 justify-end'
                            : 'text-muted-foreground'
                      }`}
                    >
                      <span>{m.time_ago || ''}</span>
                      {/* "düzenlendi" rozeti — recall edilmiş mesajlarda
                          gösterilmez (mezar taşı tek sinyal kalmalı) ve
                          edit modunda da gizlenir (textarea zaten görünüyor).
                          Task #39: rozet bir Popover trigger'ı; tıklayınca
                          tüm önceki sürümleri kronolojik sırada gösterir. */}
                      {!isDeleted && !isEditing && m.edited && (
                        <Popover
                          onOpenChange={(open) => {
                            // Lazy-fetch on first open. Refetch on reopen
                            // if the previous attempt errored OR if the
                            // message has been edited since the cache was
                            // populated (compare cached current_message).
                            if (!open) return;
                            const cached = editHistoryByMsg[m.id];
                            const isStale =
                              cached &&
                              !cached.loading &&
                              !cached.error &&
                              cached.current_message !== (m.message || '');
                            if (!cached || cached.error || isStale) {
                              fetchEditHistory(m.id);
                            }
                          }}
                        >
                          <PopoverTrigger asChild>
                            <button
                              type="button"
                              className="italic underline decoration-dotted underline-offset-2 hover:text-foreground focus:outline-none focus:ring-1 focus:ring-ring rounded-sm"
                              data-testid={`text-thread-edited-${m.id}`}
                              aria-label="Düzenleme geçmişini göster"
                              title={m.edited_at ? `Son düzenleme: ${m.edited_at}` : 'Düzenleme geçmişini göster'}
                            >
                              (düzenlendi)
                            </button>
                          </PopoverTrigger>
                          <PopoverContent
                            align={fromMe ? 'end' : 'start'}
                            className="w-80 max-w-[90vw] p-0"
                            data-testid={`popover-thread-edit-history-${m.id}`}
                          >
                            <div className="px-3 py-2 border-b text-xs font-medium">
                              Düzenleme geçmişi
                            </div>
                            <div className="max-h-72 overflow-y-auto p-3 space-y-2 text-xs">
                              {(() => {
                                const entry = editHistoryByMsg[m.id];
                                if (!entry || entry.loading) {
                                  return (
                                    <div className="text-muted-foreground italic">
                                      Yükleniyor…
                                    </div>
                                  );
                                }
                                if (entry.error) {
                                  return (
                                    <div className="text-destructive">
                                      {entry.error}
                                    </div>
                                  );
                                }
                                const versions = entry.history || [];
                                if (versions.length === 0) {
                                  return (
                                    <div className="text-muted-foreground italic">
                                      Önceki sürüm bulunamadı.
                                    </div>
                                  );
                                }
                                // Render oldest → newest, then the current
                                // (live) text last so the user sees the
                                // full timeline of "what was written when".
                                return (
                                  <>
                                    {versions.map((v, i) => (
                                      <div
                                        key={`${m.id}-v-${i}`}
                                        className="border-l-2 border-muted pl-2"
                                        data-testid={`row-thread-edit-history-${m.id}-${i}`}
                                      >
                                        <div className="text-muted-foreground text-[10px]">
                                          {(v.edited_by_name || 'Bilinmeyen')}
                                          {v.edited_at ? ` · ${v.edited_at}` : ''}
                                        </div>
                                        <div className="whitespace-pre-wrap break-words">
                                          {v.message || ''}
                                        </div>
                                      </div>
                                    ))}
                                    <div
                                      className="border-l-2 border-primary pl-2"
                                      data-testid={`row-thread-edit-current-${m.id}`}
                                    >
                                      <div className="text-muted-foreground text-[10px]">
                                        Şu anki sürüm
                                        {m.edited_at ? ` · ${m.edited_at}` : ''}
                                      </div>
                                      <div className="whitespace-pre-wrap break-words">
                                        {entry.current_message || m.message || ''}
                                      </div>
                                    </div>
                                  </>
                                );
                              })()}
                            </div>
                          </PopoverContent>
                        </Popover>
                      )}
                      {fromMe && !isDeleted && (
                        <CheckCheck
                          className={`h-3 w-3 ${
                            m.read ? 'opacity-100' : 'opacity-40'
                          }`}
                        />
                      )}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Reply input */}
        <div className="border-t p-2 flex flex-col gap-2 bg-background">
          {/* Priority selector — defaults to "normal", resets after each send.
              "Acil" gets a strong red treatment so users know it triggers an alarm. */}
          <div
            className="flex items-center gap-1.5 flex-wrap"
            role="radiogroup"
            aria-label="Mesaj önceliği"
          >
            <span className="text-xs text-muted-foreground mr-1">Öncelik:</span>
            <Button
              type="button"
              size="sm"
              variant={threadPriority === 'normal' ? 'default' : 'outline'}
              className="h-7 px-2 text-xs"
              onClick={() => setThreadPriority('normal')}
              role="radio"
              aria-checked={threadPriority === 'normal'}
              data-testid="button-thread-priority-normal"
            >
              Normal
            </Button>
            <Button
              type="button"
              size="sm"
              variant={threadPriority === 'high' ? 'default' : 'outline'}
              className="h-7 px-2 text-xs"
              onClick={() => setThreadPriority('high')}
              role="radio"
              aria-checked={threadPriority === 'high'}
              data-testid="button-thread-priority-high"
            >
              Yüksek
            </Button>
            {canSendUrgent && (
              <Button
                type="button"
                size="sm"
                variant={threadPriority === 'urgent' ? 'destructive' : 'outline'}
                className={`h-7 px-2 text-xs ${
                  threadPriority === 'urgent'
                    ? 'ring-2 ring-destructive ring-offset-1'
                    : 'border-destructive/40 text-destructive hover:bg-destructive/10'
                }`}
                onClick={() => setThreadPriority('urgent')}
                role="radio"
                aria-checked={threadPriority === 'urgent'}
                data-testid="button-thread-priority-urgent"
                title="Acil — alıcıya alarm oluşturur"
              >
                <AlertCircle className="h-3 w-3 mr-1" />
                Acil
              </Button>
            )}
            {canSendUrgent && threadPriority === 'urgent' && (
              <span
                className="text-[11px] text-destructive font-medium"
                data-testid="text-thread-priority-urgent-hint"
              >
                Alarm oluşturulacak
              </span>
            )}
            {!canSendUrgent && (
              <span
                className="text-[11px] text-muted-foreground"
                data-testid="text-thread-urgent-permission-hint"
                title="Acil mesaj yalnızca yönetici/süpervizör rollerine açıktır"
              >
                Acil yetkisiz
              </span>
            )}
          </div>

          <div className="flex items-end gap-2">
            <Textarea
              value={threadReply}
              onChange={(e) => {
                setThreadReply(e.target.value);
                // Fire a throttled typing signal so the partner sees
                // "yazıyor…" in their thread header. Empty input still
                // counts as activity (e.g. backspacing) — that's fine
                // since the indicator auto-clears after a few seconds.
                if (e.target.value.length > 0) {
                  emitTyping();
                }
              }}
              placeholder="Mesajınızı yazın… (Enter göndermek için, Shift+Enter yeni satır)"
              rows={1}
              maxLength={2000}
              className={`resize-none min-h-[40px] max-h-32 ${
                threadPriority === 'urgent'
                  ? 'border-destructive focus-visible:ring-destructive'
                  : ''
              }`}
              data-testid="textarea-thread-reply"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  if (threadReply.trim() && !sendingThreadReply) {
                    handleSendThreadReply();
                  }
                }
              }}
            />
            <Button
              type="button"
              onClick={handleSendThreadReply}
              disabled={sendingThreadReply || !threadReply.trim()}
              variant={threadPriority === 'urgent' ? 'destructive' : 'default'}
              data-testid="button-send-thread-reply"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Urgent confirmation: a single extra step to avoid accidental
            alarms. The destructive action is auto-focused so a second Enter
            keypress confirms — keeping the flow fast for intentional sends. */}
        <AlertDialog
          open={urgentConfirmOpen}
          onOpenChange={(open) => {
            if (!sendingThreadReply) setUrgentConfirmOpen(open);
          }}
        >
          <AlertDialogContent
            data-testid="dialog-urgent-confirm"
            onOpenAutoFocus={(e) => {
              e.preventDefault();
              const node = e.currentTarget?.querySelector?.(
                '[data-testid="button-urgent-confirm"]',
              );
              node?.focus();
            }}
          >
            <AlertDialogHeader>
              <AlertDialogTitle className="flex items-center gap-2">
                <AlertCircle className="h-5 w-5 text-destructive" />
                Acil mesaj göndermek istediğinize emin misiniz?
              </AlertDialogTitle>
              <AlertDialogDescription>
                Acil mesaj alıcıda alarm oluşturur. Onaylamak için Enter'a,
                vazgeçmek için Esc'e basabilirsiniz.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel data-testid="button-urgent-cancel">
                Vazgeç
              </AlertDialogCancel>
              <AlertDialogAction
                onClick={handleConfirmUrgentSend}
                disabled={sendingThreadReply}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                data-testid="button-urgent-confirm"
              >
                <AlertCircle className="h-4 w-4 mr-1" />
                Acil Gönder
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    );
  };

  const renderConversations = () => (
    <div className="grid grid-cols-1 md:grid-cols-[320px_1fr] gap-3 h-[600px]">
      <div
        className={`md:block ${selectedConvUserId ? 'hidden' : 'block'} h-full overflow-hidden`}
      >
        {renderConversationsList()}
      </div>
      <div
        className={`md:block ${selectedConvUserId ? 'block' : 'hidden'} h-full overflow-hidden`}
      >
        {renderThread()}
      </div>
    </div>
  );

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
          {renderConversationsList()}
        </div>
        <div
          className="block h-[440px] md:h-full overflow-hidden"
          data-testid="pane-detail"
        >
          {selectedConvUserId ? renderThread() : renderInboxList()}
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
          {renderCompose()}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default InternalChatTab;
