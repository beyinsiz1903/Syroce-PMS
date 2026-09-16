const fs = require('fs');
const file = 'frontend/src/components/InternalChatWidget.jsx';
let content = fs.readFileSync(file, 'utf8');

content = content.replace(
  'import { MessageSquare, MessagesSquare, X } from \'lucide-react\';',
  'import { MessageCircleMore, MessagesSquare, X } from \'lucide-react\';'
);
if (!content.includes('MessageCircleMore')) {
  content = content.replace(
    'import { MessagesSquare, X } from \'lucide-react\';',
    'import { MessageCircleMore, MessagesSquare, X } from \'lucide-react\';'
  );
}

const oldTitle = `            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground shrink-0">
              <MessagesSquare className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold leading-tight truncate">Personel Mesajlaşması</div>
              <div className="text-[11px] text-muted-foreground leading-tight">Canlı bildirim açık</div>
            </div>`;

const newTitle = `            <div className={\`flex h-8 w-8 items-center justify-center rounded-lg \${initialView === 'guest_requests' ? 'bg-amber-600' : 'bg-primary'} text-white shrink-0\`}>
              {initialView === 'guest_requests' ? <MessageCircleMore className="h-4 w-4" /> : <MessagesSquare className="h-4 w-4" />}
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold leading-tight truncate">
                {initialView === 'guest_requests' ? 'Misafir Talepleri' : 'Personel Mesajlaşması'}
              </div>
              <div className="text-[11px] text-muted-foreground leading-tight">Canlı bildirim açık</div>
            </div>`;

if (content.includes(oldTitle)) {
    content = content.replace(oldTitle, newTitle);
    fs.writeFileSync(file, content);
    console.log("Patched InternalChatWidget.jsx successfully.");
} else {
    console.log("Could not find the target code in InternalChatWidget.jsx.");
}
