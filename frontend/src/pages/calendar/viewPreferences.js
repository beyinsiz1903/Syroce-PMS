export const CALENDAR_VIEW_PREFERENCES_KEY = 'syroce_calendar_view_preferences_v1';

export const DEFAULT_CALENDAR_VIEW_PREFERENCES = Object.freeze({
  operationMode: true,
  compactMode: true,
  showOccupancy: false,
  showTimeline: false,
});

export const readCalendarViewPreferences = (storage = globalThis.localStorage) => {
  try {
    const stored = JSON.parse(storage?.getItem(CALENDAR_VIEW_PREFERENCES_KEY) || '{}');
    return { ...DEFAULT_CALENDAR_VIEW_PREFERENCES, ...stored };
  } catch {
    return { ...DEFAULT_CALENDAR_VIEW_PREFERENCES };
  }
};

export const applyCalendarViewPreference = (previous, key, value) => {
  const next = { ...previous, [key]: Boolean(value) };
  if (key === 'operationMode' && value) {
    next.showOccupancy = false;
    next.showTimeline = false;
  }
  if ((key === 'showOccupancy' || key === 'showTimeline') && value) {
    next.operationMode = false;
  }
  return next;
};

