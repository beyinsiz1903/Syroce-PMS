import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  render, screen, cleanup, waitFor,
} from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import CertificateVerifyPage from '@/pages/CertificateVerifyPage';

// The page builds its client via axios.create(); capture the returned instance's
// get() so each test can drive the public /academy/verify response.
const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));
vi.mock('axios', () => ({
  default: { create: () => ({ get: mockGet }) },
}));

// Render the page at a deep-link route so the verification code auto-runs on
// mount via useParams — mirrors a third party opening a printed cert link.
function renderAtCode(code) {
  return render(
    <MemoryRouter initialEntries={[`/sertifika-dogrula/${code}`]}>
      <Routes>
        <Route path="/sertifika-dogrula/:code" element={<CertificateVerifyPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockGet.mockReset();
});

afterEach(() => {
  cleanup();
});

describe('CertificateVerifyPage', () => {
  it('shows a clear "not found" message for an invalid/unknown code', async () => {
    mockGet.mockResolvedValueOnce({ data: { valid: false } });

    renderAtCode('SYR-ACAD-0000000000');

    expect(await screen.findByText('Sertifika bulunamadı')).toBeInTheDocument();
    expect(
      screen.getByText(/geçerli bir sertifika bulunamadı/i),
    ).toBeInTheDocument();
    // The negative branch must not render the valid-certificate panel.
    expect(screen.queryByText('Geçerli sertifika')).not.toBeInTheDocument();
  });

  it('shows a rate-limit message on HTTP 429', async () => {
    mockGet.mockRejectedValueOnce({ response: { status: 429 } });

    renderAtCode('SYR-ACAD-1111111111');

    expect(
      await screen.findByText(/çok fazla deneme/i),
    ).toBeInTheDocument();
    expect(screen.queryByText('Sertifika bulunamadı')).not.toBeInTheDocument();
    expect(screen.queryByText('Geçerli sertifika')).not.toBeInTheDocument();
  });

  it('renders masked recipient + course/department/date for a valid code', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        valid: true,
        verification_code: 'SYR-ACAD-ABCDEF1234',
        course_title: 'Misafir İlişkileri',
        department_label: 'Ön Büro',
        issued_at: '2026-06-01',
        recipient_name: 'A*** Y***',
      },
    });

    renderAtCode('SYR-ACAD-ABCDEF1234');

    expect(await screen.findByText('Geçerli sertifika')).toBeInTheDocument();
    expect(screen.getByText('A*** Y***')).toBeInTheDocument();
    expect(screen.getByText('Misafir İlişkileri')).toBeInTheDocument();
    expect(screen.getByText('Ön Büro')).toBeInTheDocument();
    expect(screen.getByText('2026-06-01')).toBeInTheDocument();
    expect(screen.getByText('SYR-ACAD-ABCDEF1234')).toBeInTheDocument();
    // Failure panels must stay hidden on success.
    expect(screen.queryByText('Sertifika bulunamadı')).not.toBeInTheDocument();
  });

  it('shows a generic error message for non-429 failures', async () => {
    mockGet.mockRejectedValueOnce({ response: { status: 500 } });

    renderAtCode('SYR-ACAD-2222222222');

    expect(
      await screen.findByText(/doğrulama sırasında bir hata oluştu/i),
    ).toBeInTheDocument();
  });
});
