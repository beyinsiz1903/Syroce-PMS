import { AlertTriangle, CheckCircle2 } from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';

export const ChannelList = ({ channels = [], stale = false, selectedChannelCodes = new Set(), onToggle, onToggleAll, provider }) => {
  const normalized = channels.map((channel, index) => ({
    key: channel?.code || channel?.name || `channel-${index}`,
    code: String(channel?.code || '').trim(),
    label: channel?.name || channel?.code || String(channel),
  }));
  const selectableChannels = normalized.filter(channel => channel.code);
  const allSelected = selectableChannels.length > 0 && selectableChannels.every(channel => selectedChannelCodes.has(channel.code));

  return (
    <div className="space-y-1.5">
      <div className="text-xs font-medium text-gray-700" data-testid="active-channel-summary">
        {provider === 'hotelrunner' ? `HotelRunner'da etkin (${normalized.length})` : 'Bağlı tüm kanallar'}
      </div>
      {stale && <div className="flex items-start gap-1.5 rounded bg-amber-50 p-2 text-[11px] text-amber-800" data-testid="rate-manager-channels-stale">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          Kanal bağlantısı doğrulanamadı. Güvenlik için kanal gönderimi kapatıldı.
        </div>}
      {normalized.length === 0 ? <p className="text-xs text-gray-400" data-testid="rate-manager-no-active-channels">
          Aktif kanal bulunamadı.
        </p> : <div className="border-t pt-1.5 space-y-1">
          {provider === 'hotelrunner' && !stale && selectableChannels.length > 0 && <label className="flex cursor-pointer items-center gap-2 border-b border-slate-100 pb-1.5 text-xs font-medium text-slate-700">
              <Checkbox checked={allSelected} onCheckedChange={onToggleAll} data-testid="channel-select-all" />
              Tümünü seç
            </label>}
          {normalized.map(channel => <label key={channel.key} className="flex cursor-pointer items-center gap-2 text-xs" data-testid={`channel-${channel.key}`}>
              {provider === 'hotelrunner' ? <Checkbox disabled={!channel.code} checked={selectedChannelCodes.has(channel.code)} onCheckedChange={() => onToggle?.(channel.code)} data-testid={`channel-checkbox-${channel.key}`} /> : <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-600" />}
              <span className="text-gray-800">{channel.label}</span>
            </label>)}
        </div>}
      <p className="pt-1 text-[10px] leading-snug text-gray-400">
        {provider === 'hotelrunner' ? 'Yalnızca seçtiğiniz ve kanal yöneticisinde doğrulanmış OTA’lara gönderilir. Seçim yoksa değişiklik PMS içinde kalır.' : 'Seçili kanal yöneticisinin OTA bazlı hedefleme desteği yoktur.'}
      </p>
    </div>
  );
};
