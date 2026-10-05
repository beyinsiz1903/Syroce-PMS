import { describe, expect, it } from 'vitest';
import { bookingDragGrip, bookingDropCheckIn } from '../bookingDragPlacement';

const place = ({
  checkIn = '2026-09-10',
  visibleStart = '2026-09-10',
  sourceLeft = 200,
  grabX = 252,
  targetStart = '2026-09-15',
  targetLeft = 700,
  dropX = 752,
} = {}) => {
  const grip = bookingDragGrip({
    bookingCheckIn: checkIn,
    visibleStart,
    sourceLeft,
    clientX: grabX,
  });
  return bookingDropCheckIn({
    targetStart,
    targetLeft,
    clientX: dropX,
    ...grip,
  }).toISOString().slice(0, 10);
};

describe('reservation bar placement', () => {
  it('keeps the whole stay anchored to the exact grabbed point', () => {
    expect(place({ grabX: 360, dropX: 860 })).toBe('2026-09-15');
    expect(place({ grabX: 360, dropX: 756 })).toBe('2026-09-14');
  });

  it('uses the cursor position on an occupied target bar, not that booking’s arrival', () => {
    expect(place({ grabX: 360, targetStart: '2026-09-14', targetLeft: 596, dropX: 960 })).toBe('2026-09-16');
  });

  it('preserves the hidden portion of a stay that began before the visible calendar', () => {
    expect(place({ checkIn: '2026-09-07', visibleStart: '2026-09-10' })).toBe('2026-09-12');
  });

  it('snaps the bar edge only after crossing half a day, without date-cell selection', () => {
    expect(place({ dropX: 803 })).toBe('2026-09-15');
    expect(place({ dropX: 804 })).toBe('2026-09-16');
  });
});
