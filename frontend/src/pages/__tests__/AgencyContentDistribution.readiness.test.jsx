import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import axios from 'axios';
import AgencyContentDistribution from '../AgencyContentDistribution';

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key, i18n: { language: 'tr' } }) }));
afterEach(cleanup);
const saved = { hotel_name: 'Hotel', room_types: [], services: [], images: [], content_version: 3 };
let checks;
beforeEach(() => {
  vi.clearAllMocks();
  checks = { ready: false, can_publish: true, errors: [], warnings: ['Tesis / kapak fotoğrafı eksik.'],
    tenant_name: 'PMS Hotel', content_name: 'Hotel', content_version: 3,
    access: { hotel_portal_published_count: 1, marketplace_listed: true, marketplace_active_contract_count: 2 } };
  axios.get.mockImplementation(async url => ({ data: url === '/hotel-content' ? saved : url === '/hotel-content/readiness' ? checks : url === '/agencies' ? [{ id: 'a', name: 'Agency', status: 'active', published_content: true }] : { currently_published: 1, selected: 1, to_add: 0, to_remove: 0 } }));
  axios.post.mockResolvedValue({ data: { message: 'Tamam' } });
});
const page = () => render(<AgencyContentDistribution user={{ role: 'admin' }} />);

it('separates access paths and blocks publishing unsaved edits', async () => {
  page();
  await screen.findByText(/PMS adı: PMS Hotel/);
  expect(screen.getByText(/marketplace erişimini veya sözleşmesini kapatmaz/)).toBeInTheDocument();
  expect(screen.getByText(/Geçerli sözleşme: 2/)).toBeInTheDocument();
  fireEvent.change(screen.getAllByRole('textbox')[0], { target: { value: 'Changed' } });
  expect(screen.getByTestId('distribute-btn')).toBeDisabled();
  expect(screen.getByText(/Kaydedilmemiş değişiklikler/)).toBeInTheDocument();
});

it('requires explicit review of warnings and submits the checked version', async () => {
  page();
  await screen.findByText(/PMS adı: PMS Hotel/);
  fireEvent.click(screen.getByTestId('distribute-btn'));
  const consent = await screen.findByLabelText(/İçerik uyarılarını inceledim/);
  expect(screen.getByTestId('confirm-distribute')).toBeDisabled();
  fireEvent.click(consent);
  fireEvent.click(screen.getByTestId('confirm-distribute'));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/hotel-content/distribute', {
    agency_ids: ['a'], unpublish_omitted: false, expected_content_version: 3,
  }));
});

it('fails closed when readiness cannot be read', async () => {
  const previous = axios.get.getMockImplementation();
  axios.get.mockImplementation(url => url === '/hotel-content/readiness' ? Promise.reject(new Error('offline')) : previous(url));
  page();
  await screen.findByText(/Hazırlık durumu doğrulanamadı/);
  expect(screen.getByTestId('distribute-btn')).toBeDisabled();
});
