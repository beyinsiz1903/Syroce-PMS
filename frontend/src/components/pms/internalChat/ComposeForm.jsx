import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Switch } from '@/components/ui/switch';
import {
  Building2, Users, MessageSquare, Search, Send,
} from 'lucide-react';
import { DEPARTMENTS, ROLE_LABELS, CONVERSATION_DEPARTMENT_FILTERS } from './constants';

const ComposeForm = ({
  recipientType, setRecipientType,
  toDepartment, setToDepartment,
  usersAccessDenied,
  userSearch, setUserSearch,
  toUserId, setToUserId,
  userDeptFilter, setUserDeptFilter,
  onlineOnly, setOnlineOnly,
  onlineUsers,
  loadOnlinePresence,
  usersLoaded,
  users,
  filteredUsers,
  messageText, setMessageText,
  priority, setPriority,
  canSendUrgent,
  resetForm,
  handleSend,
  sending,
}) => (
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

export default ComposeForm;
