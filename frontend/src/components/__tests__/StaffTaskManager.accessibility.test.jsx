import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { axiosGet } = vi.hoisted(() => ({ axiosGet: vi.fn() }));

vi.mock('axios', () => ({ default: { get: axiosGet } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }));

import StaffTaskManager from '@/components/StaffTaskManager';

describe('StaffTaskManager accessibility', () => {
  beforeEach(() => {
    axiosGet.mockResolvedValue({ data: { tasks: [] } });
  });

  it('exposes task summary filters as pressed-state buttons', async () => {
    render(<StaffTaskManager />);

    const pending = await screen.findByRole('button', { name: 'pmsComponents.staff.pending görevleri filtrele' });
    expect(pending).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(pending);
    expect(pending).toHaveAttribute('aria-pressed', 'true');
  });
});
