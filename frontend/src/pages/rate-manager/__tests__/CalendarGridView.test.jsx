import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CalendarGridView } from '../CalendarGridView';

const setup = () => {
  const props = {
    filteredGrid: [], dates: [], roomTypes: [], ratePlans: [],
    gridRoomType: 'all', setGridRoomType: vi.fn(), gridRatePlan: 'all', setGridRatePlan: vi.fn(),
    startDate: '2026-10-30', endDate: '2026-11-12', setStartDate: vi.fn(), setEndDate: vi.fn(),
    shiftDates: vi.fn(), fetchGrid: vi.fn(), loading: false, formatDate: vi.fn(), currency: 'USD',
  };
  const view = render(<CalendarGridView {...props} />);
  const choose = (start, end) => {
    fireEvent.change(screen.getByLabelText('Takvim başlangıcı'), { target: { value: start } });
    fireEvent.change(screen.getByLabelText('Takvim bitişi (dahil)'), { target: { value: end } });
  };
  const apply = () => fireEvent.click(screen.getByRole('button', { name: 'Aralığı göster' }));
  return { props, view, choose, apply };
};

describe('read-only calendar date selection', () => {
  it('applies a single-day range only on explicit submit', () => {
    const { props, choose, apply } = setup();
    choose('2026-11-10', '2026-11-10');
    expect(props.setStartDate).not.toHaveBeenCalled();
    expect(props.setEndDate).not.toHaveBeenCalled();
    apply();
    expect(props.setStartDate).toHaveBeenCalledExactlyOnceWith('2026-11-10');
    expect(props.setEndDate).toHaveBeenCalledExactlyOnceWith('2026-11-10');
    expect(props.fetchGrid).not.toHaveBeenCalled();
    expect(screen.getByText(/Yalnız görüntüler; fiyat, stok veya kanal kaydı değiştirmez/)).toBeInTheDocument();
  });

  it.each([
    ['', '2026-11-10', 'Başlangıç ve bitiş tarihlerini seçin.'],
    ['2026-11-11', '2026-11-10', 'Bitiş tarihi başlangıçtan önce olamaz.'],
    ['2026-01-01', '2027-01-02', 'Tek görünümde en fazla 366 gün seçebilirsiniz.'],
  ])('rejects invalid range %s to %s without changing the loaded calendar', (start, end, message) => {
    const { props, choose, apply } = setup();
    choose(start, end);
    apply();
    expect(screen.getByRole('alert')).toHaveTextContent(message);
    expect(props.setStartDate).not.toHaveBeenCalled();
    expect(props.setEndDate).not.toHaveBeenCalled();
    expect(props.fetchGrid).not.toHaveBeenCalled();
  });

  it('accepts exactly 366 inclusive days across a leap year', () => {
    const { props, choose, apply } = setup();
    choose('2028-01-01', '2028-12-31');
    apply();
    expect(props.setEndDate).toHaveBeenCalledWith('2028-12-31');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('synchronizes draft fields after week navigation', () => {
    const { props, view, choose } = setup();
    choose('2026-12-31', '2026-11-10');
    view.rerender(<CalendarGridView {...props} startDate="2026-11-06" endDate="2026-11-19" />);
    expect(screen.getByLabelText('Takvim başlangıcı')).toHaveValue('2026-11-06');
    expect(screen.getByLabelText('Takvim bitişi (dahil)')).toHaveValue('2026-11-19');
  });
});
