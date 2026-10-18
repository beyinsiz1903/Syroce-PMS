import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import ModuleStorePage from '../ModuleStorePage';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ i18n: { language: 'tr' } }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const product = { key: 'hr', name: 'İnsan Kaynakları', included_units: 25, pricing_model: 'employee', category: 'module', features: [], price_try: 1490 };

describe('Quote request receipt and quantity', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    axios.get.mockImplementation(async url => url.includes('/products') ? { data: { products: [product], payment_ready: false } } : { data: { subscriptions: [] } });
    axios.post.mockResolvedValue({ data: { ok: true, request_id: '883f5403-full-id', delivery: { admin_queue: true, email: 'failed' } } });
  });

  it('sends the selected quantity and clearly states where the request is delivered', async () => {
    render(<MemoryRouter><ModuleStorePage /></MemoryRouter>);
    await screen.findByRole('button', { name: 'Teklif iste' });
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '26' } });
    fireEvent.click(screen.getByRole('button', { name: 'Teklif iste' }));
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/module-store/request-quote', { product_key: 'hr', quantity: 26 }));
    expect(await screen.findByRole('status')).toHaveTextContent('883f5403-full-id');
    expect(screen.getByRole('status')).toHaveTextContent('Süperadmin → Satış ve modül talepleri');
    expect(screen.getByRole('status')).toHaveTextContent('e-posta bildirimi gönderilemedi; talebiniz kuyrukta kayıtlıdır');
    expect(screen.getByRole('status')).toHaveTextContent('satın alma veya modül aktivasyonu değildir');
  });

  it('prevents duplicate clicks while a quote is being saved and rejects invalid quantities', async () => {
    let finish;
    axios.post.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    render(<MemoryRouter><ModuleStorePage /></MemoryRouter>);
    const button = await screen.findByRole('button', { name: 'Teklif iste' });
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '1.5' } });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '25' } });
    fireEvent.click(button); fireEvent.click(button);
    expect(axios.post).toHaveBeenCalledTimes(1);
    await act(async () => finish({ data: { ok: true, request_id: 'q', delivery: {} } }));
  });
});
