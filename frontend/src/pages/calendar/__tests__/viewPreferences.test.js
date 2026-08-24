import { describe, expect, it } from 'vitest';

import {
  applyCalendarViewPreference,
  CALENDAR_VIEW_PREFERENCES_KEY,
  readCalendarViewPreferences,
} from '../viewPreferences';

describe('reservation calendar view preferences', () => {
  it('starts in a compact operation view with optional bands closed', () => {
    const storage = { getItem: () => null };
    expect(readCalendarViewPreferences(storage)).toEqual({
      operationMode: true,
      compactMode: true,
      showOccupancy: false,
      showTimeline: false,
    });
  });

  it('restores saved browser preferences', () => {
    const storage = {
      getItem: (key) => key === CALENDAR_VIEW_PREFERENCES_KEY
        ? JSON.stringify({ compactMode: false, showTimeline: true, operationMode: false })
        : null,
    };
    expect(readCalendarViewPreferences(storage)).toMatchObject({
      compactMode: false,
      showTimeline: true,
      operationMode: false,
    });
  });

  it('keeps operation mode and analytical bands mutually consistent', () => {
    const analytical = applyCalendarViewPreference({
      operationMode: true,
      compactMode: true,
      showOccupancy: false,
      showTimeline: false,
    }, 'showOccupancy', true);
    expect(analytical).toMatchObject({ operationMode: false, showOccupancy: true });

    const operation = applyCalendarViewPreference({ ...analytical, showTimeline: true }, 'operationMode', true);
    expect(operation).toMatchObject({
      operationMode: true,
      showOccupancy: false,
      showTimeline: false,
    });
  });
});

