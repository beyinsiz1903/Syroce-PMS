import { useState } from 'react';
import { Checkbox } from '@/components/ui/checkbox';
import { CHANNELS } from './constants';

export const ChannelList = () => {
  const [allChannels, setAllChannels] = useState(true);
  const [selected, setSelected] = useState(new Set(CHANNELS.map(c => c.key)));

  const toggleAll = () => {
    if (allChannels) {
      setAllChannels(false);
      setSelected(new Set());
    } else {
      setAllChannels(true);
      setSelected(new Set(CHANNELS.map(c => c.key)));
    }
  };

  const toggleChannel = (key) => {
    setAllChannels(false);
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  return (
    <div className="space-y-1.5">
      <label className="flex items-center gap-2 cursor-pointer text-sm font-medium" data-testid="channel-all">
        <Checkbox checked={allChannels} onCheckedChange={toggleAll} />
        <span>Hepsi</span>
      </label>
      <div className="border-t pt-1.5 space-y-1">
        {CHANNELS.map(ch => (
          <label key={ch.key} className="flex items-center gap-2 cursor-pointer text-xs" data-testid={`channel-${ch.key}`}>
            <Checkbox
              checked={selected.has(ch.key)}
              onCheckedChange={() => toggleChannel(ch.key)}
              className="h-3.5 w-3.5"
            />
            <span className={selected.has(ch.key) ? 'text-gray-800' : 'text-gray-400'}>
              {ch.label}
            </span>
          </label>
        ))}
      </div>
    </div>
  );
};
