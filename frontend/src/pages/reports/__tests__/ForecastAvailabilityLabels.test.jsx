import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { Bar, ComposedChart, LabelList, Line } from 'recharts';
import { availabilityLabelAnchor, AvailabilityTooltip, RemainingRoomsLabel } from '../ForecastAvailabilityLabels';

afterEach(cleanup);

it.each([[0, '0'], [5, '+5'], [-2, '-2'], [31, '+31'], [null, '—'], [undefined, '—'], [NaN, '—']])(
  'labels the signed net remaining count %s, including zero and unknown values', (value, expected) => {
    const { container } = render(<svg><RemainingRoomsLabel value={value} viewBox={{ x: 40, y: 30, width: 20, height: 0 }} /></svg>);
    const label = container.querySelector('text');
    expect(label).toHaveTextContent(expected);
    expect(label).toHaveAttribute('x', '50');
    expect(label).toHaveAttribute('y', '22');
    expect(label).toHaveAttribute('fill', value < 0 ? 'hsl(var(--destructive))' : 'hsl(var(--foreground))');
  },
);

it.each([undefined, {}, { x: 0, y: NaN, width: 20 }])('does not render a label at invalid coordinates', viewBox => {
  const { container } = render(<svg><RemainingRoomsLabel value={0} viewBox={viewBox} /></svg>);
  expect(container.querySelector('text')).toBeNull();
});

it('uses the server net count, not the physical capacity or an individual stack segment, in the tooltip', () => {
  const row = { physical_rooms: 31, booked_rooms: 31, block_rooms: 0, blocked_rooms: 0, vacant_rooms: 0, remaining_rooms: 0 };
  render(<AvailabilityTooltip active payload={[{ payload: row }]} label="31 Eki" />);
  expect(screen.getByText('Kalan oda: 0')).toBeInTheDocument();
  expect(screen.getByText('31 Eki')).toBeInTheDocument();
  expect(screen.getByText('Rezervasyon').nextSibling).toHaveTextContent('31');
  expect(screen.queryByText('Kalan oda: +31')).not.toBeInTheDocument();
});

it('preserves negative net availability rather than clipping it to the zero vacant-room segment', () => {
  render(<AvailabilityTooltip active payload={[{ payload: { remaining_rooms: -2, vacant_rooms: 0, booked_rooms: 33, block_rooms: 0, blocked_rooms: 0 } }]} label="01 Kas" />);
  expect(screen.getByText('Kalan oda: -2')).toHaveClass('text-destructive');
});

it('does not invent capacity or zero when net remaining is unknown', () => {
  render(<AvailabilityTooltip active payload={[{ payload: { physical_rooms: 31, remaining_rooms: null } }]} />);
  expect(screen.getByText('Kalan oda: —')).toBeInTheDocument();
  expect(screen.getAllByRole('definition').map(node => node.textContent)).toEqual(['—', '—', '—']);
});

it.each([{ active: false, payload: [{ payload: {} }] }, { active: true, payload: [] }, { active: true }])(
  'keeps the tooltip hidden without an active data point', props => {
    const { container } = render(<AvailabilityTooltip {...props} />);
    expect(container).toBeEmptyDOMElement();
  },
);

it('renders exactly one remaining-room label per day with real Recharts, even when the last stack is zero', () => {
  const rows = [
    { booked_rooms: 31, block_rooms: 0, vacant_rooms: 0, blocked_rooms: 0, remaining_rooms: 0 },
    { booked_rooms: 22, block_rooms: 2, vacant_rooms: 5, blocked_rooms: 2, remaining_rooms: 5 },
    { booked_rooms: 33, block_rooms: 0, vacant_rooms: 0, blocked_rooms: 0, remaining_rooms: -2 },
    { booked_rooms: 0, block_rooms: 0, vacant_rooms: 31, blocked_rooms: 0, remaining_rooms: 31 },
  ];
  const { container } = render(<ComposedChart width={800} height={260} data={rows.map(row => ({ ...row, anchor: availabilityLabelAnchor(row) }))} margin={{ top: 28 }}>
    {['booked_rooms', 'block_rooms', 'vacant_rooms', 'blocked_rooms'].map(key => <Bar key={key} dataKey={key} stackId="rooms" isAnimationActive={false} />)}
    <Line dataKey="anchor" stroke="none" dot={false} activeDot={false} legendType="none" tooltipType="none" isAnimationActive={false}>
      <LabelList dataKey="remaining_rooms" position="top" content={<RemainingRoomsLabel />} />
    </Line>
  </ComposedChart>);
  const labels = [...container.querySelectorAll('.forecast-remaining-room-label')];
  expect(labels.map(label => label.textContent)).toEqual(['0', '+5', '-2', '+31']);
  expect(labels.every(label => Number.isFinite(Number(label.getAttribute('y'))) && Number(label.getAttribute('y')) >= 0)).toBe(true);
});

it('uses stack totals only for positioning and does not coerce unknown segments to capacity or zero', () => {
  expect(availabilityLabelAnchor({ booked_rooms: 22, block_rooms: 2, vacant_rooms: 5, blocked_rooms: 2 })).toBe(31);
  expect(availabilityLabelAnchor({ booked_rooms: 31, block_rooms: 0, vacant_rooms: 0, blocked_rooms: 0 })).toBe(31);
  expect(availabilityLabelAnchor({ booked_rooms: null, block_rooms: 0, vacant_rooms: 0, blocked_rooms: 0 })).toBeNull();
});
