import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { axiosDelete, axiosGet } = vi.hoisted(() => ({
  axiosDelete: vi.fn(),
  axiosGet: vi.fn(),
}));

vi.mock('axios', () => ({
  default: {
    delete: axiosDelete,
    get: axiosGet,
    post: vi.fn(),
    put: vi.fn(),
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
});
