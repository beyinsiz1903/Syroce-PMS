import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ResultTable } from '../POSExtensions';

describe('POS operator results', () => {
  it('renders translated fields and status without raw JSON or internal payloads', () => {
    const { container } = render(<ResultTable data={[{ id: 'internal', code: 'SAVE', status: 'failed', used_count: 2, last_error: 'Bağlantı kesildi', payload: { secret: 'hidden' } }]} />);
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.getByText('Başarısız')).toBeInTheDocument();
    expect(screen.getByText('Kullanım')).toBeInTheDocument();
    expect(screen.getByText('Bağlantı kesildi')).toBeInTheDocument();
    expect(container.querySelector('pre')).toBeNull();
    expect(screen.queryByText('hidden')).not.toBeInTheDocument();
  });
  it('shows an explicit empty state', () => {
    render(<ResultTable data={[]} />);
    expect(screen.getByText('Kayıt bulunamadı.')).toBeInTheDocument();
  });
});
