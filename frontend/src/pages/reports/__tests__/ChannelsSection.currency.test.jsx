import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { ChannelsSection } from '../ChannelsSection';

afterEach(() => cleanup());

describe('channel revenue currency integrity', () => {
  it('does not compare different channel currencies on one revenue axis', () => {
    render(
      <ChannelsSection
        sourceData={[
          { name: 'Doğrudan', count: 3, revenue: 10000, revenueByCurrency: { TRY: 10000 } },
          { name: 'Online acente', count: 2, revenue: 200, revenueByCurrency: { EUR: 200 } },
        ]}
      />,
    );

    expect(screen.getByTestId('mixed-currency-revenue-warning')).toBeInTheDocument();
    expect(screen.getByText('Farklı para birimleri tek gelir grafiğinde karşılaştırılmadı.')).toBeInTheDocument();
    expect(screen.getByText(/₺10\.000/)).toBeInTheDocument();
    expect(screen.getByText(/€200/)).toBeInTheDocument();
  });
});
