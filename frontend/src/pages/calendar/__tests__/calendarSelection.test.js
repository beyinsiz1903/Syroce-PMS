import { describe, expect, it, vi } from 'vitest';

import { clearCalendarTextSelection } from '../CalendarGrid';

describe('calendar text selection', () => {
  it('clears accidental browser text selection when the grid is pressed', () => {
    const removeAllRanges = vi.fn();
    const getSelection = vi.spyOn(window, 'getSelection').mockReturnValue({ removeAllRanges });

    clearCalendarTextSelection();

    expect(removeAllRanges).toHaveBeenCalledOnce();
    getSelection.mockRestore();
  });
});
