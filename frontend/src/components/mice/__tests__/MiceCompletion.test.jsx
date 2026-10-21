import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import { confirmDialog, promptDialog } from '@/lib/dialogs';
import EventSettlements from '../EventSettlements';
import EventConsumption from '../EventConsumption';
import SeatingPlan from '../SeatingPlan';
import OperationTasks from '../OperationTasks';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/dialogs', () => ({ confirmDialog: vi.fn(), promptDialog: vi.fn() }));
beforeEach(() => { vi.resetAllMocks(); confirmDialog.mockResolvedValue(true); });
const settlements = extra => ({ currency: 'TRY', payments: [], bank_accounts: [], totals: { net_collected: 90, outstanding: 78, customer_credit: 0 }, ...extra });

describe('MICE financial and operations completion', () => {
  it('keeps the same financial request after an uncertain HTTP response', async () => {
    axios.get.mockResolvedValue({ data: settlements() });
    axios.post.mockRejectedValueOnce(new Error('Response lost')).mockResolvedValueOnce({ data: { replayed: true } });
    render(<EventSettlements eventId="event" />);
    expect(await screen.findByText(/Net tahsilat:/)).toHaveTextContent('78,00');
    fireEvent.change(screen.getByLabelText('Tutar (TRY)'), { target: { value: '40' } });
    fireEvent.change(screen.getByLabelText('Makbuz / banka referansı'), { target: { value: 'TEST-123' } });
    fireEvent.change(screen.getByLabelText('Açıklama / iade gerekçesi'), { target: { value: 'Synthetic receipt only' } });
    const button = screen.getByRole('button', { name: 'Gerçek hareketi kaydet' });
    fireEvent.click(button);
    await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));
    expect(axios.post.mock.calls[1]).toEqual(axios.post.mock.calls[0]);
    expect(axios.post.mock.calls[0][1]).toMatchObject({ amount: 40, method: 'cash', exchange_rate: null });
  });

  it('recovers the persisted pending request without allowing its payload to change', async () => {
    const request = { request_id: 'persisted-key', kind: 'collection', amount: 40, method: 'cash', bank_account_id: null, original_payment_id: null, exchange_rate: null, reference: 'TEST-123', reason: 'Synthetic receipt only' };
    axios.get.mockResolvedValue({ data: settlements({ pending: { request } }) });
    axios.post.mockResolvedValue({ data: {} });
    render(<EventSettlements eventId="event" />);
    const restore = await screen.findByRole('button', { name: 'Bekleyen isteği forma al' });
    const retry = screen.getByRole('button', { name: 'Aynı bekleyen işlemi tamamla' });
    expect(retry).toBeDisabled();
    fireEvent.click(restore);
    expect(screen.getByLabelText('Tutar (TRY)')).toBeDisabled();
    fireEvent.click(retry);
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/mice/events/event/settlements', request));
  });

  it('retains a rejected seating plan for correction and saves with its server revision', async () => {
    axios.get.mockResolvedValue({ data: { expected_revision: 'revision-1', plans: [], bookings: [{ space_id: 'hall', space_name: 'Synthetic hall', starts_at: '2026-10-21T10:00' }] } });
    axios.put.mockRejectedValueOnce({ response: { data: { detail: 'Masa kapasitesi yetersiz' } } }).mockResolvedValueOnce({ data: {} });
    const changed = vi.fn();
    render(<SeatingPlan eventId="event" canManage onChanged={changed} />);
    fireEvent.click(screen.getByRole('button', { name: 'Yerleşimleri yükle' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Yerleşimi düzenle' }));
    fireEvent.click(screen.getByRole('button', { name: 'Masa ekle' }));
    const save = screen.getByRole('button', { name: 'Yerleşimi doğrula / kaydet' });
    fireEvent.click(save);
    expect(await screen.findByRole('alert')).toHaveTextContent('Masa kapasitesi yetersiz');
    expect(changed).not.toHaveBeenCalled();
    expect(screen.getByRole('img', { name: 'Ölçekli masa yerleşimi' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Kişi'), { target: { value: '10' } });
    fireEvent.click(save);
    await waitFor(() => expect(changed).toHaveBeenCalledOnce());
    expect(axios.put.mock.calls[1][1]).toMatchObject({ booking_index: 0, expected_revision: 'revision-1', tables: [expect.objectContaining({ seats: 10 })] });
  });

  it('records confirmed recipe batches without creating a sale or payment', async () => {
    axios.get.mockResolvedValue({ data: { consumptions: [], recipes: [{ id: 'recipe', menu_item_name: 'Synthetic soup', serving_size: 4 }], orders: [{ id: 'production', lines: [{ name: 'Synthetic service', quantity: 8, unit: 'pax' }] }] } });
    axios.post.mockResolvedValue({ data: {} });
    const changed = vi.fn();
    render(<EventConsumption eventId="event" onChanged={changed} />);
    fireEvent.click(screen.getByRole('button', { name: 'Tamamlanan üretimleri / sarfları yükle' }));
    const source = await screen.findByLabelText('Tamamlanan üretim satırı');
    fireEvent.change(source, { target: { value: 'production|0' } });
    fireEvent.change(screen.getByLabelText('Fiilen kullanılan reçete'), { target: { value: 'recipe' } });
    fireEvent.change(screen.getByLabelText('Tüketilen reçete partisi'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('Sarf açıklaması'), { target: { value: 'Synthetic actual use' } });
    fireEvent.click(screen.getByRole('button', { name: 'Stoktan düş / maliyete ekle' }));
    await waitFor(() => expect(changed).toHaveBeenCalledOnce());
    expect(axios.post).toHaveBeenCalledExactlyOnceWith('/mice/events/event/stock-consumptions', { order_id: 'production', line_index: 0, recipe_id: 'recipe', batches: 2, reason: 'Synthetic actual use' });
  });

  it('lets only an assigned staff task expose partial handover actions', async () => {
    promptDialog.mockResolvedValue('2');
    axios.get.mockResolvedValue({ data: { event_status: 'confirmed', tasks: [{ id: 'task', kind: 'equipment', title: 'Chairs', department: 'banquet', quantity: 10, status: 'pending', can_transition: true }], equipment: [] } });
    axios.post.mockResolvedValue({ data: {} });
    render(<OperationTasks eventId="event" canManage={false} />);
    expect(screen.queryByRole('button', { name: 'Yeni görev / teslim planı' })).not.toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: 'Kısmi teslim' }));
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/mice/events/event/tasks/task/handover', { action: 'deliver', quantity: 2, request_id: expect.any(String) }));
  });
});
