import axios from 'axios';

/**
 * Inline mesaj düzenleme submit'i. Optimistic update + sunucu round-trip.
 * Aynı metinse no-op short-circuit yapar (geçmişe kirli giriş engellenir).
 * 403 → "sadece kendi mesajınızı düzenleyebilirsiniz" özel mesajı.
 */
export async function submitEditMessage({
  messageId,
  editingDraft,
  threadMessages,
  setThreadMessages,
  setInbox,
  setSavingEdit,
  cancelEditMessage,
  selectedConvUserId,
  loadThread,
  loadConversations,
  toast,
}) {
  if (!messageId) return;
  const trimmed = (editingDraft || '').trim();
  if (!trimmed) {
    toast({ title: 'Boş mesaj', description: 'Mesaj metni boş olamaz.', variant: 'destructive' });
    return;
  }
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
    const patch = (m) => (m.id === messageId
      ? { ...m, message: trimmed, edited: true, edited_at: editedAt }
      : m);
    setThreadMessages((prev) => prev.map(patch));
    setInbox((prev) => prev.map(patch));
    cancelEditMessage();
    toast({
      title: 'Mesaj güncellendi',
      description: 'Karşı tarafta "düzenlendi" etiketi ile görünecek.',
    });
    if (selectedConvUserId) loadThread(selectedConvUserId, { silent: true });
    loadConversations(true);
  } catch (err) {
    const status = err.response?.status;
    let description = err.response?.data?.detail || err.message;
    if (status === 403) description = 'Sadece kendi gönderdiğiniz mesajları düzenleyebilirsiniz.';
    toast({ title: 'Mesaj düzenlenemedi', description, variant: 'destructive' });
    setSavingEdit(false);
  }
}

/**
 * Mesaj geri alma (recall). window.confirm ile destructive onay; başarılıysa
 * tombstone optimistik render edilir, sunucudan canonical yanıt gelene kadar.
 */
export async function recallMessage({
  messageId,
  setThreadMessages,
  selectedConvUserId,
  loadThread,
  loadConversations,
  toast,
}) {
  if (!messageId) return;
  const ok = window.confirm(
    'Bu mesajı geri almak istediğinize emin misiniz? Karşı tarafta "Bu mesaj kaldırıldı" olarak görünecek.',
  );
  if (!ok) return;
  try {
    const res = await axios.delete(`/messaging/internal/${encodeURIComponent(messageId)}`);
    setThreadMessages((prev) => prev.map((m) => (m.id === messageId
      ? { ...m, deleted: true, message: '' }
      : m)));
    toast({
      title: 'Mesaj geri alındı',
      description: res.data?.alarm_cleared
        ? 'Acil alarmı da otomatik kapatıldı.'
        : 'Karşı tarafta "Bu mesaj kaldırıldı" olarak görünecek.',
    });
    if (selectedConvUserId) loadThread(selectedConvUserId, { silent: true });
    loadConversations(true);
  } catch (err) {
    const status = err.response?.status;
    let description = err.response?.data?.detail || err.message;
    if (status === 403) description = 'Sadece kendi gönderdiğiniz mesajları geri alabilirsiniz.';
    toast({ title: 'Mesaj geri alınamadı', description, variant: 'destructive' });
  }
}

/**
 * Düzenleme geçmişi (lazy popover). İlk açılışta çağrılır; setter mevcut
 * cache'i bozmadan yalnızca ilgili messageId entry'sini günceller.
 */
export async function fetchEditHistoryFor({ messageId, setEditHistoryByMsg }) {
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
    const detail = err?.response?.data?.detail || err?.message || 'Geçmiş yüklenemedi';
    setEditHistoryByMsg((prev) => ({
      ...prev,
      [messageId]: { loading: false, error: detail, history: [], current_message: '' },
    }));
  }
}

/**
 * Inbox'tan tek mesaj okundu işaretleme. wasUnread state'ten okunur ki
 * çift tıklamada bell counter eksiye kaçmasın.
 */
export async function markInboxMessageRead({
  messageId,
  inbox,
  setInbox,
  setUnreadCount,
  decrementInternalUnread,
  toast,
}) {
  const wasUnread = inbox.find((m) => m.id === messageId)?.read === false;
  try {
    await axios.put(`/messaging/internal/${messageId}/mark-read`);
    setInbox((prev) => prev.map((m) => (m.id === messageId ? { ...m, read: true } : m)));
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
}

/**
 * Thread reply gönder. 403 + urgent kombinasyonu için özel mesaj + priority
 * reset (kullanıcı yeniden denerken otomatik bloklanmasın).
 */
export async function sendThreadReply({
  threadReply,
  threadPriority,
  selectedConvUserId,
  setThreadReply,
  setThreadPriority,
  setSendingThreadReply,
  loadThread,
  loadConversations,
  toast,
}) {
  const trimmed = threadReply.trim();
  if (!trimmed || !selectedConvUserId) return;
  setSendingThreadReply(true);
  try {
    await axios.post('/messaging/internal/send', null, {
      params: { message: trimmed, to_user_id: selectedConvUserId, priority: threadPriority },
    });
    setThreadReply('');
    setThreadPriority('normal');
    await loadThread(selectedConvUserId, { silent: true });
    loadConversations(true);
  } catch (err) {
    const status = err.response?.status;
    const serverDetail = err.response?.data?.detail;
    let description = serverDetail || err.message;
    if (status === 403) {
      if (threadPriority === 'urgent') {
        description = serverDetail
          || 'Acil mesaj gönderme yetkiniz yok. Bu kanal yalnızca yönetici/süpervizör rollerine açıktır.';
        setThreadPriority('normal');
      } else {
        description = 'Bu işlem için yetkiniz yok. Yöneticinizden "Mesajlaşma" izni isteyin.';
      }
    }
    toast({ title: 'Yanıt gönderilemedi', description, variant: 'destructive' });
  } finally {
    setSendingThreadReply(false);
  }
}

/**
 * Compose dialog'undan yeni mesaj gönder. recipientType'a göre param mapping;
 * 'broadcast' to_department/to_user_id'siz POST eder (backend tüm departmanlara dağıtır).
 */
export async function sendNewMessage({
  messageText,
  priority,
  recipientType,
  toDepartment,
  toUserId,
  setPriority,
  setSending,
  resetForm,
  loadInbox,
  toast,
}) {
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
  if (recipientType === 'department') params.to_department = toDepartment;
  else if (recipientType === 'user') params.to_user_id = toUserId;

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
        description = serverDetail
          || 'Acil mesaj gönderme yetkiniz yok. Bu kanal yalnızca yönetici/süpervizör rollerine açıktır.';
        setPriority('normal');
      } else {
        description = 'Bu işlem için yetkiniz yok. Yöneticinizden "Mesajlaşma" izni isteyin.';
      }
    }
    toast({ title: 'Gönderim başarısız', description, variant: 'destructive' });
  } finally {
    setSending(false);
  }
}
