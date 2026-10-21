import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PrintableFolio from '@/components/PrintableFolio';

describe('PrintableFolio', () => {
  beforeEach(() => { window.print = vi.fn(); });

  it('Türkçe, rezervasyon para birimiyle ve tüm folyo kalemleriyle yazdırılır', () => {
    render(<PrintableFolio
      folioData={{
        folio_number: 'F-101',
        currency: 'TL',
        booking: { id: 'RES-1', check_in: '2026-09-20', check_out: '2026-09-22', adults: 2 },
        charges: [{ id: 'c1', description: 'Konaklama', amount: 1000, charge_category: 'room' }],
        extra_charges: [{ id: 'e1', charge_name: 'Türk kahvesi', charge_amount: 250, category: 'food_beverage' }],
        payments: [{ id: 'p1', amount: 500, payment_method: 'cash' }],
      }}
      guest={{ name: 'Test Misafir', phone: '555' }}
      room={{ room_number: '103', room_type: 'Standart' }}
      onClose={vi.fn()}
    />);

    expect(screen.getByText('Misafir Folyosu')).toBeInTheDocument();
    expect(screen.getByText('Türk kahvesi')).toBeInTheDocument();
    expect(screen.getByText('Yiyecek & İçecek')).toBeInTheDocument();
    expect(screen.getAllByText(/₺/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/GUEST FOLIO|No charges|USD/)).toBeNull();
    fireEvent.click(screen.getByTestId('print-folio'));
    expect(window.print).toHaveBeenCalledOnce();
  });

  it('önceki PMS bakiyesini yeni gelir veya ödeme satırı yapmadan ayrıca gösterir', () => {
    render(<PrintableFolio folioData={{ folio_number: 'MIG-101', currency: 'TRY', opening_balance: 50, charges: [{ id: 'new-charge', total: 100 }], payments: [{ amount: 25 }] }} />);
    expect(screen.getByText('Önceki PMS devir bakiyesi')).toBeInTheDocument();
    expect(screen.getByText('Yeni gelir veya tahsilat değildir.')).toBeInTheDocument();
    expect(screen.getAllByText(/125,00/).length).toBeGreaterThan(0);
  });
});
