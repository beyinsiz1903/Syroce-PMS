import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import axios from 'axios';
import { describe, expect, it, vi } from 'vitest';

import { loadChannelAttention } from '../channelAttention';

describe('calendar channel attention API requests', () => {
  it.each(['/api', 'https://pms.example.com/api'])(
    'uses the configured API root exactly once (%s)',
    async (baseURL) => {
      const pending = { items: [{ id: 'roomless-1' }], total: 1 };
      const mapping = { items: [{ id: 'mapping-1', queue_kind: 'mapping_required' }], total: 1 };
      const requested = [];
      const http = axios.create({
        baseURL,
        adapter: async (config) => {
          const uri = axios.getUri(config);
          requested.push(uri);
          const payloads = new Map([
            [`${baseURL}/channel-manager/conflict-queue?limit=200`, pending],
            [`${baseURL}/channel-manager/conflict-queue/mapping-issues`, mapping],
          ]);
          if (!payloads.has(uri)) {
            throw new axios.AxiosError('Not Found', 'ERR_BAD_REQUEST', config, null, { status: 404 });
          }
          return { data: payloads.get(uri), status: 200, statusText: 'OK', headers: {}, config };
        },
      });

      const [queueResponse, mappingResponse] = await loadChannelAttention(http);

      expect(requested).toEqual([
        `${baseURL}/channel-manager/conflict-queue?limit=200`,
        `${baseURL}/channel-manager/conflict-queue/mapping-issues`,
      ]);
      expect(requested.every((url) => !url.includes('/api/api/'))).toBe(true);
      expect(queueResponse.data).toEqual(pending);
      expect(mappingResponse.data).toEqual(mapping);
    },
  );

  it('treats two verified empty lists as a successful empty queue', async () => {
    const http = { get: vi.fn().mockResolvedValue({ data: { items: [], total: 0 } }) };
    const responses = await loadChannelAttention(http);

    expect(responses).toHaveLength(2);
    expect(responses.every((response) => response.data.total === 0)).toBe(true);
  });

  it.each([
    ['/channel-manager/conflict-queue', 403],
    ['/channel-manager/conflict-queue', 500],
    ['/channel-manager/conflict-queue/mapping-issues', 404],
    ['/channel-manager/conflict-queue/mapping-issues', 503],
  ])('does not mark a partial list verified when %s fails (%s)', async (path, status) => {
    const failure = Object.assign(new Error('attention API failed'), { response: { status } });
    const http = {
      get: vi.fn((url) => url === path
        ? Promise.reject(failure)
        : Promise.resolve({ data: { items: [{ id: 'available-source' }], total: 1 } })),
    };

    await expect(loadChannelAttention(http)).rejects.toBe(failure);
  });

  it('preserves network failures for the existing incomplete-list warning', async () => {
    const failure = new Error('Network Error');
    await expect(loadChannelAttention({ get: vi.fn().mockRejectedValue(failure) })).rejects.toBe(failure);
  });

  it('wires the calendar to the tested loader and retains its failure warning', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/pages/ReservationCalendar.jsx'), 'utf8');

    expect(source).toContain('loadChannelAttention(axios)');
    expect(source).not.toContain("axios.get('/api/channel-manager/conflict-queue");
    expect(source).toContain('setAllUnassignedError(true)');
    expect(source).toContain('Kanal istisnaları tam doğrulanamadı. Liste yalnız yüklenen takvim kayıtlarını gösteriyor.');
  });
});
