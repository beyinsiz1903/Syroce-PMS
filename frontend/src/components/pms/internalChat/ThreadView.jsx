import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
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
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  MessagesSquare, MessageSquare, RefreshCw, ArrowLeft,
  AlertCircle, CheckCheck, MoreVertical, Trash2, Pencil, X, Send,
} from 'lucide-react';
import { ROLE_LABELS, RECALL_WINDOW_MS, EDIT_WINDOW_MS } from './constants';
import { useTranslation } from 'react-i18next';

const ThreadView = ({
  selectedConvUserId,
  selectedConvUserName,
  setSelectedConvUserId,
  setSelectedConvUserName,
  setThreadMessages,
  threadMessages,
  loadingThread,
  loadThread,
  threadScrollRef,
  typingPartnerName,
  usersAccessDenied,
  users,
  handleStartConversationFromUser,
  editingMessageId,
  editingDraft, setEditingDraft,
  savingEdit,
  beginEditMessage,
  cancelEditMessage,
  handleSubmitEditMessage,
  handleRecallMessage,
  editHistoryByMsg,
  fetchEditHistory,
  threadReply, setThreadReply,
  threadPriority, setThreadPriority,
  emitTyping,
  handleSendThreadReply,
  sendingThreadReply,
  canSendUrgent,
  urgentConfirmOpen, setUrgentConfirmOpen,
  handleConfirmUrgentSend,
}) => {
  const { t } = useTranslation();
  if (!selectedConvUserId) {
    return (
      <div className="flex flex-col h-full items-center justify-center border rounded-md bg-background text-muted-foreground p-6 text-center">
        <MessagesSquare className="h-14 w-14 mb-3 opacity-30" />
        <p className="text-sm font-medium">{t('cm.components_pms_internalChat_ThreadView.bir_konusma_secin')}</p>
        <p className="text-xs mt-1 max-w-xs">
          {t('cm.components_pms_internalChat_ThreadView.soldaki_listeden_bir_personele_tiklayara')}
        </p>
        {!usersAccessDenied && users.length > 0 && (
          <div className="mt-4 w-full max-w-xs text-left">
            <p className="text-xs text-muted-foreground mb-1.5">
              {t('cm.components_pms_internalChat_ThreadView.veya_yeni_bir_konusma_baslatin')}
            </p>
            <Select
              value=""
              onValueChange={(uid) => {
                const u = users.find((x) => x.id === uid);
                if (u) handleStartConversationFromUser(u);
              }}
            >
              <SelectTrigger data-testid="select-start-conversation">
                <SelectValue placeholder={t('cm.components_pms_internalChat_ThreadView.personel_sec')} />
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
          className="shrink-0"
          title="Konuşmalara dön"
          aria-label="Konuşmalara dön"
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
                {t('cm.components_pms_internalChat_ThreadView.yaziyor')}
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
          title={t('cm.components_pms_internalChat_ThreadView.yenile')}
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
            {t('cm.components_pms_internalChat_ThreadView.yukleniyor')}
          </div>
        ) : threadMessages.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <MessageSquare className="h-10 w-10 mx-auto mb-2 opacity-30" />
            <p className="text-sm">{t('cm.components_pms_internalChat_ThreadView.henuz_mesaj_yok')}</p>
            <p className="text-xs mt-1">{t('cm.components_pms_internalChat_ThreadView.ilk_mesaji_asagidan_gonderin')}</p>
          </div>
        ) : (
          threadMessages.map((m) => {
            const fromMe = m.is_from_me;
            const isDeleted = !!m.deleted;
            const isEditing = editingMessageId === m.id;
            // Recall + edit are only offered for the sender's own,
            // non-deleted messages still inside the 5 min window.
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
                          title={t('cm.components_pms_internalChat_ThreadView.mesaj_secenekleri')}
                          aria-label={t('cm.components_pms_internalChat_ThreadView.mesaj_secenekleri_0a444')}
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
                          {t('cm.components_pms_internalChat_ThreadView.duzenle')}
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
                      {t('cm.components_pms_internalChat_ThreadView.bu_mesaj_kaldirildi')}
                    </p>
                  ) : isEditing ? (
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
                          <X className="h-3 w-3 mr-1" /> {t('cm.components_pms_internalChat_ThreadView.vazgec')}
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
                    {!isDeleted && !isEditing && m.edited && (
                      <Popover
                        onOpenChange={(open) => {
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
                            aria-label={t('cm.components_pms_internalChat_ThreadView.duzenleme_gecmisini_goster')}
                            title={m.edited_at ? `Son düzenleme: ${m.edited_at}` : 'Düzenleme geçmişini göster'}
                          >
                            {t('cm.components_pms_internalChat_ThreadView.duzenlendi')}
                          </button>
                        </PopoverTrigger>
                        <PopoverContent
                          align={fromMe ? 'end' : 'start'}
                          className="w-80 max-w-[90vw] p-0"
                          data-testid={`popover-thread-edit-history-${m.id}`}
                        >
                          <div className="px-3 py-2 border-b text-xs font-medium">
                            {t('cm.components_pms_internalChat_ThreadView.duzenleme_gecmisi')}
                          </div>
                          <div className="max-h-72 overflow-y-auto p-3 space-y-2 text-xs">
                            {(() => {
                              const entry = editHistoryByMsg[m.id];
                              if (!entry || entry.loading) {
                                return (
                                  <div className="text-muted-foreground italic">
                                    {t('cm.components_pms_internalChat_ThreadView.yukleniyor_b597b')}
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
                                    {t('cm.components_pms_internalChat_ThreadView.onceki_surum_bulunamadi')}
                                  </div>
                                );
                              }
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
                                      {t('cm.components_pms_internalChat_ThreadView.su_anki_surum')}
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
        <div
          className="flex items-center gap-1.5 flex-wrap"
          role="radiogroup"
          aria-label={t('cm.components_pms_internalChat_ThreadView.mesaj_onceligi')}
        >
          <span className="text-xs text-muted-foreground mr-1">{t('cm.components_pms_internalChat_ThreadView.oncelik')}</span>
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
            {t('cm.components_pms_internalChat_ThreadView.yuksek')}
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
              title={t('cm.components_pms_internalChat_ThreadView.acil_aliciya_alarm_olusturur')}
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
              {t('cm.components_pms_internalChat_ThreadView.alarm_olusturulacak')}
            </span>
          )}
          {!canSendUrgent && (
            <span
              className="text-[11px] text-muted-foreground"
              data-testid="text-thread-urgent-permission-hint"
              title={t('cm.components_pms_internalChat_ThreadView.acil_mesaj_yalnizca_yonetici_supervizor_')}
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
              if (e.target.value.length > 0) {
                emitTyping();
              }
            }}
            placeholder={t('cm.components_pms_internalChat_ThreadView.mesajinizi_yazin_enter_gondermek_icin_sh')}
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

      {/* Urgent confirmation dialog */}
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
              {t('cm.components_pms_internalChat_ThreadView.acil_mesaj_gondermek_istediginize_emin_m')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('cm.components_pms_internalChat_ThreadView.acil_mesaj_alicida_alarm_olusturur_onayl')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="button-urgent-cancel">
              {t('cm.components_pms_internalChat_ThreadView.vazgec_bf814')}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmUrgentSend}
              disabled={sendingThreadReply}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              data-testid="button-urgent-confirm"
            >
              <AlertCircle className="h-4 w-4 mr-1" />
              {t('cm.components_pms_internalChat_ThreadView.acil_gonder')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};

export default ThreadView;
