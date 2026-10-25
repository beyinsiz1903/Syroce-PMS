import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import MappingIssueCard from '../MappingIssueCard';
import { getUnassignedUrgency } from '../calendarHelpers';
import { mergeUnassignedAttention } from '../unassignedPanel';

const hold = { id: 'one', tenant_id: 'A', property_id: 'A', status: 'pending_mapping', source: { provider: 'exely', kind: 'ota_unmatched_hold' }, external_reservation_id: 'EXT', check_in: '2026-10-24T14:00:00', guest_name: 'Ahmet Yılmaz' };

describe('mapping quarantine is not room assignment or no-show', () => {
  it('groups exact legacy copies while preserving identifiers, not operational bookings', () => {
    const rows = mergeUnassignedAttention([hold, { ...hold, id: 'two' }, { id: 'normal', status: 'confirmed' }]);
    expect(rows).toHaveLength(2);
    expect(rows[0].booking_ids).toEqual(['one', 'two']);
    expect(rows[0].duplicate_hold_count).toBe(1);
    expect(hold.id).toBe('one');
  });

  it('does not conflate providers, properties, missing identities or terminal records', () => {
    expect(mergeUnassignedAttention([hold, { ...hold, source: { provider: 'hotelrunner' } }, { ...hold, property_id: 'B' }])).toHaveLength(3);
    expect(mergeUnassignedAttention([{ ...hold, external_reservation_id: null }, { ...hold, id: 'two', external_reservation_id: null }])).toHaveLength(2);
    expect(mergeUnassignedAttention([{ ...hold, status: 'cancelled' }])).toEqual([]);
  });

  it('merges inbox-only API issues with legacy calendar records without losing evidence', () => {
    const issue = { ...hold, id: 'mapping:A:exely:EXT', queue_kind: 'mapping_required', provider: 'exely', booking_ids: ['one', 'two'] };
    const rows = mergeUnassignedAttention([hold], [issue]);
    expect(rows).toHaveLength(1);
    expect(rows[0].booking_ids).toEqual(['one', 'two']);
  });

  it('offers source review, not No-Show, physical room selection or a fabricated balance', () => {
    const review = vi.fn();
    const row = mergeUnassignedAttention([hold, { ...hold, id: 'two' }])[0];
    render(<MappingIssueCard booking={row} onReview={review} />);
    expect(screen.getByText(/PMS'e kabul edilmemiş/)).toBeInTheDocument();
    expect(screen.getByText(/2 eski tutma/)).toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'No-Show' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Kanal eşleştirmesini incele' }));
    expect(review).toHaveBeenCalledWith('/exely');
  });

  it('uses open business date for today/tomorrow, even after wall-clock midnight', () => {
    expect(getUnassignedUrgency(hold, '2026-10-24').level).toBe('today');
    expect(getUnassignedUrgency(hold, '2026-10-23').level).toBe('tomorrow');
    expect(getUnassignedUrgency(hold, '2026-10-25').level).toBe('overdue');
  });
});
