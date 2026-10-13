import React from 'react';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { afterEach, it, expect, vi } from 'vitest';
import axios from 'axios';
import PreCheckinPage from '../PreCheckinPage';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('react-router-dom', () => ({ useParams: () => ({ token: 'token-123456789012' }) }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it('keeps optional WhatsApp consent separate from mandatory KVKK', async () => {
  axios.get.mockResolvedValue({ data: { property_name: 'Hotel', whatsapp_consent_available: true } });
  render(<PreCheckinPage />);
  const boxes = await screen.findAllByRole('checkbox');
  expect(boxes).toHaveLength(2);
  expect(boxes.every(box => !box.checked)).toBe(true);
  fireEvent.click(boxes[0]);
  expect(boxes[1].checked).toBe(false);
  fireEvent.change(screen.getByPlaceholderText('+905xxxxxxxxx'), { target: { value: '+905551112233' } });
  fireEvent.click(boxes[1]);
  expect(boxes[1].checked).toBe(true);
  fireEvent.change(screen.getByPlaceholderText('+905xxxxxxxxx'), { target: { value: '+905559999999' } });
  await waitFor(() => expect(boxes[1].checked).toBe(false));
  expect(axios.post).not.toHaveBeenCalled();
});

it('lets legacy QR guests continue without offering an unbound consent', async () => {
  axios.get.mockResolvedValue({ data: { property_name: 'Hotel', whatsapp_consent_available: false } });
  render(<PreCheckinPage />);
  expect(await screen.findByText(/tesisten yeni ön giriş bağlantısı/)).toBeTruthy();
  expect(screen.getAllByRole('checkbox')).toHaveLength(1);
});
