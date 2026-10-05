const fs = require('fs');
const file = 'frontend/src/components/pms/InternalChatTab.jsx';
let content = fs.readFileSync(file, 'utf8');

const oldTabs = `            <div className="flex items-center rounded-lg bg-muted p-0.5">
              <button
                type="button"
                onClick={() => setView('conversations')}
                data-testid="button-view-conversations"
                className={\`relative flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-colors \${view === 'conversations' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}\`}
              >
                Konuşmalar
                {totalConversationUnread > 0 && (
                  <span className="ml-0.5 inline-flex items-center justify-center rounded-full bg-red-500 px-1 py-0.5 text-[10px] font-semibold leading-none text-white min-w-[16px]">
                    {totalConversationUnread > 99 ? '99+' : totalConversationUnread}
                  </span>
                )}
              </button>
              <button
                type="button"
                onClick={() => setView('inbox')}
                data-testid="button-view-inbox"
                className={\`relative flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-colors \${view === 'inbox' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}\`}
              >
                Gelen Kutusu
                {unreadCount > 0 && (
                  <span className="ml-0.5 inline-flex items-center justify-center rounded-full bg-red-500 px-1 py-0.5 text-[10px] font-semibold leading-none text-white min-w-[16px]">
                    {unreadCount > 99 ? '99+' : unreadCount}
                  </span>
                )}
              </button>
              {canViewGuestRequests && (
                <button
                  type="button"
                  onClick={() => setView('guest_requests')}
                  data-testid="button-view-guest-requests"
                  className={\`relative flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-colors \${view === 'guest_requests' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}\`}
                >
                  Misafir Talepleri
                  {guestRequestsUnread > 0 && (
                    <span className="ml-0.5 inline-flex items-center justify-center rounded-full bg-red-500 px-1 py-0.5 text-[10px] font-semibold leading-none text-white min-w-[16px]">
                      {guestRequestsUnread > 99 ? '99+' : guestRequestsUnread}
                    </span>
                  )}
                </button>
              )}
            </div>`;

const newTabs = `            <div className="flex items-center rounded-lg bg-muted p-0.5">
              {initialView !== 'guest_requests' && (
                <>
                  <button
                    type="button"
                    onClick={() => setView('conversations')}
                    data-testid="button-view-conversations"
                    className={\`relative flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-colors \${view === 'conversations' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}\`}
                  >
                    Konuşmalar
                    {totalConversationUnread > 0 && (
                      <span className="ml-0.5 inline-flex items-center justify-center rounded-full bg-red-500 px-1 py-0.5 text-[10px] font-semibold leading-none text-white min-w-[16px]">
                        {totalConversationUnread > 99 ? '99+' : totalConversationUnread}
                      </span>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => setView('inbox')}
                    data-testid="button-view-inbox"
                    className={\`relative flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-colors \${view === 'inbox' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}\`}
                  >
                    Gelen Kutusu
                    {unreadCount > 0 && (
                      <span className="ml-0.5 inline-flex items-center justify-center rounded-full bg-red-500 px-1 py-0.5 text-[10px] font-semibold leading-none text-white min-w-[16px]">
                        {unreadCount > 99 ? '99+' : unreadCount}
                      </span>
                    )}
                  </button>
                </>
              )}
              {initialView === 'guest_requests' && canViewGuestRequests && (
                <button
                  type="button"
                  onClick={() => setView('guest_requests')}
                  data-testid="button-view-guest-requests"
                  className={\`relative flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-colors \${view === 'guest_requests' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}\`}
                >
                  Misafir Talepleri
                  {guestRequestsUnread > 0 && (
                    <span className="ml-0.5 inline-flex items-center justify-center rounded-full bg-red-500 px-1 py-0.5 text-[10px] font-semibold leading-none text-white min-w-[16px]">
                      {guestRequestsUnread > 99 ? '99+' : guestRequestsUnread}
                    </span>
                  )}
                </button>
              )}
            </div>`;

if (content.includes(oldTabs)) {
    content = content.replace(oldTabs, newTabs);
    fs.writeFileSync(file, content);
    console.log("Patched InternalChatTab.jsx successfully.");
} else {
    console.log("Could not find the target code in InternalChatTab.jsx.");
}
