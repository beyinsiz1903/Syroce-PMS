import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { axiosDelete, axiosGet, axiosPut } = vi.hoisted(() => ({
  axiosDelete: vi.fn(),
  axiosGet: vi.fn(),
  axiosPut: vi.fn(),
}));

vi.mock('axios', () => ({
  default: {
    delete: axiosDelete,
    get: axiosGet,
    post: vi.fn(),
    put: axiosPut,
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import StaffTaskManager from '@/components/StaffTaskManager';

describe('StaffTaskManager destructive actions', () => {
  beforeEach(() => {
    axiosDelete.mockReset();
    axiosGet.mockReset();
    axiosPut.mockReset();
    axiosGet.mockResolvedValue({
      data: {
        tasks: [{
          id: 'task-a',
          title: 'Audit task',
          task_type: 'maintenance',
          department: 'engineering',
          priority: 'normal',
          room_id: '101',
          status: 'pending',
        }],
      },
    });
    axiosDelete.mockResolvedValue({ data: { success: true } });
    axiosPut.mockResolvedValue({ data: { success: true } });
  });

  afterEach(() => cleanup());

  it('requires explicit confirmation before permanently deleting a task', async () => {
    render(<StaffTaskManager />);

    await screen.findByText('Audit task');
    fireEvent.click(screen.getByRole('button', { name: 'pmsComponents.staff.deleteTaskAria' }));

    expect(axiosDelete).not.toHaveBeenCalled();
    expect(screen.getByText('pmsComponents.staff.deleteConfirmTitle')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'pmsComponents.staff.deleteConfirmAction' }));

    await waitFor(() => expect(axiosDelete).toHaveBeenCalledWith('/pms/staff-tasks/task-a'));
  });

  it('requires explicit confirmation before bulk-deleting empty tasks', async () => {
    render(<StaffTaskManager />);

    await screen.findByText('Audit task');
    fireEvent.click(screen.getByRole('button', { name: 'pmsComponents.staff.cleanupEmpty' }));

    expect(axiosDelete).not.toHaveBeenCalled();
    expect(screen.getByText('pmsComponents.staff.cleanupConfirmTitle')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'pmsComponents.staff.cleanupConfirmAction' }));

    await waitFor(() => expect(axiosDelete).toHaveBeenCalledWith('/pms/staff-tasks/cleanup-empty'));
  });

  it('keeps guest QR tasks immutable and requires a result when completing', async () => {
    axiosGet.mockResolvedValue({
      data: {
        tasks: [{
          id: 'guest-qr:req-1',
          title: 'Ek havlu',
          task_type: 'guest_request',
          department: 'housekeeping',
          priority: 'normal',
          room_id: '208',
          room_number: '208',
          status: 'in_progress',
          source: 'guest_qr',
        }],
      },
    });

    render(<StaffTaskManager currentUser={{ name: 'Ayşe' }} />);

    await screen.findByText('Ek havlu');
    expect(screen.queryByRole('button', { name: 'pmsComponents.staff.deleteTaskAria' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'pmsComponents.staff.complete' }));
    fireEvent.change(screen.getByPlaceholderText('Örn. Talep edilen havlular odaya teslim edildi.'), {
      target: { value: 'Havlular teslim edildi.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Tamamla ve misafire bildir' }));

    await waitFor(() => expect(axiosPut).toHaveBeenCalledWith('/pms/staff-tasks/guest-qr:req-1', {
      status: 'completed',
      resolution_note: 'Havlular teslim edildi.',
      assigned_to: 'Ayşe',
    }));
  });
});
