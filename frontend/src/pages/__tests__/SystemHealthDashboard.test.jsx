import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act, cleanup, waitFor } from '@testing-library/react';
import axios from 'axios';
import { io } from 'socket.io-client';
import SystemHealthDashboard from '@/pages/SystemHealthDashboard';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => {
      if (opts && typeof opts === 'object') {
        if ('count' in opts) return `${key}:${opts.count}`;
        if ('tenants' in opts) return `${key}:${opts.tenants}`;
      }
      return key;
    },
  }),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

vi.mock('axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

const socketHandlers = {};
const fakeSocket = {
  on: vi.fn((evt, cb) => {
    socketHandlers[evt] = cb;
  }),
  emit: vi.fn(),
  disconnect: vi.fn(),
};

vi.mock('socket.io-client', () => ({
  io: vi.fn(() => fakeSocket),
}));

const RNL_URL = '/admin/db/room-night-lock-duplicates/summary';

function mockInitialFetch() {
  axios.get.mockImplementation((url) => {
    if (url === RNL_URL) {
      return Promise.resolve({
        data: { manual_required_count: 0, top_tenants: [] },
      });
    }
    return Promise.resolve({ data: {} });
  });
}

beforeEach(() => {
  axios.get.mockReset();
  axios.post.mockReset();
  fakeSocket.on.mockClear();
  fakeSocket.emit.mockClear();
  fakeSocket.disconnect.mockClear();
  io.mockClear();
  for (const k of Object.keys(socketHandlers)) delete socketHandlers[k];
});

afterEach(() => cleanup());

describe('SystemHealthDashboard — RNL duplicate live socket refresh', () => {
  it('refetches summary on rnl_duplicate_alert_state_changed and renders/hides the widget', async () => {
    mockInitialFetch();

    await act(async () => {
      render(<SystemHealthDashboard user={{ role: 'superadmin' }} />);
    });

    // Initial fetch ran, widget is hidden because count == 0.
    await waitFor(() =>
      expect(screen.getByTestId('system-health-dashboard')).toBeInTheDocument()
    );
    expect(screen.queryByTestId('rnl-duplicates-widget')).toBeNull();

    // The dashboard must have registered a handler for the live event.
    expect(socketHandlers.system_health_event).toBeTypeOf('function');

    // Emit "first_detection": the socket handler will re-fetch the summary.
    axios.get.mockImplementation((url) => {
      if (url === RNL_URL) {
        return Promise.resolve({
          data: {
            manual_required_count: 4,
            active_since: new Date().toISOString(),
            top_tenants: [{ tenant_id: 't1', manual_required_count: 4 }],
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    await act(async () => {
      await socketHandlers.system_health_event({
        event_type: 'rnl_duplicate_alert_state_changed',
        severity: 'critical',
        transition: 'first_detection',
      });
      // Flush the .then() that calls setRnlSummary after axios resolves.
      await new Promise((r) => setTimeout(r, 0));
    });

    await waitFor(() =>
      expect(screen.getByTestId('rnl-duplicates-widget')).toBeInTheDocument()
    );
    expect(screen.getByTestId('rnl-duplicates-widget').textContent).toContain(
      'rnlDuplicates.widgetTitle:4'
    );

    // Emit "cleared": re-fetch returns 0 and the widget disappears.
    axios.get.mockImplementationOnce((url) => {
      expect(url).toBe(RNL_URL);
      return Promise.resolve({
        data: { manual_required_count: 0, top_tenants: [] },
      });
    });

    await act(async () => {
      socketHandlers.system_health_event({
        event_type: 'rnl_duplicate_alert_state_changed',
        severity: 'info',
        transition: 'cleared',
      });
    });

    await waitFor(() =>
      expect(screen.queryByTestId('rnl-duplicates-widget')).toBeNull()
    );
  });
});
