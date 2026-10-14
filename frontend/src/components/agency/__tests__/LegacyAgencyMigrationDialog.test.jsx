import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }));
vi.mock('axios', () => ({ default: { get: (...a) => apiGet(...a), post: (...a) => apiPost(...a) } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import LegacyAgencyMigrationDialog from '@/components/agency/LegacyAgencyMigrationDialog';

describe('LegacyAgencyMigrationDialog', () => {
  beforeEach(() => {
    localStorage.setItem('user', JSON.stringify({ tenant_id: 't1' }));
    apiGet.mockResolvedValue({ data: { notes: [], agencies: [{
      legacy_agency: { id: 'L1', name: 'Atlas Turizm' }, contract: null, user_count: 2, future_bookings: 1,
      suggested_target: { id: 'M1', name: 'Atlas' }, warnings: [],
    }] } });
    apiPost.mockImplementation((_url, body) => Promise.resolve({ data: { dry_run: body.dry_run, results: [{ legacy_agency_id: 'L1', legacy_agency_name: 'Atlas Turizm', actions: ['Mevcut marketplace acentesine bağlanır: Atlas'], skipped: [] }] } }));
  });
  afterEach(() => { cleanup(); vi.clearAllMocks(); localStorage.clear(); });

  it('requires a dry run before migrating with the suggested target', async () => {
    const onDone = vi.fn();
    render(<LegacyAgencyMigrationDialog marketplaceAgencies={[{ id: 'M1', name: 'Atlas' }]} onDone={onDone} />);
    await userEvent.click(screen.getByTestId('legacy-migration-open'));
    expect(await screen.findByText('Atlas Turizm')).toBeTruthy();
    expect(screen.getByTestId('legacy-migration-execute').disabled).toBe(true);

    await userEvent.click(screen.getByText('Önizle (kuru çalıştırma)'));
    await screen.findByTestId('legacy-migration-plan');
    await userEvent.click(screen.getByTestId('legacy-migration-execute'));

    await waitFor(() => expect(apiPost).toHaveBeenLastCalledWith('/marketplace/v1/admin/legacy-migration/execute', {
      tenant_id: 't1', items: [{ legacy_agency_id: 'L1', marketplace_agency_id: 'M1' }], dry_run: false,
    }));
    expect(onDone).toHaveBeenCalled();
  });
});
