import { Badge as BadgeUI } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Inbox, AlertCircle, CheckCircle, MessageSquare, Reply,
} from 'lucide-react';

const InboxList = ({
  inbox,
  unreadCount,
  loadingInbox,
  showUnreadOnly,
  markAsRead,
  handleReply,
  embedded = false,
}) => (
  <div className={`flex flex-col h-full bg-background overflow-hidden ${embedded ? '' : 'border rounded-md'}`}>
    {!embedded && (
    <div className="px-3 py-2 border-b flex items-center justify-between gap-2 bg-muted/20">
      <div className="flex items-center gap-2 text-sm font-medium">
        <Inbox className="h-4 w-4" /> Gelen Kutusu
        {unreadCount > 0 && (
          <BadgeUI variant="destructive" className="px-1.5 py-0 text-[10px] h-4" data-testid="badge-unread-count">
            {unreadCount}
          </BadgeUI>
        )}
      </div>
      <div className="text-[11px] text-muted-foreground">
        {showUnreadOnly ? 'Sadece okunmamış' : 'Tümü'}
      </div>
    </div>
    )}
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
                        <BadgeUI variant="outline" className="text-xs">
                          {msg.from_department}
                        </BadgeUI>
                      )}
                      {msg.priority === 'urgent' && (
                        <BadgeUI variant="destructive" className="text-xs">
                          <AlertCircle className="h-3 w-3 mr-0.5" /> Acil
                        </BadgeUI>
                      )}
                      {!msg.read && (
                        <BadgeUI variant="default" className="text-xs">Yeni</BadgeUI>
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

export default InboxList;
