import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectTrigger, SelectValue } from '@/components/ui/select';
import * as SelectPrimitive from '@radix-ui/react-select';
import { Check } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Switch } from '@/components/ui/switch';
import { MessagesSquare, RefreshCw, Search } from 'lucide-react';
import { CONVERSATION_DEPARTMENT_FILTERS, ROLE_LABELS } from './constants';

const ConversationsList = ({
  conversations,
  filteredConversations,
  loadingConversations,
  loadConversations,
  selectedConvUserId,
  handleSelectConversation,
  totalConversationUnread,
  conversationSearch, setConversationSearch,
  conversationDeptFilter, setConversationDeptFilter,
  conversationDeptOpen, setConversationDeptOpen,
  conversationOnlyUnread, setConversationOnlyUnread,
  conversationUnreadByDept,
  conversationFiltersActive,
  jumpToFirstUnreadInDepartment,
  embedded = false,
}) => (
  <div className={`flex flex-col h-full bg-background ${embedded ? '' : 'border rounded-md'}`}>
    <div className="p-3 border-b space-y-2">
      {!embedded && (
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
      )}
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

export default ConversationsList;
