import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useToast } from '@/hooks/use-toast';
import {
  Inbox, Send, RefreshCw, AlertCircle, CheckCircle, Building2,
  Users, MessageSquare, Search, Reply, MessagesSquare, ArrowLeft, CheckCheck
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

const POLL_INTERVAL_MS = 15000;

const InternalChatTab = ({ currentUser }) => {
  const { toast } = useToast();
  const [activeSubTab, setActiveSubTab] = useState('inbox');

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
  const [sendingThreadReply, setSendingThreadReply] = useState(false);
  const [conversationSearch, setConversationSearch] = useState('');

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
      setThreadMessages([]);
      loadThread(conv.user_id, { markRead: true });
    },
    [loadThread],
  );

  const handleSendThreadReply = useCallback(async () => {
    const trimmed = threadReply.trim();
    if (!trimmed || !selectedConvUserId) return;
    setSendingThreadReply(true);
    try {
      await axios.post('/messaging/internal/send', null, {
        params: {
          message: trimmed,
          to_user_id: selectedConvUserId,
          priority: 'normal',
        },
      });
      setThreadReply('');
      // Refresh thread + conversation list
      await loadThread(selectedConvUserId, { silent: true });
      loadConversations(true);
    } catch (err) {
      const status = err.response?.status;
      let description = err.response?.data?.detail || err.message;
      if (status === 403) {
        description = 'Bu işlem için yetkiniz yok. Yöneticinizden "Mesajlaşma" izni isteyin.';
      }
      toast({ title: 'Yanıt gönderilemedi', description, variant: 'destructive' });
    } finally {
      setSendingThreadReply(false);
    }
  }, [threadReply, selectedConvUserId, loadThread, loadConversations, toast]);

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

  useEffect(() => {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    pollTimerRef.current = setInterval(() => loadInbox(true), POLL_INTERVAL_MS);
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, [loadInbox]);

  useEffect(() => {
    if (conversationPollTimerRef.current) clearInterval(conversationPollTimerRef.current);
    conversationPollTimerRef.current = setInterval(
      () => loadConversations(true),
      POLL_INTERVAL_MS,
    );
    return () => {
      if (conversationPollTimerRef.current) clearInterval(conversationPollTimerRef.current);
    };
  }, [loadConversations]);

  // Poll the open thread every 15s so incoming messages from the partner
  // appear without a manual refresh. Only runs while a thread is selected.
  useEffect(() => {
    if (threadPollTimerRef.current) clearInterval(threadPollTimerRef.current);
    if (!selectedConvUserId) return;
    threadPollTimerRef.current = setInterval(() => {
      loadThread(selectedConvUserId, { silent: true, markRead: true });
    }, POLL_INTERVAL_MS);
    return () => {
      if (threadPollTimerRef.current) clearInterval(threadPollTimerRef.current);
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

  const filteredUsers = useMemo(() => {
    if (!userSearch.trim()) return users.slice(0, 50);
    const q = userSearch.trim().toLocaleLowerCase('tr');
    return users
      .filter(
        (u) =>
          (u.name || '').toLocaleLowerCase('tr').includes(q) ||
          (u.email || '').toLocaleLowerCase('tr').includes(q),
      )
      .slice(0, 50);
  }, [users, userSearch]);

  const filteredConversations = useMemo(() => {
    if (!conversationSearch.trim()) return conversations;
    const q = conversationSearch.trim().toLocaleLowerCase('tr');
    return conversations.filter((c) =>
      (c.user_name || '').toLocaleLowerCase('tr').includes(q),
    );
  }, [conversations, conversationSearch]);

  const totalConversationUnread = useMemo(
    () => conversations.reduce((sum, c) => sum + (c.unread_count || 0), 0),
    [conversations],
  );

  const markAsRead = useCallback(
    async (messageId) => {
      try {
        await axios.put(`/messaging/internal/${messageId}/mark-read`);
        setInbox((prev) =>
          prev.map((m) => (m.id === messageId ? { ...m, read: true } : m)),
        );
        setUnreadCount((c) => Math.max(0, c - 1));
      } catch (err) {
        toast({
          title: 'İşaretleme başarısız',
          description: err.response?.data?.detail || err.message,
          variant: 'destructive',
        });
      }
    },
    [toast],
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
        setActiveSubTab('conversations');
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
      setActiveSubTab('compose');
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
      let description = err.response?.data?.detail || err.message;
      if (status === 403) {
        description = 'Bu işlem için yetkiniz yok. Yöneticinizden "Mesajlaşma" izni isteyin.';
      }
      toast({ title: 'Gönderim başarısız', description, variant: 'destructive' });
    } finally {
      setSending(false);
    }
  };

  const renderInbox = () => (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Inbox className="h-5 w-5" /> Gelen Kutusu
              {unreadCount > 0 && (
                <Badge variant="destructive" data-testid="badge-unread-count">
                  {unreadCount} okunmamış
                </Badge>
              )}
            </CardTitle>
            <CardDescription>
              {myDepartment && (
                <>
                  Departmanım: <span className="font-medium">{myDepartment}</span>
                  {' · '}
                </>
              )}
              Otomatik yenileme: 15 sn
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
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
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {loadingInbox && inbox.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">Yükleniyor…</div>
        ) : inbox.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <MessageSquare className="h-12 w-12 mx-auto mb-3 opacity-30" />
            <p>Henüz mesaj yok.</p>
            <p className="text-sm mt-1">Yeni Mesaj sekmesinden departmanlara veya kişilere mesaj gönderebilirsiniz.</p>
          </div>
        ) : (
          <ScrollArea className="h-[500px] pr-2">
            <div className="space-y-2">
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
                      {!msg.read && (
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
                    </div>
                  </div>
                  <p className="text-sm whitespace-pre-wrap break-words">{msg.message}</p>
                </div>
              ))}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );

  const renderCompose = () => (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Send className="h-5 w-5" /> Yeni Mesaj
        </CardTitle>
        <CardDescription>
          Bir departmana, belirli bir personele veya tüm otele mesaj gönderin.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
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
            <div className="relative">
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
                      <div className="font-medium">{u.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {ROLE_LABELS[u.role] || u.role}
                        {u.email ? ` · ${u.email}` : ''}
                      </div>
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
              <SelectItem value="urgent">Acil (alarm oluşturur)</SelectItem>
            </SelectContent>
          </Select>
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
      </CardContent>
    </Card>
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
            <p className="text-sm">Eşleşen konuşma bulunamadı.</p>
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
                      <span
                        className={`text-sm truncate ${
                          conv.unread_count > 0 ? 'font-semibold' : 'font-medium'
                        }`}
                      >
                        {conv.user_name}
                      </span>
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
            <div className="text-[11px] text-muted-foreground">
              Birebir mesaj · Otomatik yenileme: 15 sn
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
              return (
                <div
                  key={m.id}
                  data-testid={`thread-message-${m.id}`}
                  className={`flex ${fromMe ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[78%] rounded-lg px-3 py-1.5 shadow-sm ${
                      fromMe
                        ? 'bg-primary text-primary-foreground rounded-br-sm'
                        : 'bg-muted rounded-bl-sm'
                    } ${m.priority === 'urgent' ? 'ring-2 ring-destructive' : ''}`}
                  >
                    {m.priority === 'urgent' && (
                      <div className="flex items-center gap-1 text-[10px] font-semibold mb-0.5 opacity-90">
                        <AlertCircle className="h-3 w-3" /> Acil
                      </div>
                    )}
                    <p className="text-sm whitespace-pre-wrap break-words">
                      {m.message}
                    </p>
                    <div
                      className={`flex items-center gap-1 mt-0.5 text-[10px] ${
                        fromMe ? 'opacity-80 justify-end' : 'text-muted-foreground'
                      }`}
                    >
                      <span>{m.time_ago || ''}</span>
                      {fromMe && (
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
        <div className="border-t p-2 flex items-end gap-2 bg-background">
          <Textarea
            value={threadReply}
            onChange={(e) => setThreadReply(e.target.value)}
            placeholder="Mesajınızı yazın… (Enter göndermek için, Shift+Enter yeni satır)"
            rows={1}
            maxLength={2000}
            className="resize-none min-h-[40px] max-h-32"
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
            data-testid="button-send-thread-reply"
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
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

  return (
    <div className="space-y-4">
      <Tabs value={activeSubTab} onValueChange={setActiveSubTab}>
        <TabsList>
          <TabsTrigger value="inbox" data-testid="subtab-inbox">
            <Inbox className="h-4 w-4 mr-1" />
            Gelen Kutusu
            {unreadCount > 0 && (
              <Badge variant="destructive" className="ml-2 px-1.5 py-0 text-xs">
                {unreadCount}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="conversations" data-testid="subtab-conversations">
            <MessagesSquare className="h-4 w-4 mr-1" />
            Konuşmalar
            {totalConversationUnread > 0 && (
              <Badge
                variant="destructive"
                className="ml-2 px-1.5 py-0 text-xs"
                data-testid="badge-subtab-conversations-unread"
              >
                {totalConversationUnread}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="compose" data-testid="subtab-compose">
            <Send className="h-4 w-4 mr-1" />
            Yeni Mesaj
          </TabsTrigger>
        </TabsList>
        <TabsContent value="inbox" className="mt-4">
          {renderInbox()}
        </TabsContent>
        <TabsContent value="conversations" className="mt-4">
          {renderConversations()}
        </TabsContent>
        <TabsContent value="compose" className="mt-4">
          {renderCompose()}
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default InternalChatTab;
