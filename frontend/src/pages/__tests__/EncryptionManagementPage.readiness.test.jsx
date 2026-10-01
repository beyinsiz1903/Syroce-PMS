import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { axiosGet } = vi.hoisted(() => ({ axiosGet: vi.fn() }));

vi.mock('axios', () => ({
  default: {
    get: axiosGet,
    post: vi.fn(),
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: key => key, i18n: { language: 'tr-TR' } }),
}));

import EncryptionManagementPage from '../EncryptionManagementPage';

describe('şifreleme yönetimi hazırlık durumu', () => {
  beforeEach(() => {
    axiosGet.mockReset();
    axiosGet.mockResolvedValue({
      data: {
        keys: { summary: {}, keys: [], overdue_rotations: [], rotation_warnings: [] },
        reencryption_jobs: { summary: {}, recent_jobs: [] },
      },
    });
  });

  it('anahtar yokken durumu açıklar ve geçersiz yeniden şifreleme akışını engeller', async () => {
    render(<EncryptionManagementPage tenant={{ name: 'Test Otel' }} />);

    await waitFor(() => expect(screen.getByTestId('encryption-readiness-warning')).toBeInTheDocument());
    expect(screen.getByText(/0 aktif anahtar.*verilerin şifrelenmediği anlamına/i)).toBeInTheDocument();
    expect(screen.getByTestId('create-job-btn')).toBeDisabled();
    expect(screen.getByTestId('create-job-btn')).toHaveAttribute(
      'title',
      'Önce bir şifreleme anahtarı kaydedin',
    );
  });
});
