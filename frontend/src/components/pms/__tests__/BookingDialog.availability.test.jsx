import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import BookingDialog from '../BookingDialog';
import tr from '@/locales/tr.json';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('axios', () => ({ default: { get, post: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key, fallback) => key.split('.').reduce((o, k) => o?.[k], tr) || fallback || key }) }));

const available = [{ id: 'r1', room_number: '101', room_type: 'Junior Suite', status: 'occupied', available: true }];
const props = () => ({ open: true, onClose: vi.fn(), guests: [], rooms: available, companies: [], ratePlans: [], packages: [],
  newBooking: { check_in: '2027-01-13', check_out: '2027-01-15', currency: 'TRY', children: 0 },
  setNewBooking: vi.fn(), multiRoomBooking: [{ id: 'line', room_id: 'r1', adults: 1, children: 0, total_amount: 190 }],
  handleCreateBooking: vi.fn(), updateMultiRoomField: vi.fn(), addRoomToMultiBooking: vi.fn(), setOpenDialog: vi.fn(), isLite: true });
const submit = () => screen.getByRole('button', { name: 'Rezervasyonu oluştur' });
const ready = () => waitFor(() => expect(submit()).toBeEnabled());
beforeEach(() => { get.mockReset(); get.mockResolvedValue({ data: available }); });
afterEach(cleanup);

it('uses date availability, not current housekeeping status, and excludes closed physical sources', async () => {
  get.mockResolvedValue({ data: [...available,
    { id: 'r2', room_number: '102', status: 'available', available: false },
    { id: 'deleted', room_number: '103', available: true, deleted_at: '2026-10-20' },
    { id: 'inactive', room_number: '104', available: true, is_active: false },
    { id: 'virtual', room_number: '105', available: true, is_virtual: true },
  ] });
  render(<BookingDialog {...props()} />); await ready();
  expect(get).toHaveBeenCalledWith('/pms/rooms/availability', expect.objectContaining({ params: { check_in: '2027-01-13', check_out: '2027-01-15' } }));
  fireEvent.click(screen.getByRole('combobox', { name: 'Oda 1' }));
  expect(screen.getByRole('option', { name: 'Oda 101 - Junior Suite' })).toBeInTheDocument();
  expect(screen.getAllByRole('option')).toHaveLength(1);
});

it('blocks pending and failed reads, guards direct form submission and supports explicit retry', async () => {
  let reject;
  get.mockReturnValueOnce(new Promise((resolve, fail) => { reject = fail; }));
  const p = props(); render(<BookingDialog {...p} />);
  expect(submit()).toBeDisabled();
  fireEvent.submit(submit().closest('form'));
  expect(p.handleCreateBooking).not.toHaveBeenCalled();
  await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
  await act(async () => reject(new Error('Read failed')));
  expect(screen.getByRole('alert')).toHaveTextContent('müsaitliği okunamadı');
  expect(submit()).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Müsaitliği yeniden kontrol et' }));
  await ready();
});

it('ignores a late old-date response and refuses a newly unavailable selection', async () => {
  let resolve;
  get.mockReturnValueOnce(new Promise(done => { resolve = done; }));
  const p = props(); const view = render(<BookingDialog {...p} />);
  await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
  get.mockResolvedValueOnce({ data: [{ ...available[0], available: false }] });
  view.rerender(<BookingDialog {...p} newBooking={{ ...p.newBooking, check_out: '2027-01-16' }} />);
  await screen.findByText('Seçili tarih aralığında müsait fiziksel oda yok.');
  await act(async () => resolve({ data: available }));
  expect(submit()).toBeDisabled();
  expect(screen.getByRole('alert')).toHaveTextContent('yeniden oda seçin');
});

it.each([null, {}, [{ id: 'r1', available: 'true' }], [...available, ...available]])('fails closed on incomplete or duplicate API data: %j', async data => {
  get.mockResolvedValue({ data }); render(<BookingDialog {...props()} />);
  expect(await screen.findByRole('alert')).toHaveTextContent('müsaitliği okunamadı');
  expect(submit()).toBeDisabled();
});

it('does not read or submit without a valid ordered date range', async () => {
  const p = props(); render(<BookingDialog {...p} newBooking={{ ...p.newBooking, check_out: p.newBooking.check_in }} />);
  expect(submit()).toBeDisabled(); fireEvent.submit(submit().closest('form'));
  await act(async () => {});
  expect(get).not.toHaveBeenCalled(); expect(p.handleCreateBooking).not.toHaveBeenCalled();
});

it('rejects duplicate physical room selection without calling the writer', async () => {
  const p = props(); render(<BookingDialog {...p} multiRoomBooking={[...p.multiRoomBooking, { ...p.multiRoomBooking[0], id: 'line2' }]} />);
  await waitFor(() => expect(get).toHaveBeenCalled());
  await act(async () => {});
  expect(submit()).toBeDisabled(); fireEvent.submit(submit().closest('form'));
  expect(p.handleCreateBooking).not.toHaveBeenCalled();
});

it('ignores a pending response after the dialog closes', async () => {
  let resolve; get.mockReturnValueOnce(new Promise(done => { resolve = done; }));
  const p = props(); const view = render(<BookingDialog {...p} />);
  await waitFor(() => expect(get).toHaveBeenCalled());
  view.rerender(<BookingDialog {...p} open={false} />);
  await act(async () => resolve({ data: available }));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});
