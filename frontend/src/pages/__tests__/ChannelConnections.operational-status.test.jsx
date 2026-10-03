import { describe, expect, it } from 'vitest';

import { getChannelOperationalStatus } from '@/pages/ChannelConnections';

describe('ChannelConnections operational status', () => {
  it('does not present a configured provider as production before setup is complete', () => {
    expect(getChannelOperationalStatus({ connected: false })).toMatchObject({ key: 'setup_pending' });
    expect(getChannelOperationalStatus({ connected: true, room_mappings_count: 0 })).toMatchObject({ key: 'mapping_required' });
    expect(getChannelOperationalStatus({ connected: true, room_mappings_count: 1, auto_sync_reservations: false })).toMatchObject({ key: 'sync_paused' });
    expect(getChannelOperationalStatus({ connected: true, room_mappings_count: 1, auto_sync_reservations: true })).toMatchObject({ key: 'first_sync_pending' });
    expect(getChannelOperationalStatus({ connected: true, room_mappings_count: 1, auto_sync_reservations: true, last_sync_at: '2026-10-03T09:00:00Z' })).toMatchObject({ key: 'production' });
  });
});
