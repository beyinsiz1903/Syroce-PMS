import { AlertTriangle, CheckCircle2 } from 'lucide-react';

export const ChannelList = ({ channels = [], stale = false, provider }) => {
  const normalized = channels.map((channel, index) => ({
    key: channel?.code || channel?.name || `channel-${index}`,
    label: channel?.name || channel?.code || String(channel),
  }));

  return (
    <div className="space-y-1.5">
      <div className="text-xs font-medium text-gray-700" data-testid="active-channel-summary">
        {provider === 'hotelrunner' ? `HotelRunner'da etkin (${normalized.length})` : 'Bağlı tüm kanallar'}
      </div>
      {stale && <div className="flex items-start gap-1.5 rounded bg-amber-50 p-2 text-[11px] text-amber-800" data-testid="rate-manager-channels-stale">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          Aktif kanal listesi yenilenemedi.
        </div>}
      {!stale && normalized.length === 0 ? <p className="text-xs text-gray-400" data-testid="rate-manager-no-active-channels">
          Aktif kanal bulunamadı.
        </p> : <div className="border-t pt-1.5 space-y-1">
          {normalized.map(channel => <div key={channel.key} className="flex items-center gap-2 text-xs" data-testid={`channel-${channel.key}`}>
              <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-600" />
              <span className="text-gray-800">{channel.label}</span>
            </div>)}
        </div>}
      <p className="pt-1 text-[10px] leading-snug text-gray-400">
        Güncelleme, kanal yöneticisindeki etkin kanallara uygulanır.
      </p>
    </div>
  );
};
